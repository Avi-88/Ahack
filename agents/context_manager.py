import json
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import aiohttp
from dotenv import load_dotenv

load_dotenv()

@dataclass
class ConversationTurn:
    speaker: str  # "user" or "assistant" 
    content: str
    timestamp: datetime

class TherapyContextManager:
    def __init__(self, session_id: str, user_id: str):
        self.session_id = session_id
        self.user_id = user_id
        
        # Current session context (starts empty for new users, loaded for returning users)
        self.summary: Optional[str] = None
        self.topics: List[str] = []
        self.emotions: List[str] = []

        # Conversation transcript accumulation
        self.conversation_transcript: List[ConversationTurn] = []
        
        # API base URL for your FastAPI server
        self.api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
    
    async def load_context_from_room_metadata(self, room_metadata: Dict[str, Any]):
        """Load previous session context into current context for returning users"""

        self.summary = room_metadata.get("summary")
        self.topics = room_metadata.get("key_topics", [])
        self.emotions = room_metadata.get("primary_emotions", [])

    
    def add_conversation_turn(self, speaker: str, content: str):
        """Add a conversation turn to the transcript"""
        turn = ConversationTurn(
            speaker=speaker,
            content=content,
            timestamp=datetime.now()
        )
        self.conversation_transcript.append(turn)
    
    def update_context_from_deepgram(self, deepgram_analysis: Dict[str, Any]):
        """Update current context with latest Deepgram analysis"""
        
        # Update topics (add new ones, keep existing)
        new_topics = deepgram_analysis.get("topics", [])
        for topic in new_topics:
            if topic not in self.current_topics:
                self.current_topics.append(topic)
        
        # Update emotions (keep recent ones, add new)
        new_emotions = deepgram_analysis.get("sentiments", [])
        for emotion in new_emotions:
            if emotion not in self.current_emotions:
                self.current_emotions.append(emotion)
        
        # Update mood score (take latest if available)
        if deepgram_analysis.get("overall_sentiment_score") is not None:
            self.current_mood_score = deepgram_analysis.get("overall_sentiment_score")
    
    def get_context_for_llm(self) -> str:
        """Generate context string for LLM from current session state"""
        context_parts = []
        
        if self.current_summary:
            context_parts.append(f"Session context: {self.current_summary}")
            
        if self.current_topics:
            context_parts.append(f"Topics being discussed: {', '.join(self.current_topics)}")
            
        if self.current_emotions:
            # Show only recent emotions (last 3)
            recent_emotions = self.current_emotions[-3:]
            context_parts.append(f"Recent emotions detected: {', '.join(recent_emotions)}")
            
        if self.current_mood_score is not None:
            mood_desc = "positive" if self.current_mood_score > 0 else "negative" if self.current_mood_score < 0 else "neutral"
            context_parts.append(f"Current mood: {mood_desc}")
            
        if self.current_coping_strategies:
            context_parts.append(f"Coping strategies discussed: {', '.join(self.current_coping_strategies)}")
        
        return "\\n".join(context_parts) if context_parts else ""
    
    def get_full_transcript(self) -> str:
        """Get the complete conversation transcript for final analysis"""
        transcript_lines = []
        for turn in self.conversation_transcript:
            timestamp = turn.timestamp.strftime("%H:%M:%S")
            transcript_lines.append(f"[{timestamp}] {turn.speaker.upper()}: {turn.content}")
        
        return "\\n".join(transcript_lines)
    
    async def generate_final_summary_and_save(self, deepgram_analysis: Dict[str, Any]):
        """Generate final summary using transcript + Deepgram analysis and save to database"""
        
        # Get full transcript
        full_transcript = self.get_full_transcript()
        
        # Calculate session duration
        duration = self._calculate_session_duration()
        
        # Prepare analysis data from Deepgram + your processing
        analysis_data = {
            "duration": duration,
            "summary": await self._generate_session_summary(full_transcript),
            "key_topics": deepgram_analysis.get("topics", []),
            "primary_emotions": deepgram_analysis.get("sentiments", []),
            "mood_score": deepgram_analysis.get("overall_sentiment_score"),
            "sentiment_trend": deepgram_analysis.get("sentiment_progression"),
            "word_count": len(full_transcript.split()),
            "engagement_score": self._estimate_engagement_from_transcript()
        }
        
        # Save to database via API
        await self._save_session_analysis(analysis_data)
        
        return analysis_data
    
    def _calculate_session_duration(self) -> int:
        """Calculate session duration in seconds"""
        if not self.conversation_transcript:
            return 0
        
        start_time = self.conversation_transcript[0].timestamp
        end_time = self.conversation_transcript[-1].timestamp
        return int((end_time - start_time).total_seconds())
    
    async def _generate_session_summary(self, transcript: str) -> str:
        """Generate session summary using LLM call"""
        # You can replace this with OpenAI/Anthropic API call
        try:
            # Simplified for now - enhance with actual LLM summarization
            user_turns = len([t for t in self.conversation_transcript if t.speaker == "user"])
            duration_min = self._calculate_session_duration() // 60
            
            summary = f"Therapy session lasted {duration_min} minutes with {user_turns} user interactions. "
            
            if self.previous_summary:
                summary += "Building on previous session themes. "
            
            summary += "Session focused on therapeutic conversation and emotional support."
            
            return summary
            
        except Exception as e:
            print(f"Error generating summary: {e}")
            return "Session completed with therapeutic conversation."
    
    def _estimate_engagement_from_transcript(self) -> float:
        """Estimate engagement based on conversation patterns"""
        if not self.conversation_transcript:
            return 0.5
        
        user_turns = len([t for t in self.conversation_transcript if t.speaker == "user"])
        total_turns = len(self.conversation_transcript)
        
        # Basic engagement heuristics
        if user_turns == 0:
            return 0.1
        elif user_turns < 3:
            return 0.3
        elif user_turns < 8:
            return 0.6
        else:
            return 0.8
    
    async def _save_session_analysis(self, analysis_data: Dict[str, Any]):
        """Save analysis to FastAPI server"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_base_url}/api/sessions/{self.session_id}/complete",
                    json=analysis_data,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        print(f"Session analysis saved successfully for session {self.session_id}")
                    else:
                        print(f"Failed to save session analysis: {response.status}")
                        
        except Exception as e:
            print(f"Error saving session analysis: {e}")
            # Could implement retry logic or local storage as fallback