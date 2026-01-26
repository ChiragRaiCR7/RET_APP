from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from api.core.database import get_db
from api.core.dependencies import get_current_user
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
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    current_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from api.services.storage_service import cleanup_user_sessions
    
    # Revoke refresh token from database
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        revoke_refresh_token(db, refresh_token)

    # Clean up all user sessions and their data
    try:
        cleanup_user_sessions(current_user_id)
    except Exception:
        pass  # Continue with logout even if cleanup fails

    response.delete_cookie(
        key="refresh_token",
        secure=settings.ENV == "production",
    )

    return {"success": True}


@router.post("/refresh", response_model=RefreshTokenResponse)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    # Get refresh token from HttpOnly cookie
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        from fastapi import HTTPException, status
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
    request_password_reset(db, req.username)
    # Always return success to avoid user enumeration
    return {"success": True, "message": "If account exists, reset email will be sent"}


@router.post("/password-reset/confirm")
def password_reset_confirm(req: PasswordResetConfirm, db: Session = Depends(get_db)):
    confirm_password_reset(db, req.token, req.new_password)
    return {"success": True}
