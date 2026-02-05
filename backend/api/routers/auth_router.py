from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from sqlalchemy.orm import Session
import logging

from api.core.database import get_db
from api.core.dependencies import get_current_user
from api.core.session_cache import get_session_cache, clear_cache_pattern
from api.models.models import User
from api.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
    TokenResponse,
    RefreshTokenResponse,
    UserInfo,
)
from api.services.auth_service import (
    authenticate_user,
    issue_tokens,
    refresh_tokens,
    request_password_reset,
    confirm_password_reset,
)
from api.services.session_service import revoke_refresh_token
from api.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, req.username, req.password)
    tokens = issue_tokens(db, user, request)
    
    # Set refresh token as HttpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=tokens["refresh_token"],
        httponly=True,
        secure=settings.ENV == "production",
        samesite="lax",
        max_age=7 * 24 * 60 * 60,  # 7 days
    )
    
    # Remove refresh_token from response body (it's in cookie)
    tokens_response = TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_type=tokens["token_type"],
        user=tokens["user"],
    )
    return tokens_response


@router.get("/me", response_model=UserInfo)
def get_me(
    current_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == int(current_user_id)).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    current_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Logout endpoint with comprehensive cleanup
    
    Cleans up:
    - Database session records
    - Session directories (XML, CSV, extracted files)
    - ChromaDB vector indices (Advanced RAG)
    - AI session managers
    - Cache entries
    """
    from api.services.storage_service import cleanup_user_sessions
    from api.services.ai.session_manager import cleanup_session_ai
    
    logger.info(f"User logout initiated: {current_user_id}")
    
    try:
        # Revoke refresh token from database
        refresh_token = request.cookies.get("refresh_token")
        if refresh_token:
            revoke_refresh_token(db, refresh_token)
            logger.debug(f"Revoked refresh token for user: {current_user_id}")
    except Exception as e:
        logger.error(f"Failed to revoke refresh token: {e}")
    
    try:
        # Clean up AI session managers and their ChromaDB indices
        # This is important for session-isolated vector stores
        # Note: cleanup_user_sessions below will also clean directories,
        # but we call this first to properly shutdown AI resources
        from api.services.storage_service import get_user_sessions
        
        user_sessions = get_user_sessions(current_user_id)
        for session_info in user_sessions:
            session_id = session_info.get("session_id", "")
            if session_id:
                try:
                    cleanup_session_ai(session_id, current_user_id)
                    logger.debug(f"Cleaned up AI resources for session: {session_id}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup AI for session {session_id}: {e}")
        
        logger.info(f"Cleaned up AI sessions for user: {current_user_id}")
    except Exception as e:
        logger.error(f"Failed to cleanup AI sessions: {e}")
    
    try:
        # Clean up all user sessions and their data
        # This removes:
        # - Session directories with XML/CSV files
        # - Extracted content
        # - Remaining ChromaDB files
        cleanup_user_sessions(current_user_id)
        logger.info(f"Cleaned up all sessions for user: {current_user_id}")
    except Exception as e:
        logger.error(f"Failed to cleanup sessions: {e}")
    
    try:
        # Clear cache entries for this user
        cache = get_session_cache()
        cleared = clear_cache_pattern(f"user:{current_user_id}:")
        logger.debug(f"Cleared {cleared} cache entries for user: {current_user_id}")
    except Exception as e:
        logger.debug(f"Cache cleanup failed: {e}")

    # Delete refresh token cookie
    response.delete_cookie(
        key="refresh_token",
        secure=settings.ENV == "production",
    )

    logger.info(f"User logout completed: {current_user_id}")
    return {"success": True, "message": "Logged out successfully"}


@router.post("/refresh", response_model=RefreshTokenResponse)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    # Get refresh token from HttpOnly cookie
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")
    
    tokens = refresh_tokens(db, refresh_token)
    
    # Update refresh token cookie if a new one was issued
    if "refresh_token" in tokens:
        response.set_cookie(
            key="refresh_token",
            value=tokens["refresh_token"],
            httponly=True,
            secure=settings.ENV == "production",
            samesite="lax",
            max_age=7 * 24 * 60 * 60,
        )
    
    return RefreshTokenResponse(
        access_token=tokens["access_token"],
        token_type=tokens["token_type"],
    )


@router.post("/password-reset/request")
def password_reset_request(req: PasswordResetRequest, db: Session = Depends(get_db)):
    request_password_reset(db, req.username, req.reason)
    # Always return success to avoid user enumeration
    return {"success": True, "message": "If account exists, reset email will be sent"}


@router.post("/password-reset/confirm")
def password_reset_confirm(req: PasswordResetConfirm, db: Session = Depends(get_db)):
    confirm_password_reset(db, req.token, req.new_password)
    return {"success": True}
