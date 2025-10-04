from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from livekit import api
from livekit.api import RoomConfiguration, RoomAgentDispatch
import os
import json
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

# Import our modules
from auth import get_current_user, User, supabase
from database import db
from pydantic import BaseModel

load_dotenv(".env")

class CreateSessionRequest(BaseModel):
    session_id: Optional[str] = None

class SignInRequest(BaseModel):
    email: str
    password: str

class SignUpRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None  

app = FastAPI()

# CORS 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001"],
    allow_methods=["*"],
    allow_headers=["*"],
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

@app.post("/auth/signin")
async def signin(request: SignInRequest):
    """Sign in user with email and password"""
    try:
        response = supabase.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password
        })
        
        if response.user:
            return {
                "access_token": response.session.access_token,
                "refresh_token": response.session.refresh_token,
                "user": {
                    "id": response.user.id,
                    "email": response.user.email,
                    "name": response.user.user_metadata.get('name', response.user.email.split('@')[0])
                }
            }
        else:
            raise HTTPException(status_code=401, detail="Invalid credentials")
            
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

@app.post("/auth/signup")  
async def signup(request: SignUpRequest):
    """Sign up new user with email and password"""
    try:
        response = supabase.auth.sign_up({
            "email": request.email,
            "password": request.password,
            "options": {
                "data": {
                    "name": request.name or request.email.split('@')[0]
                }
            }
        })
        
        if response.user:
            return {
                "message": "User created successfully. Please check your email for verification.",
                "user": {
                    "id": response.user.id,
                    "email": response.user.email,
                    "name": request.name or request.email.split('@')[0]
                }
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to create user")
            
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Registration failed: {str(e)}")

@app.post("/auth/signout")
async def signout(current_user: User = Depends(get_current_user)):
    """Sign out current user"""
    try:
        supabase.auth.sign_out()
        return {"message": "Successfully signed out"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Sign out failed: {str(e)}")

@app.get("/auth/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info"""
    return current_user

@app.post("/api/create-session")
async def create_therapy_session(
    current_user: User = Depends(get_current_user),
):
    """Called by frontend to start therapy session"""
    print(current_user)
    # 1. Create unique room name
    room_name = f"emotional_guidance_{current_user.id}_{int(datetime.now().timestamp())}"
    # 2. Save to database using Prisma
    session = await db.create_session(
        user_id=current_user.id
    )
    if not session:
        return {"status_code": 500, "detail": f"Failed to create a session"}

    room_metadata = {
        "user_id": current_user.id,
        "user_name": current_user.name or current_user.email,
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
    

    
    # 4. Generate access token for user
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
                    RoomAgentDispatch(agent_name="miso8", metadata=json.dumps(room_metadata))
                ],
            ),
        )
    
    
    return {
        "room_name": room_name,
        "token": token.to_jwt(),
        "session_id": session.id 
    }

@app.get("/api/session-history")
async def get_user_sessions(current_user: User = Depends(get_current_user)):
    """Get user's therapy history"""
    sessions = await db.get_user_sessions(current_user.id)
    return {"sessions": sessions}

@app.post("/api/resume-session")
async def resume_therapy_session(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """Resume therapy with context from previous session"""
    
    # 1. Get previous session data
    previous_session = await db.get_session_by_id(session_id)
    if not previous_session or previous_session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # 2. Create new room for resumed conversation
    room_name = f"emotional_guidance_{current_user.id}_{int(datetime.now().timestamp())}_resume"
    
    # 3. Create room with previous session context
    await lk_manager.room_service.room.create_room(
        api.CreateRoomRequest(
            name=room_name,
            empty_timeout=300,
            max_participants=2,
            metadata=json.dumps({
                "user_id": current_user.id,
                "user_name": current_user.name or current_user.email,
                "session_id": session_id,
                "summary": previous_session.summary,
                "key_topics": previous_session.key_topics,
                "primary_emotions": previous_session.primary_emotions
            })
        )
    )
    
    # 5. Generate access token
    token = api.AccessToken(
        api_key=lk_manager.api_key,
        api_secret=lk_manager.api_secret
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
        "session_id": previous_session.id,
    }

@app.get("/api/analytics/mood-trends")
async def get_mood_trends(
    days: int = 90,
    current_user: User = Depends(get_current_user)
):
    """Get user's mood trends over time"""
    mood_data = await db.get_mood_trends(current_user.id, days)
    return {"mood_trends": mood_data}

@app.get("/api/analytics/topics")
async def get_topic_analysis(
    days: int = 30,
    current_user: User = Depends(get_current_user)
):
    """Get frequency analysis of discussed topics"""
    topic_data = await db.get_topic_frequency(current_user.id, days)
    
    # Aggregate topic frequencies
    topic_counts = {}
    goal_counts = {}
    
    for session in topic_data:
        for topic in session.key_topics:
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
        for goal in session.therapeutic_goals:
            goal_counts[goal] = goal_counts.get(goal, 0) + 1
    
    return {
        "topics": topic_counts,
        "therapeutic_goals": goal_counts,
        "session_count": len(topic_data)
    }

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

@app.post("/api/sessions/{session_id}/complete")
async def complete_session_analysis(
    session_id: str,
    analysis_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Complete a session with analysis data (called by agent)"""
    
    # Verify session belongs to user
    session = await db.get_session_by_id(session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Complete session with analysis
    completed_session = await db.complete_session_with_analysis(
        session_id=session_id,
        duration=analysis_data.get('duration', 0),
        summary=analysis_data.get('summary', ''),
        key_topics=analysis_data.get('key_topics', []),
        primary_emotions=analysis_data.get('primary_emotions', []),
        mood_score=analysis_data.get('mood_score'),
        sentiment_trend=analysis_data.get('sentiment_trend'),
        therapeutic_goals=analysis_data.get('therapeutic_goals', []),
        coping_strategies=analysis_data.get('coping_strategies', []),
        breakthrough_moments=analysis_data.get('breakthrough_moments'),
        homework_assigned=analysis_data.get('homework_assigned'),
        progress_notes=analysis_data.get('progress_notes'),
        word_count=analysis_data.get('word_count'),
        engagement_score=analysis_data.get('engagement_score'),
        stress_indicators=analysis_data.get('stress_indicators', [])
    )
    
    return {"message": "Session completed successfully", "session": completed_session}

# Startup/shutdown events
@app.on_event("startup")
async def startup():
    await db.connect()

@app.on_event("shutdown") 
async def shutdown():
    await db.disconnect()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)