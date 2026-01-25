from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from api.core.database import get_db
from api.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
    TokenResponse,
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


@router.post("/refresh")
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
