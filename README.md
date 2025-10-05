# Miso Backend Server

A FastAPI-based backend server for the Miso therapy application with AI agent integration.

## Prerequisites

- Python 3.8+
- [uv](https://github.com/astral-sh/uv) package manager
- PostgreSQL database
- Supabase account
- LiveKit server
- Cerebras API key

## Environment Setup

1. **Clone the repository and navigate to the backend directory:**
   ```bash
   cd miso
   ```

2. **Install dependencies using uv:**
   ```bash
   uv sync
   ```

3. **Create a `.env` file with the following variables:**
   ```env
   # Database
   DATABASE_URL="postgresql://username:password@localhost:5432/miso_db"
   
   # Supabase
   SUPABASE_URL="your-supabase-url"
   SUPABASE_KEY="your-supabase-anon-key"
   
   # LiveKit
   LIVEKIT_API_KEY="your-livekit-api-key"
   LIVEKIT_API_SECRET="your-livekit-api-secret"
   LIVEKIT_URL="wss://your-livekit-server.livekit.cloud"
   
   # Cerebras AI
   CEREBRAS_API_KEY="your-cerebras-api-key"
   
   # Optional: Port (defaults to 8000)
   PORT=8000
   ```

## Database Setup

1. **Generate Prisma client:**
   ```bash
   uv run python -m prisma generate
   ```

2. **Run database migrations:**
   ```bash
   uv run python -m prisma migrate deploy
   ```

3. **Optional: Reset database (development only):**
   ```bash
   uv run python -m prisma migrate reset
   ```

## Running the Server

### Development Mode
```bash
uv run python main.py
```

### Production Mode
```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

The server will be available at `http://localhost:8000`

### API Documentation
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## AI Agent Setup

The AI agent is located in the `agents/miso-agent/` directory.

### Agent Dependencies
```bash
cd agents/miso-agent
uv sync
```

### Agent Environment Variables
Create a `.env` file in `agents/miso-agent/`:
```env
LIVEKIT_URL="wss://your-livekit-server.livekit.cloud"
LIVEKIT_API_KEY="your-livekit-api-key"
LIVEKIT_API_SECRET="your-livekit-api-secret"
CEREBRAS_API_KEY="your-cerebras-api-key"
```

### Running the Agent
```bash
cd agents/miso-agent
uv run python agent.py dev
```

## API Endpoints

### Authentication
- `POST /auth/signin` - User sign in
- `POST /auth/signup` - User registration
- `POST /auth/refresh` - Refresh access token
- `POST /auth/logout` - User logout

### Sessions
- `POST /create-session` - Create new therapy session
- `POST /resume-session` - Resume existing session
- `GET /sessions` - Get user's sessions
- `GET /session/{session_id}` - Get session details
- `DELETE /session/{session_id}` - Delete session

### Health Check
- `GET /health` - Server health status

## Deployment

### Using Render

1. **Build Command:**
   ```bash
   uv run python -m prisma generate
   ```

2. **Start Command:**
   ```bash
   uv run python main.py
   ```

3. **Environment Variables:**
   Set all required environment variables in Render dashboard

### Using Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install uv
RUN uv sync

RUN uv run python -m prisma generate

EXPOSE 8000

CMD ["uv", "run", "python", "main.py"]
```

## Development

### Database Schema Changes
1. Modify `prisma/schema.prisma`
2. Create migration:
   ```bash
   uv run python -m prisma migrate dev --name your_migration_name
   ```
3. Generate client:
   ```bash
   uv run python -m prisma generate
   ```

### Adding Dependencies
```bash
uv add package-name
```

### Running Tests
```bash
uv run pytest
```

## Troubleshooting

### Common Issues

1. **Prisma Client Error:**
   ```bash
   uv run python -m prisma generate
   ```

2. **Database Connection Issues:**
   - Verify DATABASE_URL in .env
   - Ensure PostgreSQL is running
   - Check database permissions

3. **LiveKit Connection Issues:**
   - Verify LIVEKIT_URL, API_KEY, and API_SECRET
   - Ensure LiveKit server is accessible

4. **Agent Not Connecting:**
   - Check agent .env file
   - Verify agent is running: `cd agents/miso-agent && uv run python agent.py dev`
   - Check LiveKit dashboard for agent status

### Logs
Server logs are output to console. For production, consider using a logging service.

## Project Structure

```
miso/
├── main.py              # FastAPI application
├── auth.py              # Authentication logic
├── database.py          # Database connection
├── prisma/
│   └── schema.prisma    # Database schema
├── agents/
│   └── miso-agent/      # AI agent code
├── .env                 # Environment variables
├── pyproject.toml       # Project dependencies
└── README.md           # This file
```

## Support

For issues and questions, please check the troubleshooting section above or create an issue in the project repository.