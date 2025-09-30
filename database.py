from prisma import Prisma
import os
from typing import Optional, List, Dict, Any
from datetime import datetime

class DatabaseManager:
    def __init__(self):
        self.prisma = Prisma()
        self._connected = False
    
    async def connect(self):
        """Connect to the database"""
        if not self._connected:
            await self.prisma.connect()
            self._connected = True
    
    async def disconnect(self):
        """Disconnect from the database"""
        if self._connected:
            await self.prisma.disconnect()
            self._connected = False
    
    async def create_session(self, user_id: str, room_name: str):
        """Create a new therapy session"""
        await self.connect()
        session = await self.prisma.session.create(
            data={
                'user_id': user_id,
                'room_name': room_name,
                'status': 'ACTIVE'
            }
        )
        return session
    
    async def get_user_sessions(self, user_id: str, limit: int = 20):
        """Get all sessions for a user with analytics data"""
        await self.connect()
        sessions = await self.prisma.session.find_many(
            where={'user_id': user_id},
            order_by={'started_at': 'desc'},
            take=limit
        )
        return sessions
    
    async def get_session_by_id(self, session_id: str):
        """Get a specific session by ID"""
        await self.connect()
        session = await self.prisma.session.find_unique(
            where={'id': session_id}
        )
        return session
    
    async def complete_session_with_analysis(
        self,
        session_id: str,
        duration: int,
        summary: str,
        key_topics: List[str],
        primary_emotions: List[str],
        mood_score: float,
        sentiment_trend: Dict[str, Any] = None,
        therapeutic_goals: List[str] = None,
        coping_strategies: List[str] = None,
        breakthrough_moments: str = None,
        homework_assigned: str = None,
        progress_notes: str = None,
        word_count: int = None,
        engagement_score: float = None,
        stress_indicators: List[str] = None
    ):
        """Complete a session with full analysis data"""
        await self.connect()
        
        session = await self.prisma.session.update(
            where={'id': session_id},
            data={
                'status': 'COMPLETED',
                'ended_at': datetime.now(),
                'duration': duration,
                'summary': summary,
                'key_topics': key_topics or [],
                'primary_emotions': primary_emotions or [],
                'mood_score': mood_score,
                'sentiment_trend': sentiment_trend,
                'therapeutic_goals': therapeutic_goals or [],
                'coping_strategies': coping_strategies or [],
                'breakthrough_moments': breakthrough_moments,
                'homework_assigned': homework_assigned,
                'progress_notes': progress_notes,
                'word_count': word_count,
                'engagement_score': engagement_score,
                'stress_indicators': stress_indicators or []
            }
        )
        return session
    
    async def get_user_analytics(self, user_id: str, days: int = 30):
        """Get aggregated analytics for a user over time"""
        await self.connect()
        from datetime import datetime, timedelta
        
        since_date = datetime.now() - timedelta(days=days)
        
        sessions = await self.prisma.session.find_many(
            where={
                'user_id': user_id,
                'status': 'COMPLETED',
                'started_at': {'gte': since_date}
            },
            order_by={'started_at': 'asc'}
        )
        
        return sessions
    
    async def get_mood_trends(self, user_id: str, days: int = 90):
        """Get mood score trends over time"""
        await self.connect()
        from datetime import datetime, timedelta
        
        since_date = datetime.now() - timedelta(days=days)
        
        sessions = await self.prisma.session.find_many(
            where={
                'user_id': user_id,
                'status': 'COMPLETED',
                'started_at': {'gte': since_date},
                'mood_score': {'not': None}
            },
            order_by={'started_at': 'asc'},
            select={
                'started_at': True,
                'mood_score': True,
                'primary_emotions': True
            }
        )
        
        return sessions
    
    async def get_topic_frequency(self, user_id: str, days: int = 30):
        """Get frequency of topics discussed"""
        await self.connect()
        from datetime import datetime, timedelta
        
        since_date = datetime.now() - timedelta(days=days)
        
        sessions = await self.prisma.session.find_many(
            where={
                'user_id': user_id,
                'status': 'COMPLETED',
                'started_at': {'gte': since_date}
            },
            select={
                'key_topics': True,
                'therapeutic_goals': True
            }
        )
        
        return sessions
    
    async def get_progress_insights(self, user_id: str):
        """Get overall progress insights for a user"""
        await self.connect()
        
        # Get all completed sessions
        all_sessions = await self.prisma.session.find_many(
            where={
                'user_id': user_id,
                'status': 'COMPLETED'
            },
            order_by={'started_at': 'asc'}
        )
        
        # Get recent sessions (last 5)
        recent_sessions = await self.prisma.session.find_many(
            where={
                'user_id': user_id,
                'status': 'COMPLETED'
            },
            order_by={'started_at': 'desc'},
            take=5
        )
        
        return {
            'all_sessions': all_sessions,
            'recent_sessions': recent_sessions
        }

# Global database instance
db = DatabaseManager()