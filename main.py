from fastapi import FastAPI, HTTPException, Depends, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from livekit import api
from livekit.api import RoomConfiguration, RoomAgentDispatch
import os
import json
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
from auth import get_current_user, User, supabase
from database import db
from pydantic import BaseModel
from cerebras.cloud.sdk import Cerebras
import asyncio
import logging

load_dotenv(".env")

logger = logging.getLogger(__name__)

class CreateSessionRequest(BaseModel):
    session_id: Optional[str] = None

class ResumeSessionRequest(BaseModel):
    session_id: str

class DeleteSessionRequest(BaseModel):
    session_id: str

class SignInRequest(BaseModel):
    email: str
    password: str

class SignUpRequest(BaseModel):
    email: str
    password: str
    username: str

class SessionTranscriptWebhook(BaseModel):
    room_name: str
    transcript: str
    duration_seconds: int

app = FastAPI()

# CORS 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://miso-client.vercel.app", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

class LiveKitManager:
    def __init__(self):
        self.api_key = os.getenv("LIVEKIT_API_KEY")
        self.api_secret = os.getenv("LIVEKIT_API_SECRET")
        self.livekit_url = os.getenv("LIVEKIT_URL")
        
        self.room_service = api.LiveKitAPI(
            self.livekit_url,
            self.api_key,
            self.api_secret
        )

lk_manager = LiveKitManager()


async def analyze_session_with_llm(transcript: str, duration_seconds: int, max_retries: int = 3) -> dict:
    """Use LLM to analyze session transcript and generate insights with retry mechanism"""

    analysis_prompt = f"""
        Analyze the following conversation transcript and provide detailed insights. 
        The conversation lasted {duration_seconds} seconds.

        Transcript:
        {transcript}

        Guidelines:
        - summary: Write in SECOND PERSON perspective, addressing "you" directly to the user.
        Describe what happened in the conversation naturally, without explicitly mentioning "the assistant".
        Example: "You expressed feeling overwhelmed and frustrated with being stuck on a task, 
        but after discussing your concerns, you gained clarity and renewed energy to tackle the task again. 
        Through the conversation, you received empathetic support and practical advice, 
        helping you to reframe your approach and feel more in control."
        Use natural language like "through the conversation", "after discussing", "you explored", etc.
        - title: Short 3-5 word title for the session based on topics discussed
        - mood_score: 1-10 scale (1=very negative, 10=very positive)
        - engagement_score: 1-10 scale (1=very disengaged, 10=highly engaged)
        - key_topics: 3-5 main themes discussed
        - primary_emotions: 3-5 emotions detected throughout the session
        - stress_indicators: Signs of stress, anxiety, or distress mentioned
        - breakthrough_moments: Significant realizations or insights (in second person: "You realized...")
        - word_count: Approximate number of words in the transcript

        Focus on therapeutic value and emotional insights. Be empathetic and professional.
        Write as if speaking directly to the person, describing their journey through the conversation 
        without explicitly referencing the assistant.
        """

    analysis_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Short 3-5 word title for the session based on topics discussed"
            },
            "summary": {
                "type": "string",
                "description": "Brief 5-6 sentence summary of the session"
            },
            "key_topics": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-5 main themes discussed in the conversation"
            },
            "primary_emotions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-5 emotions detected throughout the session"
            },
            "mood_score": {
                "type": "number",
                "description": "Overall mood on 1-10 scale"
            },
            "breakthrough_moments": {
                "type": "string",
                "description": "Description of any significant insights or breakthroughs"
            },
            "word_count": {
                "type": "integer",
                "description": "Approximate number of words in the transcript"
            },
            "engagement_score": {
                "type": "number",
                "description": "Engagement level on 1-10 scale"
            },
            "stress_indicators": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Signs of stress, anxiety, or distress"
            }
        },
        "required": [
            "title",
            "summary",
            "key_topics",
            "primary_emotions",
            "mood_score",
            "word_count",
            "engagement_score",
            "stress_indicators"
        ],
        "additionalProperties": False
    }

    def get_default_analysis():
        """Return default analysis when LLM fails"""
        return {
            "title": int(datetime.now()),
            "summary": "Session completed successfully",
            "status": "ERROR",
            "key_topics": ["general discussion"],
            "primary_emotions": ["neutral"],
            "mood_score": 5.0,
            "breakthrough_moments": "",
            "word_count": len(transcript.split()),
            "engagement_score": 5.0,
            "stress_indicators": []
        }
    
    # Retry with exponential backoff
    for attempt in range(max_retries):
        try:
            logger.info(f"🤖 LLM Analysis attempt {attempt + 1}/{max_retries}")
            
            client = Cerebras(
                api_key=os.environ.get("CEREBRAS_API_KEY"),
            )
            
            response = client.chat.completions.create(
                model="llama-4-scout-17b-16e-instruct",
                messages=[
                    {"role": "system", "content": "You are a professional conversation analyzer specializing in therapeutic sessions. When writing summaries, always address the user in SECOND PERSON using 'you' and 'your'. Describe what happened in the conversation naturally without explicitly mentioning 'the assistant' or 'the AI'. Use phrases like 'through the conversation', 'after discussing', 'you explored', 'you discovered', etc. Write as if narrating the user's journey."},
                    {"role": "user", "content": analysis_prompt}
                ],
                temperature=0.3,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "session_analysis",
                        "strict": True,
                        "schema": analysis_schema
                    }
                }
            )
            
            # Parse the JSON response
            analysis_text = response.choices[0].message.content

            if not analysis_text or not analysis_text.strip():
                logger.error("LLM returned empty response")
                raise ValueError("Empty response from LLM")
            
            analysis_data = json.loads(analysis_text.strip())
            analysis_data["status"] = "COMPLETED"
            logger.info(f"LLM Analysis successful on attempt {attempt + 1}")
            return analysis_data
            
        except Exception as e:
            logger.warning(f"LLM Analysis attempt {attempt + 1} failed: {e}")
            
            # If this is the last attempt, return default
            if attempt == max_retries - 1:
                logger.error(f"All {max_retries} LLM attempts failed. Using default analysis.")
                return get_default_analysis()
            
            # Exponential backoff: wait 2^attempt seconds (1s, 2s, 4s, etc.)
            wait_time = 2 ** attempt
            logger.info(f"Waiting {wait_time}s before retry...")
            await asyncio.sleep(wait_time)
    
    return get_default_analysis()

