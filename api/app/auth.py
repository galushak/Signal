from collections import defaultdict
from datetime import UTC, datetime, timedelta
from threading import Lock

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import AuthSession, User
from .settings import get_settings

settings = get_settings()
password_hasher = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
_attempts: dict[str, list[datetime]] = defaultdict(list)
_enrollment_attempts: dict[str, list[datetime]] = defaultdict(list)
_lock = Lock()


def utc_datetime(value: datetime) -> datetime:
    """Treat database timestamps without an offset as UTC.

    PostgreSQL preserves timezone-aware values, while SQLite (used by the
    isolated test suite) returns the same columns without an offset.
    """
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def check_login_rate_limit(key: str) -> None:
    now = datetime.now(UTC)
    with _lock:
        history = [at for at in _attempts[key] if now - at < timedelta(minutes=15)]
        _attempts[key] = history
        if len(history) >= 8:
            raise HTTPException(status_code=429, detail="Too many sign-in attempts. Please wait 15 minutes and try again.")
        history.append(now)


def check_device_enrollment_rate_limit(key: str) -> None:
    """Throttle short-code guesses separately from human sign-in attempts."""
    now = datetime.now(UTC)
    with _lock:
        history = [at for at in _enrollment_attempts[key] if now - at < timedelta(minutes=15)]
        _enrollment_attempts[key] = history
        if len(history) >= 12:
            raise HTTPException(status_code=429, detail="Too many enrollment attempts. Please wait 15 minutes and try again.")
        history.append(now)


def create_session(db: Session, user: User) -> tuple[str, AuthSession]:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.access_token_minutes)
    session = AuthSession(user_id=user.id, expires_at=expires_at)
    db.add(session)
    db.flush()
    token = jwt.encode({"sub": user.id, "sid": session.id, "exp": expires_at, "iat": now}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, session


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in to continue.")
    try:
        claims = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your sign-in session has expired. Please sign in again.") from exc
    session = db.get(AuthSession, claims.get("sid"))
    user = db.get(User, claims.get("sub"))
    if not session or session.revoked_at or utc_datetime(session.expires_at) < datetime.now(UTC) or not user or not user.enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your sign-in session is no longer active.")
    return user


def current_session(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> AuthSession:
    if not credentials:
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    try:
        claims = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Your sign-in session has expired.") from exc
    session = db.get(AuthSession, claims.get("sid"))
    if not session:
        raise HTTPException(status_code=401, detail="Your sign-in session is no longer active.")
    return session


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else None)
