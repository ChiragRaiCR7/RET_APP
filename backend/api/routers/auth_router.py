from fastapi import APIRouter, Depends, Request
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

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    req: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, req.username, req.password)
    tokens = issue_tokens(db, user, request)
    return tokens


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
    current_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # In a real app, you would invalidate the session in the DB
    return {"success": True}


@router.post("/refresh", response_model=RefreshTokenResponse)
def refresh(req: RefreshRequest, db: Session = Depends(get_db)):
    return refresh_tokens(db, req.refresh_token)


@router.post("/password-reset/request")
def password_reset_request(req: PasswordResetRequest, db: Session = Depends(get_db)):
    request_password_reset(db, req.username)
    return {"success": True}


@router.post("/password-reset/confirm")
def password_reset_confirm(req: PasswordResetConfirm, db: Session = Depends(get_db)):
    confirm_password_reset(db, req.token, req.new_password)
    return {"success": True}
