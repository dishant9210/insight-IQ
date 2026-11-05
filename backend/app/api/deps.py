"""Who is calling. Shared by every router and the rate limiter."""
import os
from dataclasses import dataclass
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.services import auth

# Off by default so the demo works without an account; signed-in users get
# private datasets and a history. On: every dataset and query route needs a token.
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"

_bearer = HTTPBearer(auto_error=False)

@dataclass(frozen=True)
class Viewer:
    id: str
    email: str

def viewer(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Viewer | None:
    """The signed-in user, or None for a guest. A bad or expired token is a
    401 (not a guest), so the client knows to refresh."""
    if creds is None:
        if AUTH_REQUIRED:
            raise HTTPException(401, "Sign in first", headers={"WWW-Authenticate": "Bearer"})
        return None
    claims = auth.decode_access(creds.credentials)
    return Viewer(claims["sub"], claims.get("email", ""))

def require_user(user: Viewer | None = Depends(viewer)) -> Viewer:
    if user is None:
        raise HTTPException(401, "Sign in first", headers={"WWW-Authenticate": "Bearer"})
    return user

