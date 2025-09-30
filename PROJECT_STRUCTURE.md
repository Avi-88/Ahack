# MindWave MVP - Project Structure Guide

## Root Files

### docker-compose.yml
- Docker Compose configuration for multi-container setup
- Should include services for backend and any required databases
- Configure port mappings and environment variables

### .env.example
- Template for environment variables
- Include API keys for OpenAI/Cerebras, database URLs, etc.
- Copy to .env for local development

### README.md
- Project overview and setup instructions
- Installation and running instructions
- API documentation links

## Backend Structure (/backend/)

### Main Files
- **Dockerfile**: Container configuration for Python FastAPI app
- **requirements.txt**: Python dependencies (FastAPI, OpenAI, speech libraries)
- **main.py**: FastAPI application entry point with WebSocket endpoint
- **config.py**: Environment variable loading and configuration management

### Services (/backend/services/)
- **transcription.py**: Speech-to-text service integration
- **llm_service.py**: Cerebras/OpenAI LLM API wrapper and conversation logic
- **tts_service.py**: Text-to-speech service for audio responses
- **conversation_handler.py**: Orchestrates the full conversation flow (audio → text → LLM → audio)

### Models (/backend/models/)
- **messages.py**: Pydantic models for WebSocket message schemas and data validation

### Utils (/backend/utils/)
- **audio.py**: Audio format conversion and processing helpers
- **logger.py**: Centralized logging configuration

## Frontend Structure (/frontend/)

### Files
- **index.html**: Simple web interface with audio recording controls
- **app.js**: WebSocket client, audio recording/playback, UI interactions
- **styles.css**: Basic styling for the web interface

## Test Audio (/test_audio/)
- **sample.wav**: Test audio file for debugging transcription services

## Development Workflow
1. Set up environment variables in .env
2. Run with docker-compose or locally with uvicorn
3. Open frontend in browser to test WebSocket connection
4. Use test audio files to verify the full pipeline