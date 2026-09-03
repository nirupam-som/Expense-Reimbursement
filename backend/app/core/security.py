"""Password hashing and JWT issuing/verification.

bcrypt directly rather than via passlib: passlib 1.7.4 is unmaintained and warns loudly
against bcrypt 4.x, and we only need two functions from it.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

# bcrypt refuses inputs longer than 72 bytes; the API schema caps passwords below that.
MAX_PASSWORD_BYTES = 72


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode()[:MAX_PASSWORD_BYTES], bcrypt.gensalt()).decode()


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode()[:MAX_PASSWORD_BYTES], password_hash.encode())


def create_access_token(user_id: int, role: str) -> str:
    issued_at = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),  # the JWT spec wants `sub` to be a string
        "role": role,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError (expired, bad signature, malformed) for the caller to handle."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
