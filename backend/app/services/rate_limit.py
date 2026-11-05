"""Fixed-window rate limits per client, e.g. RATE_LIMIT_QUERY="20/minute,200/day".

Questions cost an LLM call and uploads cost disk and CPU, so both are capped
per client: the account when signed in, otherwise the IP. Sign-in is capped
per IP to slow down password guessing. Counters live in the shared store
(Redis when configured)."""
import hmac
import logging
import os
from fastapi import HTTPException, Request, Response
from app.store import get_store
from app import metrics

log = logging.getLogger(__name__)

WINDOWS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
DEFAULTS = {
    "query": "20/minute,200/day",
    "upload": "10/minute,100/day",
    "feedback": "30/minute",
    "auth": "10/minute,50/hour",       # register + login, per IP
    "refresh": "30/minute",
}
# limits that always go by IP, even with a token
PER_IP = {"auth", "refresh"}

# Behind a proxy every request comes from the proxy, so read the real client
# from a header it sets and clients can't forge (Fly: Fly-Client-IP).
CLIENT_IP_HEADER = os.getenv("CLIENT_IP_HEADER", "")
# The gateway sends the client's address in X-Real-IP along with this shared
# secret. The secret is what makes the header trustworthy: a client calling
# the api directly can set X-Real-IP but can't prove it came from the gateway.
GATEWAY_TOKEN = os.getenv("GATEWAY_TOKEN", "")

def parse(spec: str) -> list[tuple[int, int]]:
    """'20/minute,200/day' -> [(20, 60), (200, 86400)]. Empty or '0' means no limit."""
    rules = []
    for part in spec.split(","):
        part = part.strip()
        if not part or part == "0":
            continue
        count, _, unit = part.partition("/")
        if unit not in WINDOWS or not count.isdigit():
            raise ValueError(f"Bad rate limit {part!r}, expected e.g. 20/minute")
        rules.append((int(count), WINDOWS[unit]))
    return rules

LIMITS = {name: parse(os.getenv(f"RATE_LIMIT_{name.upper()}", spec)) for name, spec in DEFAULTS.items()}

def client_ip(request: Request) -> str:
    sent = request.headers.get("X-Gateway-Token", "")
    if GATEWAY_TOKEN and sent and hmac.compare_digest(sent, GATEWAY_TOKEN):
        if ip := request.headers.get("X-Real-IP"):
            return ip.strip()
    if CLIENT_IP_HEADER and (ip := request.headers.get(CLIENT_IP_HEADER)):
        return ip.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def client_id(request: Request, name: str = "") -> str:
    if name not in PER_IP:
        if (user := _token_user(request)) is not None:
            return f"user:{user}"
    return f"ip:{client_ip(request)}"

def _token_user(request: Request) -> str | None:
    """User id from a valid bearer token, without failing the request (the
    route's own dependency decides what a bad token means)."""
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    from app.services.auth import decode_access
    try:
        return decode_access(header[7:].strip())["sub"]
    except HTTPException:
        return None

def limit(name: str):
    async def check(request: Request, response: Response):
        rules = LIMITS.get(name) or []
        if not rules:
            return
        who = client_id(request, name)
        tightest = None   # (remaining, limit, reset) of the rule closest to its cap
        for allowed, window in rules:
            try:
                count, reset = get_store().hit(f"rl:{name}:{window}:{who}", window)
            except Exception as e:   # fail open — an outage shouldn't take the api down
                log.warning("rate limit check failed: %s", e)
                return
            if count > allowed:
                metrics.RATE_LIMITED.labels(name).inc()
                raise HTTPException(
                    429,
                    f"Too many requests. Try again in {reset} seconds.",
                    headers={
                        "Retry-After": str(reset),
                        "X-RateLimit-Limit": str(allowed),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset),
                    },
                )
            remaining = allowed - count
            if tightest is None or remaining < tightest[0]:
                tightest = (remaining, allowed, reset)
        remaining, allowed, reset = tightest
        response.headers["X-RateLimit-Limit"] = str(allowed)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset)
    return check
