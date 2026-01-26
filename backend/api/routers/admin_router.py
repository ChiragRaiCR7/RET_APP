from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from api.core.rbac import require_role
from api.core.database import get_db
from api.core.dependencies import get_current_user
from api.schemas.admin import (
    UserCreateRequest,
    UserUpdateRequest,
    UserInfo,
    AuditLogEntry,
)
from api.services.admin_service import (
    create_user,
    update_user,
    get_user,
    delete_user,
    list_users,
    list_audit_logs,
    list_ops_logs,
    force_logout_user,
    get_admin_stats,
    update_user_role,
    unlock_user_account,
    generate_reset_token,
    list_reset_requests,
    list_sessions,
    cleanup_old_sessions,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ============================================================
# STATS ENDPOINTS
# ============================================================
@router.get("/stats")
def stats_ep(
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Get admin dashboard statistics"""
    return get_admin_stats(db)


# ============================================================
# USER MANAGEMENT ENDPOINTS
# ============================================================
@router.post("/users", response_model=UserInfo)
def create_user_ep(
    req: UserCreateRequest,
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Create new user"""
    user = create_user(db, req.username, req.password, req.role or "user")
    return user


@router.get("/users", response_model=list[UserInfo])
def list_users_ep(
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """List all users"""
    return list_users(db)


@router.get("/users/{user_id}", response_model=UserInfo)
def get_user_ep(
    user_id: int,
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Get user details"""
    return get_user(db, user_id)


@router.put("/users/{user_id}", response_model=UserInfo)
def update_user_ep(
    user_id: int,
    req: UserUpdateRequest,
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Update user fields"""
    return update_user(db, user_id, **req.dict(exclude_unset=True))


@router.put("/users/{user_id}/role", response_model=UserInfo)
def update_user_role_ep(
    user_id: int,
    body: dict,
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Update user role"""
    if "role" not in body:
        raise HTTPException(status_code=400, detail="Missing 'role' field")
    return update_user_role(db, user_id, body["role"])


@router.delete("/users/{user_id}")
def delete_user_ep(
    user_id: int,
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Delete user and all associated data"""
    force_logout_user(db, user_id)
    delete_user(db, user_id)
    return {"success": True}


# ============================================================
# PASSWORD RESET ENDPOINTS
# ============================================================
@router.get("/reset-requests")
def reset_requests_ep(
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """List password reset requests"""
    return list_reset_requests(db)


@router.post("/users/{user_id}/reset-token")
def generate_reset_token_ep(
    user_id: int,
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Generate password reset token for user"""
    token = generate_reset_token(db, user_id)
    return {"token": token}


@router.post("/users/{user_id}/unlock")
def unlock_account_ep(
    user_id: int,
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Unlock user account"""
    user = unlock_user_account(db, user_id)
    return user


# ============================================================
# SESSION MANAGEMENT ENDPOINTS
# ============================================================
@router.get("/sessions")
def sessions_ep(
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """List all active sessions"""
    return list_sessions(db)


@router.post("/sessions/cleanup")
def cleanup_sessions_ep(
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Clean up old sessions (older than 24 hours)"""
    deleted = cleanup_old_sessions(db, hours=24)
    return {"deleted": deleted}


# ============================================================
# AUDIT LOG ENDPOINTS
# ============================================================
@router.get("/audit-logs", response_model=list[AuditLogEntry])
def audit_logs_ep(
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """List audit logs"""
    return list_audit_logs(db)


@router.get("/ops-logs")
def ops_logs_ep(
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """List operational logs"""
    return list_ops_logs(db)
