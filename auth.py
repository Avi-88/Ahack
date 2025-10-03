from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client
import jwt
import os
from typing import Optional
from pydantic import BaseModel
import logging
from dotenv import load_dotenv


load_dotenv(".env")

# Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)
logger = logging.getLogger(__name__)

security = HTTPBearer()

class User(BaseModel):
    id: str
    email: str
    name: Optional[str] = None
    avatar_url: Optional[str] = None

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """
    Extract user from Supabase JWT token
    """
    try:
        token = credentials.credentials
        
        # Verify token with Supabase
        response = supabase.auth.get_user(token)
        
        if not response.user:
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication token"
            )
        
        user_data = response.user
        
        # Create user object
        user = User(
            id=user_data.id,
            email=user_data.email,
            name=user_data.user_metadata.get('name', user_data.email.split('@')[0]),
            avatar_url=user_data.user_metadata.get('avatar_url')
        )
        
        return user
        
    except Exception as e:
        logger.error("Failed to get current user")
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed: {str(e)}"
        )

