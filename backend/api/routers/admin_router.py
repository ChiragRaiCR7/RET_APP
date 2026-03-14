from __future__ import annotations

import shlex

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from api.core.config import settings
from api.core.rbac import require_role
from api.core.database import get_db
from api.schemas.admin import (
    UserCreateRequest,
    UserUpdateRequest,
    UserInfo,
    AuditLogEntry,
    AgentRequest,
    AgentResponse,
)
from api.schemas.common import MessageResponse
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
from api.services.ai.async_azure_openai_service import (
    generate_admin_agent_reply,
    is_async_azure_chat_configured,
)

router = APIRouter(prefix="/admin", tags=["admin"])


# ============================================================
# STATS ENDPOINTS
# ============================================================
@router.get("/stats")
async def stats_ep(
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Get admin dashboard statistics"""
    return await get_admin_stats(db)


# ============================================================
# USER MANAGEMENT ENDPOINTS
# ============================================================
@router.post("/users")
async def create_user_ep(
    req: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Create new user with token-first onboarding support"""
    user, token = await create_user(
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
async def list_users_ep(
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """List all users"""
    return await list_users(db)


@router.get("/users/{user_id}", response_model=UserInfo)
async def get_user_ep(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Get user details"""
    return await get_user(db, user_id)


@router.put("/users/{user_id}", response_model=UserInfo)
async def update_user_ep(
    user_id: int,
    req: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Update user fields"""
    updates = req.model_dump(exclude_unset=True) if hasattr(req, "model_dump") else req.dict(exclude_unset=True)
    return await update_user(
        db, 
        user_id, 
        updates, 
        admin_username=admin_user.username
    )


@router.put("/users/{user_id}/role", response_model=UserInfo)
async def update_user_role_ep(
    user_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Update user role"""
    if "role" not in body:
        raise HTTPException(status_code=400, detail="Missing 'role' field")
    return await update_user_role(
        db, 
        user_id, 
        body["role"], 
        admin_username=admin_user.username
    )


@router.delete("/users/{user_id}", response_model=MessageResponse)
async def delete_user_ep(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Delete user and all associated data"""
    await force_logout_user(db, user_id, admin_username=admin_user.username)
    await delete_user(db, user_id, admin_username=admin_user.username)
    return {"success": True, "message": "User deleted"}


# ============================================================
# PASSWORD RESET ENDPOINTS
# ============================================================
@router.get("/reset-requests")
async def reset_requests_ep(
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """List password reset requests"""
    return await list_reset_requests(db)


@router.post("/users/{user_id}/reset-token")
async def generate_reset_token_ep(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Generate password reset token for user"""
    token = await generate_reset_token(db, user_id, admin_username=admin_user.username)
    return {"token": token}


@router.post("/users/{user_id}/unlock")
async def unlock_account_ep(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Unlock user account"""
    user = await unlock_user_account(db, user_id, admin_username=admin_user.username)
    return user


# ============================================================
# SESSION MANAGEMENT ENDPOINTS
# ============================================================
@router.get("/sessions")
async def sessions_ep(
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """List all active sessions"""
    return await list_sessions(db)


@router.post("/sessions/cleanup", response_model=MessageResponse)
async def cleanup_sessions_ep(
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Clean up old sessions (older than 24 hours)"""
    deleted = await cleanup_old_sessions(db, hours=24, admin_username=admin_user.username)
    return {"success": True, "message": f"Cleaned up {deleted} old sessions"}


# ============================================================
# AUDIT LOG ENDPOINTS
# ============================================================
@router.get("/audit-logs", response_model=list[AuditLogEntry])
async def audit_logs_ep(
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """List audit logs"""
    return await list_audit_logs(db)


@router.get("/ops-logs")
async def ops_logs_ep(
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """List operational logs"""
    return await list_ops_logs(db)


# ============================================================
# AI INDEXING CONFIGURATION
# ============================================================
@router.post("/ai-indexing-config")
async def save_ai_indexing_config(
    body: dict,
    db: AsyncSession = Depends(get_db),
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
async def get_ai_indexing_config(
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """Get AI indexing configuration (includes read-only feature flags)."""
    data = get_ai_indexing_config_data()
    # Expose read-only feature flags so the admin UI can display status
    data["hitl_enabled"] = getattr(settings, "FEATURE_HITL_ENABLED", False)
    data["hitl_confidence_threshold"] = getattr(
        settings, "RAG_HITL_CONFIDENCE_THRESHOLD", 0.35
    )
    return data


# ============================================================
# ADMIN AI AGENT & TOOLS
# ============================================================
@router.post("/agent", response_model=AgentResponse)
async def admin_agent_ep(
    req: AgentRequest,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(require_role("admin")),
):
    """
    Execute admin commands via natural language (Enhanced Tool-Use)
    """
    # Keep original text for LLM fallback; use lowered for routing
    raw_command = (req.command or "").strip()
    command = raw_command.lower()

    # Helper: robust tokenization (supports quotes, escaped spaces)
    def split_words(cmd: str) -> list[str]:
        try:
            return shlex.split(cmd)
        except Exception:
            return cmd.split()

    # --- TOOL: Create User ---
    # Syntax: "create user <username> <password> [role]"
    if command.startswith("create user"):
        parts = split_words(raw_command)  # use raw for correct casing if needed
        if len(parts) < 4:
            return AgentResponse(
                result="Usage: `create user <username> <password> [role]`",
                format="markdown",
            )

        # parts[0]='create', parts[1]='user', parts[2]=username, parts[3]=password
        username = parts[2]
        password = parts[3]
        role = parts[4] if len(parts) > 4 else "user"

        try:
            await create_user(db, username, password, role, admin_username=admin_user.username)
            return AgentResponse(
                result=f"✅ User **{username}** created with role `{role}`.",
                format="markdown",
                details={"username": username, "role": role},
            )
        except Exception as e:
            return AgentResponse(result=f"❌ Failed to create user: {str(e)}", format="markdown")

    # --- TOOL: Reset Password (Generate Token) ---
    # Syntax: "reset password <username>" or "reset token <username>"
    if command.startswith("reset password") or command.startswith("reset token"):
        parts = split_words(raw_command)
        if len(parts) < 3:
            return AgentResponse(result="Usage: `reset password <username>`", format="markdown")

        target_user = parts[2]
        user = await get_user_by_username(db, target_user)
        if not user:
            return AgentResponse(result=f"❌ User **{target_user}** not found.", format="markdown")

        try:
            token = await generate_reset_token(db, user.id, admin_username=admin_user.username)
            return AgentResponse(
                result=f"**Reset token for `{target_user}`**\n\n```\n{token}\n```",
                format="markdown",
                details={"username": target_user},
            )
        except Exception as e:
            return AgentResponse(result=f"❌ Failed to generate token: {str(e)}", format="markdown")

    # --- TOOL: Unlock User ---
    # Syntax: "unlock user <username>"
    if command.startswith("unlock user") or command.startswith("unlock account"):
        parts = split_words(raw_command)
        if len(parts) < 3:
            return AgentResponse(result="Usage: `unlock user <username>`", format="markdown")

        target_user = parts[2]
        user = await get_user_by_username(db, target_user)
        if not user:
            return AgentResponse(result=f"❌ User **{target_user}** not found.", format="markdown")

        try:
            await unlock_user_account(db, user.id, admin_username=admin_user.username)
            return AgentResponse(result=f"✅ Account for **{target_user}** unlocked.", format="markdown")
        except Exception as e:
            return AgentResponse(result=f"❌ Failed to unlock: {str(e)}", format="markdown")

    # --- TOOL: Cleanup Sessions ---
    if "cleanup sessions" in command or "clean sessions" in command:
        try:
            # keep default 24h as before
            count = await cleanup_old_sessions(db, hours=24, admin_username=admin_user.username)
            return AgentResponse(
                result=f"✅ Cleanup complete. Removed **{count}** old sessions.",
                format="markdown",
                details={"deleted": count, "hours": 24},
            )
        except Exception as e:
            return AgentResponse(result=f"❌ Cleanup failed: {str(e)}", format="markdown")

    # --- INFO: Users ---
    if "users" in command or "list user" in command:
        users = await list_users(db)
        lines = [f"- {u.username} ({u.role})" for u in users[:10]]
        if len(users) > 10:
            lines.append(f"- …and {len(users)-10} more.")
        return AgentResponse(
            result="**Users**\n\n" + "\n".join(lines),
            format="markdown",
            details={"count": len(users)},
        )

    # --- INFO: Stats ---
    if "stats" in command or "status" in command:
        stats = await get_admin_stats(db)
        md = (
            f"**System Status**\n\n"
            f"- Users: {stats['totalUsers']}\n"
            f"- Active Sessions: {stats['activeSessions']}\n"
        )
        return AgentResponse(result=md, format="markdown", details=stats)

    # --- INFO: Audit Logs ---
    if "audit" in command or "log" in command:
        logs = await list_audit_logs(db, limit=5)
        # keep markdown; concise bullets
        lines = [f"- {l.created_at.strftime('%H:%M:%S')} [{l.username}] {l.action}" for l in logs]
        return AgentResponse(
            result="**Recent Audit Logs**\n\n" + "\n".join(lines),
            format="markdown",
            details={"count": len(lines)},
        )

    # --- INFO: Help ---
    if command in ("help", "?", "commands", "tools"):
        return AgentResponse(
            result=(
                "**Available Admin Commands:**\n\n"
                "- `create user <name> <pass> [role]` — Create a new user\n"
                "- `reset password <name>` — Generate a password reset token\n"
                "- `unlock user <name>` — Unlock a locked account\n"
                "- `cleanup sessions` — Remove sessions older than 24h\n"
                "- `users` / `list users` — List all users\n"
                "- `stats` / `status` — System statistics\n"
                "- `audit` / `logs` — Recent audit logs\n\n"
                "For anything else, just ask in natural language."
            ),
            format="markdown",
        )

    # Optional LLM fallback (unchanged)
    if is_async_azure_chat_configured():
        try:
            ai_result = await generate_admin_agent_reply(req.command, admin_user.username)
            if ai_result:
                # If your LLM returns Markdown, you can set format='markdown' here.
                return AgentResponse(result=ai_result, format="markdown")
        except Exception:
            # Fall back to static help to keep the endpoint resilient
            pass

    # Default: didn’t understand
    return AgentResponse(
        result=(
            f"I didn't understand the command: `{raw_command}`.\n\n"
            "**Available Tools:**\n"
            "- `create user <name> <pass> [role]`\n"
            "- `reset password <name>`\n"
            "- `unlock user <name>`\n"
            "- `cleanup sessions`\n"
            "- `stats`, `users`, `audit logs`\n"
        ),
        format="markdown",
    )

