"""Shared FastAPI dependencies for authentication and authorization.

Authorization is two independent checks, and both are enforced here rather than inline in
each handler so every route applies the same ones (docs/architecture.md, "Authorization"):

  1. role     — does this user's role permit this kind of action at all?
  2. ownership — is this specific report theirs, or are they excluded *because* it is theirs?

The self-approval rule is check 2 applied to a decision, and it lives in
app/services/lifecycle.py so the single-report and bulk paths cannot disagree.
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User

_bearer_scheme = HTTPBearer(auto_error=False)

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise _CREDENTIALS_ERROR

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise _CREDENTIALS_ERROR from None

    # The role is re-read from the database, never trusted from the token: a token issued
    # before a role change must not keep granting the old role.
    user = db.get(User, user_id)
    if user is None:
        raise _CREDENTIALS_ERROR

    return user


def require_approver(current_user: User = Depends(get_current_user)) -> User:
    """Role gate. Says nothing about ownership — that is checked per report."""
    if not current_user.is_approver:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires the approver role.",
        )
    return current_user
