from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client
import jwt
import os
from typing import Optional
from pydantic import BaseModel

# Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

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
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed: {str(e)}"
        )

async def get_optional_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[User]:
    """
    Optional authentication - returns None if no valid token
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None