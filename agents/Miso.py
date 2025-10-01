import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, RunContext
from livekit.agents.llm import function_tool
from livekit.plugins import (
    openai,
    cartesia,
    deepgram,
    noise_cancellation,
    silero,
)
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from utils import DeepgramWrapper

from context_manager import TherapyContextManager

load_dotenv(".env.local")


class Miso(Agent):
    def __init__(self, session_id: str, user_id: str):
        super().__init__()
        self.session_id = session_id
        self.user_id = user_id
        self.deepgram = DeepgramWrapper()
        self.db_pool = None
        self.audio_buffer = []
        # self.audio_file = None
        self.audio_payload = []


    async def setup(self):
        """Initialize database connection"""
        self.db_pool = await asyncpg.create_pool(
            'postgresql://user:pass@localhost/therapy_db'
        )
        
        isRestart  = 
        await self.load_user_context()

    async def stt_node(
        self, 
        audio: AsyncIterable[rtc.AudioFrame],
        model_settings: ModelSettings
    ) -> Optional[AsyncIterable[stt.SpeechEvent]]:
        
        async def buffered_audio():
            async for frame in audio:
                self.audio_buffer.append(frame)
                yield frame
        
        async for event in Agent.default.stt_node(self, buffered_audio(), model_settings):
            if event.type == stt.SpeechEventType.FINAL_TRANSCRIPT and self.audio_buffer:
                # sample_rate = 16000
                # channels = 1
                # sample_width = 2 

                # combined_data = b''.join([frame.data for frame in self.audio_buffer])
                
                # # Create WAV file in memory
                # wav_buffer = io.BytesIO()
                # with wave.open(wav_buffer, 'wb') as wav:
                #     wav.setnchannels(channels)
                #     wav.setsampwidth(sample_width)
                #     wav.setframerate(sample_rate)
                #     wav.writeframes(combined_data)
                
                # wav_buffer.seek(0)
                # self.audio_file =  wav_buffer.read()
                self.audio_payload = self.audio_buffer
                self.audio_buffer = []

            yield event

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage):
        # 1. Get Audio Intelligence results
        intelligent_context = await self.deepgram.get_audio_intelligence(self.audio_payload)
        self.audio_payload = []

        if intelligent_context:
            # 2. Add sentiment context
            turn_ctx.add_message(
                role="system", 
                content=f"Emotional Context: {intelligent_context['sentiments']}, Intents: {intelligent_context['intents']}"
            )
        # 4. Update the context
        await self.update_chat_ctx(turn_ctx)
            
    
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