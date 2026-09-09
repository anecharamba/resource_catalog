"""
Real multi-admin authentication: bcrypt password hashing + JWT bearer tokens.

Uses raw `bcrypt` rather than passlib (passlib's bcrypt backend has a known
version-compatibility break with recent bcrypt releases).
"""
from __future__ import annotations

import os
import secrets
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_env_secret = os.environ.get("JWT_SECRET")
if _env_secret:
    SECRET_KEY = _env_secret
else:
    # No hardcoded fallback here on purpose: a fixed secret baked into source
    # code that's ever been shared or committed is a forgeable-token
    # vulnerability the moment anyone deploys without overriding it. A random
    # secret generated fresh per process start can't be guessed, at the cost
    # of invalidating existing sessions on every restart — set JWT_SECRET
    # explicitly in any environment where that matters (i.e. anywhere beyond
    # a single local dev session).
    SECRET_KEY = secrets.token_hex(32)
    print(
        "\n[auth] WARNING: JWT_SECRET is not set — generated a random secret "
        "for this process only. All admin sessions will be invalidated on "
        "restart. Set the JWT_SECRET environment variable to a stable, "
        "random value before deploying.\n"
    )

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 12

security = HTTPBearer()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: int, username: str, role: str, session_version: int = 1) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "sv": session_version,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")


def get_current_admin(creds: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    payload = decode_token(creds.credentials)
    if payload.get("role") != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required")
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token subject")
    import sqlite3
    from pathlib import Path
    db_path = Path(__file__).parent.parent / "data" / "catalog" / "catalog.db"
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT username, role, is_active, session_version FROM admin_users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
    except sqlite3.Error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication database unavailable")
    if not row or row[1] != "admin" or not row[2]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Administrator account is no longer active")
    token_version = payload.get("sv", 1)
    if int(token_version) != int(row[3] or 1):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session has been revoked. Please sign in again")
    return {"id": user_id, "username": row[0], "role": "admin"}


# ---------- Account lockout ----------
# In-memory and per-process, matching the same trade-off already documented
# for the background job queue in README.md: fine for one backend instance,
# resets on restart, doesn't share state across multiple replicas. This is a
# second layer alongside IP-based rate limiting — rate limiting alone doesn't
# stop a distributed attack (many IPs) targeting one specific account.

_failed_attempts: dict[str, list[float]] = {}
_lockouts: dict[str, float] = {}

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60
ATTEMPT_WINDOW_SECONDS = 15 * 60


def is_locked_out(username: str) -> tuple[bool, int]:
    """Returns (is_locked, seconds_remaining)."""
    unlock_at = _lockouts.get(username)
    if unlock_at is None:
        return False, 0
    remaining = unlock_at - time.time()
    if remaining <= 0:
        _lockouts.pop(username, None)
        _failed_attempts.pop(username, None)
        return False, 0
    return True, int(remaining)


def record_failed_login(username: str) -> None:
    now = time.time()
    attempts = [t for t in _failed_attempts.get(username, []) if now - t < ATTEMPT_WINDOW_SECONDS]
    attempts.append(now)
    _failed_attempts[username] = attempts
    if len(attempts) >= MAX_FAILED_ATTEMPTS:
        _lockouts[username] = now + LOCKOUT_SECONDS


def clear_failed_logins(username: str) -> None:
    _failed_attempts.pop(username, None)
    _lockouts.pop(username, None)
