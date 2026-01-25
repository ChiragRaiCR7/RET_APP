from fastapi import APIRouter, Depends
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
    delete_user,
    list_users,
    list_audit_logs,
    list_ops_logs,
    force_logout_user,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(user=Depends(get_current_user)):
    # user is subject (user_id) from JWT
    # role check added in Phase 8 middleware
    return user


@router.post("/users", response_model=UserInfo)
def create_user_ep(
    req: UserCreateRequest,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
    admin=Depends(require_role("admin")),
):
    return create_user(db, req.username, req.password, req.role)


@router.get("/users", response_model=list[UserInfo])
def list_users_ep(
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    return list_users(db)


@router.put("/users/{user_id}")
def update_user_ep(
    user_id: int,
    req: UserUpdateRequest,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    return update_user(db, user_id, **req.dict())


@router.delete("/users/{user_id}")
def delete_user_ep(
    user_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    force_logout_user(db, user_id)
    delete_user(db, user_id)
    return {"success": True}


@router.get("/audit-logs", response_model=list[AuditLogEntry])
def audit_logs_ep(
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    return list_audit_logs(db)


@router.get("/ops-logs")
def ops_logs_ep(
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    return list_ops_logs(db)
