from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.schemas.user import TokenOut, UserOut
from app.services.auth import exchange_google_code, get_or_create_user
from app.api.deps import get_current_active_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_AUTH_URL = (
    "https://accounts.google.com/o/oauth2/v2/auth"
    "?response_type=code"
    "&scope=openid%20email%20profile"
    "&client_id={client_id}"
    "&redirect_uri={redirect_uri}"
)


@router.get("/login/google")
async def login_google():
    logger.info("Redirecting to Google OAuth login")
    url = GOOGLE_AUTH_URL.format(
        client_id=settings.GOOGLE_CLIENT_ID,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )
    return RedirectResponse(url)


@router.get("/callback", response_model=TokenOut)
async def auth_callback(code: str = Query(...), db: AsyncSession = Depends(get_db)):
    logger.info("Google OAuth callback received")
    try:
        google_user = await exchange_google_code(code)
    except Exception as e:
        logger.error(f"OAuth exchange failed: {e}")
        raise HTTPException(status_code=400, detail="OAuth exchange failed")

    user = await get_or_create_user(db, google_user)
    logger.info(f"User authenticated: {user.email}")
    token = create_access_token(str(user.id))
    return TokenOut(access_token=token)


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_active_user)):
    logger.debug(f"Fetching profile for user: {current_user.email}")
    return current_user
