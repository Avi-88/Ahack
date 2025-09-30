from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import (
    openai,
    cartesia,
    deepgram,
    noise_cancellation,
    silero,
)
from livekit.plugins.turn_detector.multilingual import MultilingualModel

load_dotenv(".env.local")


class Miso(Agent):
    def __init__(self, session_id: str, user_id: str):
        super().__init__()
        self.session_id = session_id
        self.user_id = user_id
        self.db_pool = None


    async def setup(self):
        """Initialize database connection"""
        self.db_pool = await asyncpg.create_pool(
            'postgresql://user:pass@localhost/therapy_db'
        )
        
        # Load previous context if returning user
        await self.load_user_context()

    async def load_user_context(self):
        """Load previous session data for returning users"""
        async with self.db_pool.acquire() as conn:
            # Get last session summary
            last_summary = await conn.fetchrow("""
                SELECT s.summary, s.key_topics, s.emotional_journey
                FROM session_summaries s
                JOIN sessions sess ON s.session_id = sess.id
                WHERE sess.user_id = $1
                ORDER BY s.created_at DESC
                LIMIT 1
            """, self.user_id)
            
            # Get user profile
            profile = await conn.fetchrow("""
                SELECT recurring_themes, progress_indicators
                FROM user_profiles
                WHERE user_id = $1
            """, self.user_id)
            
            if last_summary:
                self.context_manager.previous_summary = last_summary['summary']
                self.context_manager.known_topics = last_summary['key_topics']
            
            if profile:
                self.context_manager.user_themes = profile['recurring_themes']
    
    @function_tool()
    async def save_conversation_turn(
        self, 
        ctx: RunContext,
        text: str,
        speaker: str,
        emotion: str = None
    ):
        """Save each conversation turn to database"""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO conversation_turns 
                (session_id, speaker, text, emotion, timestamp)
                VALUES ($1, $2, $3, $4, $5)
            """, self.session_id, speaker, text, emotion, datetime.now())
    
    async def on_session_end(self):
        """When conversation ends, generate and save summary"""
        # Generate summary using Deepgram
        full_transcript = self.context_manager.get_full_transcript()
        summary = await deepgram.summarize(full_transcript)
        
        async with self.db_pool.acquire() as conn:
            # Save session summary
            await conn.execute("""
                INSERT INTO session_summaries
                (session_id, summary, key_topics, emotional_journey)
                VALUES ($1, $2, $3, $4)
            """, 
            self.session_id, 
            summary,
            self.context_manager.topics,
            self.context_manager.emotional_journey
            )
            
            # Update user profile
            await conn.execute("""
                INSERT INTO user_profiles (user_id, last_session_summary, total_sessions)
                VALUES ($1, $2, 1)
                ON CONFLICT (user_id) 
                DO UPDATE SET 
                    last_session_summary = $2,
                    total_sessions = user_profiles.total_sessions + 1,
                    updated_at = NOW()
            """, self.user_id, summary)


async def entrypoint(ctx: agents.JobContext):
    room_metadata = json.loads(ctx.room.metadata)
    session_id = room_metadata["session_id"]
    user_id = room_metadata["user_id"]
    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=openai.LLM.with_cerebras(model="llama-3.3-70b"),
        tts=cartesia.TTS(model="sonic-2", voice="f786b574-daa5-4673-aa0c-cbe3e8534c02"),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )

    await session.start(
        room=ctx.room,
        agent=Miso(session_id, user_id),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(), 
        ),
    )

    await session.generate_reply(
        instructions="Greet the user and offer your assistance."
    )


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))