
from __future__ import annotations

import logging
from typing import List, Union
from fastapi import Depends, HTTPException, status

from api.core.dependencies import get_current_user
from api.models.models import User, UserRole

logger = logging.getLogger(__name__)


def _normalize_role(role: Union[str, UserRole]) -> str:
    """Return the canonical lowercase string for *role*."""
    if isinstance(role, UserRole):
        return role.value.lower()
    return str(role).lower()


def require_role(*required_roles: Union[str, UserRole]):
    """
    Dependency factory that requires the current user to hold one of
    *required_roles*.  Logs and raises 403 on access denial.

    Usage::

        @router.get("/admin", dependencies=[Depends(require_role("admin"))])
        @router.get("/users", dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.USER))])
    """
    role_strings = {_normalize_role(r) for r in required_roles}

    def checker(current_user: User = Depends(get_current_user)) -> User:
        user_role = _normalize_role(current_user.role)
        if user_role not in role_strings:
            logger.warning(
                "Access denied",
                extra={
                    "extra_fields": {
                        "user_id": current_user.id,
                        "user_role": user_role,
                        "required_roles": sorted(role_strings),
                    }
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {', '.join(sorted(role_strings))}",
            )
        return current_user

    return checker


def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Direct dependency: return *current_user* if they are admin or super_admin,
    else raise 403.  Prefer this over ``require_admin()`` for new endpoints.

    Usage::

        @router.get("/admin-only")
        def admin_endpoint(admin: User = Depends(get_admin_user)):
            ...
    """
    if _normalize_role(current_user.role) not in {"admin", "super_admin"}:
        logger.warning(
            "Admin access denied",
            extra={"extra_fields": {"user_id": current_user.id, "role": _normalize_role(current_user.role)}},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def require_admin():
    """
    Deprecated factory — kept for backward compatibility.
    Prefer ``Depends(get_admin_user)`` directly in new code.
    """
    return require_role(UserRole.ADMIN, "super_admin")


def require_roles(roles: List[Union[str, UserRole]]):
    """Convenience wrapper that accepts a list instead of variadic args."""
    return require_role(*roles)