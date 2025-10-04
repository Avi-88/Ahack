from prisma import Prisma
from prisma.errors import PrismaError
import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv(".env")

class DatabaseManager:
    def __init__(self):
        self.prisma = Prisma()
        self._connected = False
    
    async def connect(self):
        """Connect to the database with error handling"""
        if not self._connected:
            try:
                await self.prisma.connect()
                self._connected = True
                logger.info("Database connected successfully")
            except Exception as e:
                logger.error(f"Failed to connect to database: {e}")
                raise
    
    async def disconnect(self):
        """Disconnect from the database with error handling"""
        if self._connected:
            try:
                await self.prisma.disconnect()
                self._connected = False
                logger.info("Database disconnected successfully")
            except Exception as e:
                logger.error(f"Error disconnecting from database: {e}")
    
    async def create_session(self, user_id: str, room_name: str):
        """Create a new therapy session with error handling"""
        try:
            await self.connect()
            session = await self.prisma.session.create(
                data={
                    'user_id': user_id,
                    'room_name': room_name,
                    'status': 'ACTIVE'
                }
            )
            logger.info(f"Session created successfully for user {user_id}")
            return session
        except PrismaError as e:
            logger.error(f"Database error creating session for user {user_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating session for user {user_id}: {e}")
            raise
    
    async def get_user_sessions(self, user_id: str, limit: int = 20):
        """Get all sessions for a user with analytics data"""
        try:
            await self.connect()
            sessions = await self.prisma.session.find_many(
                where={'user_id': user_id},
                order_by={'started_at': 'desc'},
                take=limit
            )
            logger.info(f"Retrieved {len(sessions)} sessions for user {user_id}")
            return sessions
        except PrismaError as e:
            logger.error(f"Database error getting sessions for user {user_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting sessions for user {user_id}: {e}")
            raise
    
    async def get_session_by_id(self, session_id: str):
        """Get a specific session by ID"""
        try:
            await self.connect()
            session = await self.prisma.session.find_unique(
                where={'id': session_id}
            )
            if session:
                logger.info(f"Session {session_id} retrieved successfully")
            else:
                logger.warning(f"Session {session_id} not found")
            return session
        except PrismaError as e:
            logger.error(f"Database error getting session {session_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting session {session_id}: {e}")
            raise
    
    async def get_session_by_room_name(self, room_name: str):
        """Get a specific session by room name"""
        try:
            await self.connect()
            session = await self.prisma.session.find_first(
                where={'room_name': room_name}
            )
            if session:
                logger.info(f"Session for room {room_name} retrieved successfully")
            else:
                logger.warning(f"Session for room {room_name} not found")
            return session
        except PrismaError as e:
            logger.error(f"Database error getting session by room name {room_name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting session by room name {room_name}: {e}")
            raise
    
    async def complete_session_with_analysis(
        self,
        status: str,
        session_id: str,
        duration: int,
        summary: str,
        key_topics: List[str],
        primary_emotions: List[str],
        mood_score: float,
        breakthrough_moments: str = None,
        word_count: int = None,
        engagement_score: float = None,
        stress_indicators: List[str] = None
    ):
        """Complete a session with full analysis data"""
        try:
            await self.connect()
            
            session = await self.prisma.session.update(
                where={'id': session_id},
                data={
                    'status': status or "ERROR",
                    'ended_at': datetime.now(),
                    'duration': duration,
                    'summary': summary,
                    'key_topics': key_topics or [],
                    'primary_emotions': primary_emotions or [],
                    'mood_score': mood_score,
                    'breakthrough_moments': breakthrough_moments,
                    'word_count': word_count,
                    'engagement_score': engagement_score,
                    'stress_indicators': stress_indicators or []
                }
            )
            logger.info(f"Session {session_id} completed successfully with analysis")
            return session
        except PrismaError as e:
            logger.error(f"Database error completing session {session_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error completing session {session_id}: {e}")
            raise
    
    async def get_user_analytics(self, user_id: str, days: int = 30):
        """Get aggregated analytics for a user over time"""
        try:
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
            
            logger.info(f"Retrieved analytics for user {user_id}: {len(sessions)} sessions")
            return sessions
        except PrismaError as e:
            logger.error(f"Database error getting analytics for user {user_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting analytics for user {user_id}: {e}")
            raise
    
    async def get_mood_trends(self, user_id: str, days: int = 90):
        """Get mood score trends over time"""
        try:
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
            
            logger.info(f"Retrieved mood trends for user {user_id}: {len(sessions)} sessions")
            return sessions
        except PrismaError as e:
            logger.error(f"Database error getting mood trends for user {user_id}: {e}")
            return []  # Return empty list for analytics failure
        except Exception as e:
            logger.error(f"Unexpected error getting mood trends for user {user_id}: {e}")
            return []
    
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