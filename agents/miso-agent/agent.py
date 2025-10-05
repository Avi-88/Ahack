import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from typing import AsyncIterable
from livekit import rtc
from typing import Optional
import io
import wave
import logging
import aiohttp
import os

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, RunContext, ModelSettings, stt, WorkerType, AutoSubscribe
from livekit.agents.llm import function_tool, ChatContext, ChatMessage
from livekit.plugins import (
    openai,
    cartesia,
    inworld,
    deepgram,
    noise_cancellation,
    silero,
)
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from utils import DeepgramWrapper

logger = logging.getLogger(__name__)
load_dotenv(".env.local")


class Miso(Agent):
    def __init__(self, room_name, room_metadata=None):
        # system prompt
        base_instructions = """You are a compassionate and empathetic mental health assistant. Your goal is to **understand the user's emotions and provide supportive guidance**, not medical diagnoses or treatment.
                Guidelines:
                1. **Recognize emotions:** Identify the user's feelings, tone, and sentiment (e.g., sadness, anxiety, stress, frustration, loneliness).  
                2. **Respond with empathy:** Validate and acknowledge their emotions. Use warm, understanding, and patient language. Example: "It sounds like you're feeling overwhelmed, and that's understandable."  
                3. **Provide safe guidance:** Offer general coping strategies like deep breathing, mindfulness, journaling, talking to someone trusted, or grounding exercises. Focus on helping the user navigate their feelings safely.  
                4. **Never diagnose or prescribe:** Do not give medical advice, clinical diagnoses, or treatment suggestions.  
                5. **Encourage support when needed:** Suggest seeking professional help if appropriate, phrased gently: "Talking to a trained professional can sometimes help when feelings are intense."  
                6. **Follow the user's lead:** Let the user describe their experience in their own words. Tailor responses to their needs without assumptions.  
                Your responses should always be **empathetic, validating, supportive, and safe**, helping the user process emotions constructively."""

        # Add context from room metadata if available
        context_instructions = self._build_context_instructions(room_metadata)
        full_instructions = base_instructions + context_instructions

        super().__init__(instructions=full_instructions)

        self.room_name = room_name
        self.room_metadata = room_metadata
        self.db_pool = None
        self.deepgram = DeepgramWrapper()
        self.audio_buffer_list = []
        self.audio_file = None

    def _build_context_instructions(self, room_metadata):
        """Building context-specific instructions from room metadata"""
        if not room_metadata:
            return ""

        context_parts = []
        
        if room_metadata.get('user_name'):
            context_parts.append(f"\n\nUser Context: You are speaking with {room_metadata['user_name']}.")

        if room_metadata.get('summary'):
            context_parts.append(f"\nPrevious Session Summary: {room_metadata['summary']}")

        if room_metadata.get('key_topics'):
            if isinstance(room_metadata['key_topics'], list):
                topics = ', '.join(room_metadata['key_topics'])
            else:
                topics = str(room_metadata['key_topics'])
            context_parts.append(f"\nKey Topics Previously Discussed: {topics}")

        if room_metadata.get('primary_emotions'):
            if isinstance(room_metadata['primary_emotions'], list):
                emotions = ', '.join(room_metadata['primary_emotions'])
            else:
                emotions = str(room_metadata['primary_emotions'])
            context_parts.append(f"\nPrimary Emotions from Previous Sessions: {emotions}")

        if context_parts:
            context_parts.append(f"\nImportant: Use this context to provide continuity and personalized support. Reference previous discussions naturally when relevant, but don't force connections. Allow the user to guide the conversation while being aware of their history.")

        return ''.join(context_parts)


        

    async def stt_node(
        self, 
        audio: AsyncIterable[rtc.AudioFrame],
        model_settings: ModelSettings
    ) -> Optional[AsyncIterable[stt.SpeechEvent]]:
        
        async def buffered_audio():
            async for frame in audio:
                self.audio_buffer_list.append(frame)
                yield frame
        
        async for event in Agent.default.stt_node(self, buffered_audio(), model_settings):
            if event.type == stt.SpeechEventType.FINAL_TRANSCRIPT and self.audio_buffer_list:
                sample_rate = 16000
                channels = 1
                sample_width = 2 

                combined_data = b''.join([frame.data for frame in self.audio_buffer_list])
                
                # Create WAV file in memory
                wav_buffer = io.BytesIO()
                with wave.open(wav_buffer, 'wb') as wav:
                    wav.setnchannels(channels)
                    wav.setsampwidth(sample_width)
                    wav.setframerate(sample_rate)
                    wav.writeframes(combined_data)
                
                wav_buffer.seek(0)
                self.audio_file =  wav_buffer.read()
            yield event

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage):
        audio_payload = self.audio_file
        if audio_payload:
            intelligent_context = await self.deepgram.get_audio_intelligence(audio_payload)
            self.audio_buffer_list = []
            self.audio_file = None
        else:
            intelligent_context = None

        print(intelligent_context)
        if intelligent_context:
            turn_ctx.add_message(
                role="system", 
                content=f"Emotional Context: {intelligent_context}"
            )
        await self.update_chat_ctx(turn_ctx)
            


async def entrypoint(ctx: agents.JobContext):
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    participant = await ctx.wait_for_participant()
    
    # Parse room metadata for context
    room_metadata = None
    if ctx.room.metadata:
        try:
            room_metadata = json.loads(ctx.room.metadata)
            print(f"Parsed metadata: {room_metadata}")
        except json.JSONDecodeError as e:
            print(f"Failed to parse room metadata: {e}")
            room_metadata = None
    
    # Store session start time
    session_start_time = datetime.now()

    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=openai.LLM.with_cerebras(model="llama-3.3-70b"),
        tts=inworld.TTS(voice="Wendy"),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )

    async def end_session_hook():
        try:
            # Convert session history to transcript string
            transcript_data = session.history.to_dict()
            transcript_text = ""
            
            for item in transcript_data.get('items', []):
                role = item.get('role', 'unknown')
                content = item.get('content', [])

                if role in ['user', 'assistant'] and content:
                    speaker = "User" if role == 'user' else "Assistant"
                    content_text = ' '.join(content).strip()
                    if content_text:
                        transcript_text += f"{speaker}: {content_text}\n"
            
            duration_seconds = int((datetime.now() - session_start_time).total_seconds())
            
            webhook_payload = {
                "room_name": ctx.room.name,
                "transcript": transcript_text,
                "duration_seconds": duration_seconds
            }
            
            webhook_url = f"{os.getenv('BACKEND_SERVER_BASE_URL', 'http://localhost:8000')}/webhooks/session-transcript"
            
            async with aiohttp.ClientSession() as client_session:
                async with client_session.post(
                    webhook_url,
                    json=webhook_payload,
                    headers={'Content-Type': 'application/json'}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        print(f"Transcript sent for room {ctx.room.name}")
                    else:
                        error_text = await response.text()
                        print(f"Failed to send transcript. Status: {response.status}, Error: {error_text}")
            
        except Exception as e:
            print(f"Error in end_session_hook: {e}")
            import traceback
            traceback.print_exc()


    await session.start(
        room=ctx.room,
        agent=Miso(ctx.room.name, room_metadata),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(), 
        ),
    )

    await session.generate_reply(
        instructions="Greet the user with a quick but warm greeting"
    )

    ctx.add_shutdown_callback(end_session_hook)


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, worker_type=WorkerType.ROOM, shutdown_process_timeout=30))