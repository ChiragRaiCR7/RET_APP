from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.core.dependencies import get_current_user
from api.core.database import get_db
from api.models.models import User

def require_role(required_role: str):
    def checker(
        user_id: str = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        user = db.query(User).get(int(user_id))
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED)

        if user.role != required_role:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"{required_role} role required",
            )

        return user

    return checker
