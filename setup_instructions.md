# Miso Therapy App Setup Instructions

## 1. Install Dependencies

```bash
pip install -r requirements.txt
```

## 2. Setup Supabase

1. Go to [supabase.com](https://supabase.com) and create a new project
2. Get your project URL and API keys from Settings > API
3. Copy `.env.example` to `.env` and fill in your Supabase credentials

## 3. Setup Database with Prisma

```bash
# Generate Prisma client
prisma generate

# Push schema to Supabase database  
prisma db push

# Optional: Create and apply migrations
prisma migrate dev --name init
```

## 4. Setup LiveKit

1. Go to [livekit.io](https://livekit.io) and create an account
2. Create a new project
3. Get your API key, secret, and project URL
4. Add them to your `.env` file

## 5. Enable Supabase Auth

In your Supabase dashboard:
1. Go to Authentication > Settings
2. Add your frontend URL to "Site URL" and "Redirect URLs"
3. Configure any auth providers you want (Google, GitHub, etc.)

## 6. Run the Application

```bash
# Start the FastAPI server
python main.py

# In another terminal, start your agent
python agents/Miso.py
```

## 7. Environment Variables

Make sure your `.env` file has:

```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Database (from Supabase Settings > Database)
DATABASE_URL="postgresql://postgres:password@db.your-project.supabase.co:5432/postgres"

# LiveKit
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret
LIVEKIT_URL=wss://your-project.livekit.cloud

# App
SECRET_KEY=your-random-secret-key
```

## 8. API Endpoints

- `POST /api/create-session` - Start new therapy session
- `POST /api/resume-session` - Resume existing conversation
- `GET /api/session-history` - Get user's session history

## 9. Frontend Integration

Your React app should:
1. Authenticate users with Supabase Auth
2. Call `/api/create-session` to start therapy
3. Use returned token to connect to LiveKit room
4. Use LiveKit React components for audio/video

## 10. Agent Integration

Your `Miso.py` agent will:
1. Automatically join rooms when users connect
2. Access conversation context from room metadata
3. Save messages back to the same database