from typing import List, Union
from fastapi import Depends, HTTPException, status

from api.core.dependencies import get_current_user
from api.models.models import User, UserRole


def require_role(*required_roles: Union[str, UserRole]):
    """
    Dependency that requires the current user to have one of the specified roles.
    
    Args:
        *required_roles: One or more roles that are allowed access
        
    Usage:
        @router.get("/admin", dependencies=[Depends(require_role("admin"))])
        @router.get("/users", dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.USER))])
    """
    # Convert all roles to lowercase strings for comparison
    role_strings = set()
    for role in required_roles:
        if isinstance(role, UserRole):
            role_strings.add(role.value.lower())
        else:
            role_strings.add(str(role).lower())
    
    def checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        # Get user's role as lowercase string for comparison
        user_role = current_user.role
        if isinstance(user_role, UserRole):
            user_role = user_role.value.lower()
        else:
            user_role = str(user_role).lower()
        
        if user_role not in role_strings:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {', '.join(role_strings)}",
            )
        
        return current_user

    return checker


def require_admin():
    """
    Shortcut dependency for admin-only endpoints.
    
    Usage:
        @router.get("/admin-only")
        def admin_endpoint(admin: User = Depends(require_admin)):
            ...
    """
    return require_role(UserRole.ADMIN)


def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Get the current user if they are an admin or super_admin, else raise 403.
    
    This is a direct dependency (not a factory) for simpler usage.
    """
    user_role = current_user.role
    if isinstance(user_role, UserRole):
        user_role = user_role.value.lower()
    else:
        user_role = str(user_role).lower()
    
    if user_role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    
    return current_user
