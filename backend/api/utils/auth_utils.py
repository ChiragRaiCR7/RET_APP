"""
Authorization utilities for session and resource ownership checks.
"""
from fastapi import HTTPException, status
from typing import Optional, Union

from api.models.models import User
from api.services.storage_service import get_session_metadata


def verify_session_owner(
    session_id: str,
    current_user: Union[User, str, int],
    allow_admin: bool = True,
) -> None:
    """
    Verify that the current user owns the specified session.
    
    Raises HTTPException 403 if the user doesn't have access.
    
    Args:
        session_id: The session ID to check ownership of
        current_user: The current user (User object, user ID string, or int)
        allow_admin: If True, admins can access any session
        
    Raises:
        HTTPException: 403 if user doesn't own the session
        HTTPException: 404 if session doesn't exist
    """
    meta = get_session_metadata(session_id)
    
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    owner_id = meta.get("user_id")
    
    if owner_id is None:
        # Session has no owner - allow access
        return
    
    # Get the user ID for comparison
    if isinstance(current_user, User):
        user_id = str(current_user.id)
        is_admin = _is_admin(current_user)
    else:
        user_id = str(current_user)
        is_admin = False  # Can't determine admin status from just ID
    
    # Check if user is admin and admin access is allowed
    if allow_admin and is_admin:
        return
    
    # Check ownership
    if str(owner_id) != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this session",
        )


def require_session_owner(
    session_id: str,
    current_user: Union[User, str, int],
) -> dict:
    """
    Require session ownership and return session metadata.
    
    Similar to verify_session_owner but returns the metadata.
    
    Args:
        session_id: The session ID to check ownership of
        current_user: The current user
        
    Returns:
        Session metadata dict
        
    Raises:
        HTTPException: 403 if user doesn't own the session
        HTTPException: 404 if session doesn't exist
    """
    meta = get_session_metadata(session_id)
    
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    owner_id = meta.get("user_id")
    
    if owner_id is None:
        return meta
    
    # Get the user ID for comparison
    if isinstance(current_user, User):
        user_id = str(current_user.id)
        is_admin = _is_admin(current_user)
    else:
        user_id = str(current_user)
        is_admin = False
    
    # Admin access
    if is_admin:
        return meta
    
    if str(owner_id) != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this session",
        )
    
    return meta


def _is_admin(user: User) -> bool:
    """Check if user has admin role."""
    from api.models.models import UserRole
    
    role = user.role
    if isinstance(role, UserRole):
        return role == UserRole.ADMIN
    return str(role).lower() == "admin"


def require_job_owner(
    job,
    current_user: Union[User, str, int],
    allow_admin: bool = True,
) -> None:
    """
    Verify that the current user owns the specified job.
    
    Args:
        job: The Job object to check
        current_user: The current user
        allow_admin: If True, admins can access any job
        
    Raises:
        HTTPException: 403 if user doesn't own the job
    """
    if job.user_id is None:
        # Job has no owner - allow access
        return
    
    # Get the user ID for comparison
    if isinstance(current_user, User):
        user_id = current_user.id
        is_admin = _is_admin(current_user)
    else:
        user_id = int(current_user) if str(current_user).isdigit() else None
        is_admin = False
    
    # Check if user is admin and admin access is allowed
    if allow_admin and is_admin:
        return
    
    if job.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this job",
        )
