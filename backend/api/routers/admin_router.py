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
    AgentRequest,
    AgentResponse,
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
    get_ai_indexing_config_data,
    save_ai_indexing_config_data,
    get_user_by_username,
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
@router.post("/users")
def create_user_ep(
    req: UserCreateRequest,
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Create new user with token-first onboarding support"""
    user, token = create_user(
        db, 
        req.username, 
        password=req.password,  # None for token-first
        role=req.role or "user", 
        admin_username=admin_user.username,
        token_ttl_minutes=req.tokenTTL or 60,
    )
    
    # Build response
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": getattr(user, 'is_active', True),
        "is_locked": getattr(user, 'is_locked', False),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "token": token,  # Only provided for token-first onboarding
    }


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
    return update_user(
        db, 
        user_id, 
        req.dict(exclude_unset=True), 
        admin_username=admin_user.username
    )


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
    return update_user_role(
        db, 
        user_id, 
        body["role"], 
        admin_username=admin_user.username
    )


@router.delete("/users/{user_id}")
def delete_user_ep(
    user_id: int,
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Delete user and all associated data"""
    force_logout_user(db, user_id, admin_username=admin_user.username)
    delete_user(db, user_id, admin_username=admin_user.username)
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
    token = generate_reset_token(db, user_id, admin_username=admin_user.username)
    return {"token": token}


@router.post("/users/{user_id}/unlock")
def unlock_account_ep(
    user_id: int,
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Unlock user account"""
    user = unlock_user_account(db, user_id, admin_username=admin_user.username)
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
    deleted = cleanup_old_sessions(db, hours=24, admin_username=admin_user.username)
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


# ============================================================
# AI INDEXING CONFIGURATION
# ============================================================
@router.post("/ai-indexing-config")
def save_ai_indexing_config(
    body: dict,
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Save AI indexing configuration"""
    success = save_ai_indexing_config_data(body)
    return {
        "success": success,
        "message": "AI indexing configuration saved" if success else "Failed to save configuration",
        "config": body,
    }


@router.get("/ai-indexing-config")
def get_ai_indexing_config(
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Get AI indexing configuration"""
    return get_ai_indexing_config_data()


# ============================================================
# ADMIN AI AGENT & TOOLS
# ============================================================
@router.post("/agent", response_model=AgentResponse)
def admin_agent_ep(
    req: AgentRequest,
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """
    Execute admin commands via natural language (Enhanced Tool-Use)
    """
    command = req.command.strip().lower()
    
    # --- TOOL: Create User ---
    # Syntax: "create user <username> <password> [role]"
    if command.startswith("create user"):
        parts = command.split()
        if len(parts) < 4:
            return AgentResponse(result="Usage: <code>create user &lt;username&gt; &lt;password&gt; [role]</code>")
        
        username = parts[2]
        password = parts[3]
        role = parts[4] if len(parts) > 4 else "user"
        
        try:
            create_user(db, username, password, role, admin_username=admin_user.username)
            return AgentResponse(result=f"✅ User <b>{username}</b> created successfully with role <code>{role}</code>.")
        except Exception as e:
            return AgentResponse(result=f"❌ Failed to create user: {str(e)}")

    # --- TOOL: Reset Password (Generate Token) ---
    # Syntax: "reset password <username>" or "reset token <username>"
    if command.startswith("reset password") or command.startswith("reset token"):
        parts = command.split()
        if len(parts) < 3:
            return AgentResponse(result="Usage: <code>reset password &lt;username&gt;</code>")
        
        target_user = parts[2]
        user = get_user_by_username(db, target_user)
        if not user:
            return AgentResponse(result=f"❌ User <b>{target_user}</b> not found.")
        
        try:
            token = generate_reset_token(db, user.id, admin_username=admin_user.username)
            return AgentResponse(result=f"✅ Reset token for <b>{target_user}</b>:<br><br><pre>{token}</pre>")
        except Exception as e:
            return AgentResponse(result=f"❌ Failed to generate token: {str(e)}")

    # --- TOOL: Unlock User ---
    # Syntax: "unlock user <username>"
    if command.startswith("unlock user") or command.startswith("unlock account"):
        parts = command.split()
        if len(parts) < 3:
            return AgentResponse(result="Usage: <code>unlock user &lt;username&gt;</code>")
            
        target_user = parts[2]
        user = get_user_by_username(db, target_user)
        if not user:
            return AgentResponse(result=f"❌ User <b>{target_user}</b> not found.")
            
        try:
            unlock_user_account(db, user.id, admin_username=admin_user.username)
            return AgentResponse(result=f"✅ Account for <b>{target_user}</b> unlocked.")
        except Exception as e:
            return AgentResponse(result=f"❌ Failed to unlock: {str(e)}")

    # --- TOOL: Cleanup Sessions ---
    if "cleanup sessions" in command or "clean sessions" in command:
        try:
            count = cleanup_old_sessions(db, hours=24, admin_username=admin_user.username)
            return AgentResponse(result=f"✅ Cleanup complete. Removed <b>{count}</b> old sessions.")
        except Exception as e:
            return AgentResponse(result=f"❌ Cleanup failed: {str(e)}")

    # --- INFO: Users ---
    if "users" in command or "list user" in command:
        users = list_users(db)
        items = "".join([f"<li>{u.username} ({u.role})</li>" for u in users[:10]])
        if len(users) > 10:
            items += f"<li>...and {len(users)-10} more.</li>"
        return AgentResponse(result=f"Here are the users:<ul style='margin-top:8px'>{items}</ul>")
    
    # --- INFO: Stats ---
    if "stats" in command or "status" in command:
        stats = get_admin_stats(db)
        res = (
            f"<b>System Status</b>:<br>"
            f"<ul>"
            f"<li>Users: {stats['totalUsers']}</li>"
            f"<li>Active Sessions: {stats['activeSessions']}</li>"
            f"</ul>"
        )
        return AgentResponse(result=res)

    # --- INFO: Audit Logs ---
    if "audit" in command or "log" in command:
        logs = list_audit_logs(db, limit=5)
        items = "".join([f"<li>{l.created_at.strftime('%H:%M:%S')} [{l.username}] {l.action}</li>" for l in logs])
        return AgentResponse(result=f"Recent Audit Logs:<br><ul style='margin-top:8px'>{items}</ul>")

    return AgentResponse(result=f"""I didn't understand the command: '<code>{req.command}</code>'.<br><br>
    
<b>Available Tools:</b>
<ul>
<li><code>create user &lt;name&gt; &lt;pass&gt; [role]</code></li>
<li><code>reset password &lt;name&gt;</code></li>
<li><code>unlock user &lt;name&gt;</code></li>
<li><code>cleanup sessions</code></li>
<li><code>stats</code>, <code>users</code>, <code>audit logs</code></li>
</ul>
""")
