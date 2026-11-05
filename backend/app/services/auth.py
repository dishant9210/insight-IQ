"""Accounts and tokens.

- Passwords are hashed with argon2id.
- Access tokens are short-lived JWTs (HS256) sent as `Authorization: Bearer`.
  The browser keeps them in memory only.
- Refresh tokens are random strings in an httpOnly cookie scoped to
  /api/auth. The database keeps only their SHA-256. Every refresh rotates the
  token; replaying an already-used one revokes its whole family (all tokens
  descended from the same sign-in), which logs out whoever copied it.
"""
import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException
from sqlalchemy import select, update
from app.db import SessionLocal, User, RefreshToken

log = logging.getLogger(__name__)

JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET:
    # fine for a single local process; tokens stop working on restart
    JWT_SECRET = secrets.token_urlsafe(48)
    log.warning("JWT_SECRET is not set; using a random one for this process")
elif len(JWT_SECRET.encode()) < 32:
    log.warning("JWT_SECRET is shorter than 32 bytes; use e.g. `openssl rand -hex 32`")
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "insightiq"
ACCESS_TTL = timedelta(minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "15")))
REFRESH_TTL = timedelta(days=int(os.getenv("REFRESH_TOKEN_DAYS", "30")))
# two tabs refreshing at once both present the same token; the slower one
# shouldn't be treated as a stolen token
REUSE_GRACE = timedelta(seconds=10)

_hasher = PasswordHasher()
# verified against when the email doesn't exist, so a miss takes as long as a wrong password
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _aware(dt: datetime) -> datetime:
    # SQLite hands back naive datetimes
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def user_dict(user: User) -> dict:
    return {"id": user.id, "email": user.email, "created_at": user.created_at}

# --- accounts --------------------------------------------------------------

def register(email: str, password: str) -> User:
    email = email.strip().lower()
    with SessionLocal() as s:
        if s.scalar(select(User.id).where(User.email == email)):
            raise HTTPException(409, "An account with this email already exists")
        user = User(id=str(uuid.uuid4()), email=email, password_hash=_hasher.hash(password))
        s.add(user)
        s.commit()
        return user

def authenticate(email: str, password: str) -> User:
    email = email.strip().lower()
    with SessionLocal() as s:
        user = s.scalar(select(User).where(User.email == email))
        try:
            _hasher.verify(user.password_hash if user else _DUMMY_HASH, password)
        except (VerificationError, InvalidHashError):
            user = None
        if user is None:
            raise HTTPException(401, "Wrong email or password")
        if _hasher.check_needs_rehash(user.password_hash):
            user.password_hash = _hasher.hash(password)
            s.commit()
        return user

def get_user(user_id: str) -> User | None:
    with SessionLocal() as s:
        return s.get(User, user_id)

# --- access tokens ---------------------------------------------------------

def issue_access(user: User) -> str:
    now = _now()
    return jwt.encode({
        "sub": user.id,
        "email": user.email,
        "iss": JWT_ISSUER,
        "iat": now,
        "exp": now + ACCESS_TTL,
        "jti": uuid.uuid4().hex,
        "typ": "access",
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_access(token: str) -> dict:
    try:
        claims = jwt.decode(
            token, JWT_SECRET, algorithms=[JWT_ALGORITHM], issuer=JWT_ISSUER,
            options={"require": ["sub", "exp", "iat", "iss"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired", headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token", headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})
    if claims.get("typ") != "access":
        raise HTTPException(401, "Invalid token", headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})
    return claims

# --- refresh tokens --------------------------------------------------------

def issue_refresh(user_id: str, family: str | None = None) -> str:
    token = secrets.token_urlsafe(32)
    with SessionLocal() as s:
        s.add(RefreshToken(
            user_id=user_id,
            family=family or str(uuid.uuid4()),
            token_hash=_sha(token),
            expires_at=_now() + REFRESH_TTL,
        ))
        s.commit()
    return token

def rotate_refresh(token: str) -> tuple[User, str]:
    """Spend a refresh token: returns (user, the next refresh token)."""
    now = _now()
    with SessionLocal() as s:
        row = s.scalar(select(RefreshToken).where(RefreshToken.token_hash == _sha(token)))
        if row is None or _aware(row.expires_at) <= now:
            raise HTTPException(401, "Session expired")
        if row.revoked_at is not None:
            if now - _aware(row.revoked_at) > REUSE_GRACE:
                log.warning("refresh token reused; revoking family %s of user %s", row.family, row.user_id)
                _revoke_family(s, row.family, now)
                s.commit()
            raise HTTPException(401, "Session expired")
        # claim it atomically, so two concurrent refreshes can't both succeed
        claimed = s.execute(
            update(RefreshToken)
            .where((RefreshToken.id == row.id) & RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        ).rowcount
        s.commit()
        if not claimed:
            raise HTTPException(401, "Session expired")
        user = s.get(User, row.user_id)
        family = row.family
    if user is None:
        raise HTTPException(401, "Session expired")
    return user, issue_refresh(user.id, family)

def revoke_refresh(token: str):
    """Sign out: the token's whole family stops working."""
    with SessionLocal() as s:
        row = s.scalar(select(RefreshToken).where(RefreshToken.token_hash == _sha(token)))
        if row is not None:
            _revoke_family(s, row.family, _now())
            s.commit()

def _revoke_family(s, family: str, when: datetime):
    s.execute(
        update(RefreshToken)
        .where((RefreshToken.family == family) & RefreshToken.revoked_at.is_(None))
        .values(revoked_at=when)
    )