@app.post("/auth/signin")
async def signin(request: SignInRequest):
    """Sign in user with email and password"""
    try:
        response = supabase.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password
        })
        
        if response.user:
            # Create response with user data
            user_data = {
                "user": {
                    "id": response.user.id,
                    "email": response.user.email,
                    "username": response.user.user_metadata.get('username', response.user.email.split('@')[0])
                }
            }
            
            # Create HTTP response
            from fastapi import Response
            response_obj = Response(content=json.dumps(user_data))
            
            # Set HTTP-only cookies for tokens
            response_obj.set_cookie(
                key="access_token",
                value=response.session.access_token,
                httponly=True,  # Cannot be accessed by JavaScript
                secure=True,    # Only sent over HTTPS
                samesite="strict",  # CSRF protection
                max_age=3600    # 1 hour expiration
            )
            
            response_obj.set_cookie(
                key="refresh_token", 
                value=response.session.refresh_token,
                httponly=True,
                secure=True,
                samesite="strict",
                max_age=604800  # 7 days expiration
            )
            
            return response_obj
        else:
            raise HTTPException(status_code=401, detail="Invalid credentials")
            
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

@app.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    """Refresh access token using HTTP-only refresh token"""
    try:
        # Get refresh token from HTTP-only cookie
        refresh_token = request.cookies.get("refresh_token")
        
        if not refresh_token:
            raise HTTPException(status_code=401, detail="No refresh token found")
        
        # Use Supabase to refresh the session
        auth_response = supabase.auth.refresh_session(refresh_token)
        
        if not auth_response.session:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        
        session = auth_response.session
        user = auth_response.user
        
        # Set new HTTP-only cookies
        response.set_cookie(
            key="access_token",
            value=session.access_token,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=3600  # 1 hour
        )
        
        response.set_cookie(
            key="refresh_token", 
            value=session.refresh_token,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=604800  # 7 days
        )
        
        return {
            "message": "Token refreshed successfully",
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.user_metadata.get('username', user.email.split('@')[0])
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token refresh failed: {str(e)}")

@app.post("/auth/signup")  
async def signup(request: SignUpRequest):
    """Sign up new user with email and password"""
    try:
        response = supabase.auth.sign_up({
            "email": request.email,
            "password": request.password,
            "options": {
                "data": {
                    "username": request.username or request.email.split('@')[0]
                }
            }
        })
        
        if response.user:
            return {
                "message": "User created successfully. Please check your email for verification.",
                "user": {
                    "id": response.user.id,
                    "email": response.user.email,
                    "username": request.username or request.email.split('@')[0]
                }
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to create user")
            
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail=f"Registration failed: {str(e)}")

@app.post("/auth/signout")
async def signout(response: Response, current_user: User = Depends(get_current_user)):
    """Sign out current user"""
    try:
        supabase.auth.sign_out()
        
        # Clear HTTP-only cookies
        response.delete_cookie(
            key="access_token",
            httponly=True,
            secure=True,
            samesite="strict"
        )
        response.delete_cookie(
            key="refresh_token", 
            httponly=True,
            secure=True,
            samesite="strict"
        )
        
        return {"message": "Successfully signed out"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Sign out failed: {str(e)}")


@app.post("/api/create-session")
async def create_therapy_session(
    current_user: User = Depends(get_current_user),
):
    """Called by frontend to start therapy session"""
    print(current_user)
    # Create unique room name
    room_name = f"emotional_guidance_{current_user.id}_{int(datetime.now().timestamp())}"
    title = datetime.today().strftime('%Y-%m-%d')
    # Save to database using Prisma
    session = await db.create_session(
        user_id=current_user.id,
        title=title,
        room_name=room_name,
    )
    if not session:
        return {"status_code": 500, "detail": f"Failed to create a session"}

    room_metadata = {
        "user_id": current_user.id,
        "user_name": current_user.name,
        "session_id": session.id,
        "summary": None,
        "key_topics": None,
        "primary_emotions": None
    }
    
    await lk_manager.room_service.room.create_room(
        api.CreateRoomRequest(
            name=room_name,
            empty_timeout=300,
            max_participants=2,
            metadata=json.dumps(room_metadata)
        )
    )

    # Generate access token for user
    token = api.AccessToken(
        api_key=lk_manager.api_key,
        api_secret=lk_manager.api_secret,
    )
    token.with_identity(current_user.id)\
        .with_name(current_user.name or current_user.email)\
        .with_grants(api.VideoGrants(
             room_join=True,
             room=room_name
        ))\
        .with_room_config(
            RoomConfiguration(
                agents=[
                    RoomAgentDispatch(agent_name="miso", metadata=json.dumps(room_metadata))
                ],
            ),
        )
    
    
    return {
        "room_name": room_name,
        "token": token.to_jwt(),
        "session_id": session.id 
    }


@app.post("/api/resume-session")
async def resume_therapy_session(
    request: ResumeSessionRequest,
    current_user: User = Depends(get_current_user)
):
    """Resume therapy with context from previous session"""
    session_id = request.session_id
    print(f"this is it:{session_id}")
    # Get previous session data
    previous_session = await db.get_session_by_id(session_id)
    if not previous_session or previous_session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    room_metadata = {
        "user_id": current_user.id,
        "user_name": current_user.name,
        "session_id": session_id,
        "summary": previous_session.summary,
        "key_topics": previous_session.key_topics,
        "primary_emotions": previous_session.primary_emotions
    }
    
    # Create room with previous session context but same room name ( rooms are ephemeral )
    await lk_manager.room_service.room.create_room(
        api.CreateRoomRequest(
            name=previous_session.room_name,
            empty_timeout=300,
            max_participants=2,
            metadata=json.dumps(room_metadata)
        )
    )
    
    # Generate access token
    token = api.AccessToken(
        api_key=lk_manager.api_key,
        api_secret=lk_manager.api_secret
    )
    token.with_identity(current_user.id)\
         .with_name(current_user.name or current_user.email)\
         .with_grants(api.VideoGrants(
             room_join=True,
             room=previous_session.room_name
         ))\
         .with_room_config(
            RoomConfiguration(
                agents=[
                    RoomAgentDispatch(agent_name="miso", metadata=json.dumps(room_metadata))
                ],
            ),
        )
    
    return {
        "room_name": previous_session.room_name,
        "token": token.to_jwt(),
        "session_id": previous_session.id,
    }


@app.delete("/api/delete-session")
async def delete_therapy_session(
    request: DeleteSessionRequest,
    current_user: User = Depends(get_current_user)
):
    """Delete a therapy session"""
    try:
        session_id = request.session_id
        
        # Get session and verify ownership
        session = await db.get_session_by_id(session_id)
        if not session or session.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Delete the session
        deleted_session = await db.delete_session(session_id)
        if not deleted_session:
            raise HTTPException(status_code=500, detail="Failed to delete session")
        
        return {
            "message": "Session deleted successfully",
            "session_id": session_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")


@app.get("/api/analytics/progress")
async def get_progress_insights(current_user: User = Depends(get_current_user)):
    """Get overall progress insights and trends"""
    insights_data = await db.get_progress_insights(current_user.id)
    
    all_sessions = insights_data['all_sessions']
    recent_sessions = insights_data['recent_sessions']
    
    # Calculate progress metrics
    total_sessions = len(all_sessions)
    avg_mood_score = None
    mood_trend = None
    
    if all_sessions:
        mood_scores = [s.mood_score for s in all_sessions if s.mood_score is not None]
        if mood_scores:
            avg_mood_score = sum(mood_scores) / len(mood_scores)
            
            # Calculate mood trend (recent vs earlier)
            if len(mood_scores) >= 4:
                recent_mood = sum(mood_scores[-2:]) / 2
                earlier_mood = sum(mood_scores[:2]) / 2
                mood_trend = recent_mood - earlier_mood
    
    # Get most common topics and emotions
    all_topics = []
    all_emotions = []
    for session in all_sessions:
        all_topics.extend(session.key_topics)
        all_emotions.extend(session.primary_emotions)
    
    topic_frequency = {}
    emotion_frequency = {}
    
    for topic in all_topics:
        topic_frequency[topic] = topic_frequency.get(topic, 0) + 1
    
    for emotion in all_emotions:
        emotion_frequency[emotion] = emotion_frequency.get(emotion, 0) + 1
    
    return {
        "total_sessions": total_sessions,
        "average_mood_score": avg_mood_score,
        "mood_trend": mood_trend,
        "most_discussed_topics": sorted(topic_frequency.items(), key=lambda x: x[1], reverse=True)[:5],
        "common_emotions": sorted(emotion_frequency.items(), key=lambda x: x[1], reverse=True)[:5],
        "recent_sessions": recent_sessions
    }


@app.post("/webhooks/session-transcript")
async def receive_session_transcript(webhook_data: SessionTranscriptWebhook):
    """Webhook endpoint for agents to send session transcripts"""
    
    try:
        # Find session by room name
        session = await db.get_session_by_room_name(webhook_data.room_name)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session not found for room: {webhook_data.room_name}")
        
        # Check if session is not terminated 
        if session.status != 'ACTIVE' and session.status != 'COMPLETED':
            return {"message": "Session already processed", "session_id": session.id, "room_name": webhook_data.room_name}

        # Analyze transcript with LLM
        analysis_data = await analyze_session_with_llm(
            webhook_data.transcript, 
            webhook_data.duration_seconds
        )
        
        print(f"LLM Analysis completed: {analysis_data}")
        
        # Update session with analysis data
        completed_session = await db.complete_session_with_analysis(
            session_id=session.id,
            title=analysis_data.get('title'),
            status=analysis_data.get("status", "ERROR"),
            duration=webhook_data.duration_seconds,
            summary=analysis_data.get('summary', ''),
            key_topics=analysis_data.get('key_topics', []),
            primary_emotions=analysis_data.get('primary_emotions', []),
            mood_score=analysis_data.get('mood_score'),
            breakthrough_moments=analysis_data.get('breakthrough_moments',''),
            word_count=analysis_data.get('word_count'),
            engagement_score=analysis_data.get('engagement_score'),
            stress_indicators=analysis_data.get('stress_indicators', [])
        )
        
        print(f"Session completed successfully")
        
        return {
            "message": "Transcript processed successfully", 
            "status": 200
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error processing transcript webhook: {e}")
        
        # Mark session as ERROR if processing fails
        try:
            if 'session' in locals() and session:
                await db.prisma.session.update(
                    where={'id': session.id},
                    data={
                        'status': 'ERROR',
                        'ended_at': datetime.now()
                    }
                )
        except:
            pass 
            
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to process transcript: {str(e)}"
        )

@app.get("/api/user-sessions")
async def get_user_sessions(
    page: int = 1,
    page_size: int = 10,
    current_user: User = Depends(get_current_user),
):
    """Get sessions for the current user grouped by month with pagination"""
    try:
        sessions = await db.get_user_sessions_grouped_by_month(
            user_id=current_user.id,
            page=page,
            page_size=page_size
        )
        return sessions
    except Exception as e:
        print(f"Error getting user sessions: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve sessions")


@app.get("/api/sessions/{session_id}")
async def fetch_session_details(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get session data by id"""
    
    # Verify session belongs to user
    session = await db.get_session_by_id(session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Unauthorized Session access")
    
    return {"status": 200, "session": session}


@app.on_event("startup")
async def startup():
    await db.connect()

@app.on_event("shutdown") 
async def shutdown():
    await db.disconnect()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)