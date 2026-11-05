import os
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from app.api.deps import Viewer, require_user
from app.models.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.services import auth
from app.services.rate_limit import limit

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE = "iq_refresh"
COOKIE_PATH = "/api/auth"
# the gateway serves the app and the api from one origin, so the cookie is
# first-party and can be strict
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "strict")

def _session(response: Response, user, refresh: str) -> TokenResponse:
    response.set_cookie(
        COOKIE, refresh,
        max_age=int(auth.REFRESH_TTL.total_seconds()),
        path=COOKIE_PATH, httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE,
    )
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(
        access_token=auth.issue_access(user),
        expires_in=int(auth.ACCESS_TTL.total_seconds()),
        user=UserOut(**auth.user_dict(user)),
    )

def _clear(response: Response):
    response.delete_cookie(COOKIE, path=COOKIE_PATH, httponly=True,
                           secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE)

@router.post("/register", response_model=TokenResponse, status_code=201,
             dependencies=[Depends(limit("auth"))])
def register(req: RegisterRequest, response: Response):
    user = auth.register(req.email, req.password)
    return _session(response, user, auth.issue_refresh(user.id))

@router.post("/login", response_model=TokenResponse, dependencies=[Depends(limit("auth"))])
def login(req: LoginRequest, response: Response):
    user = auth.authenticate(req.email, req.password)
    return _session(response, user, auth.issue_refresh(user.id))

@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(limit("refresh"))])
def refresh(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Not signed in")
    try:
        user, next_token = auth.rotate_refresh(token)
    except HTTPException as e:
        # a raised error would drop cookie changes, so build the response here
        failed = JSONResponse({"detail": e.detail}, status_code=e.status_code)
        _clear(failed)
        return failed
    return _session(response, user, next_token)

@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    if token := request.cookies.get(COOKIE):
        auth.revoke_refresh(token)
    _clear(response)
    response.status_code = 204
    return response

@router.get("/me", response_model=UserOut)
def me(user: Viewer = Depends(require_user)):
    found = auth.get_user(user.id)
    if found is None:
        raise HTTPException(401, "Account no longer exists")
    return UserOut(**auth.user_dict(found))
