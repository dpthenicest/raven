from datetime import datetime
from typing import Optional

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import User


GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


async def exchange_google_code(code: str) -> dict:
    logger.info("Exchanging Google OAuth code for user info")
    async with httpx.AsyncClient() as client:
        resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        resp.raise_for_status()
        tokens = resp.json()

        user_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        user_resp.raise_for_status()
        google_user = user_resp.json()
        logger.info(f"Google user info retrieved: {google_user.get('email')}")
        return google_user


async def get_or_create_user(db: AsyncSession, google_user: dict) -> User:
    result = await db.execute(select(User).where(User.oauth_id == google_user["id"]))
    user = result.scalar_one_or_none()

    if not user:
        logger.info(f"Creating new user: {google_user['email']}")
        user = User(
            email=google_user["email"],
            oauth_id=google_user["id"],
            name=google_user.get("name"),
            credits=1,
        )
        db.add(user)
    else:
        logger.info(f"Existing user logged in: {google_user['email']}")

    user.last_login_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)
    return user


async def get_current_user(db: AsyncSession, user_id: str) -> Optional[User]:
    logger.debug(f"Fetching user by id: {user_id}")
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
