"""Accounts, tokens, refresh rotation, and who can see which dataset."""
from datetime import timedelta
import jwt
import pytest
from fastapi.testclient import TestClient
from app.api import deps
from app.main import app
from app.services import auth, rate_limit
from tests.conftest import upload, SALES_CSV, PASSWORD

def register(client, email="carol@example.com", password=PASSWORD):
    return client.post("/api/auth/register", json={"email": email, "password": password})

def login(client, email="carol@example.com", password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})

def bearer(r):
    return {"Authorization": f"Bearer {r.json()['access_token']}"}

def upload_as(client, headers=None):
    r = client.post("/api/upload", files={"file": ("sales.csv", SALES_CSV, "text/csv")}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["dataset_id"]

# --- accounts ----------------------------------------------------------------

def test_register_returns_a_session(client):
    r = register(client, "Carol@Example.com")
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["email"] == "carol@example.com"       # stored lowercased
    assert body["token_type"] == "bearer" and body["expires_in"] == 15 * 60
    cookie = r.headers["set-cookie"]
    assert "iq_refresh=" in cookie and "HttpOnly" in cookie and "Path=/api/auth" in cookie
    assert "samesite=strict" in cookie.lower()
    assert r.headers["cache-control"] == "no-store"

def test_register_validation(client):
    register(client)
    assert register(client, "CAROL@example.com").status_code == 409
    assert register(client, "not-an-email").status_code == 422
    assert register(client, "dan@example.com", "short").status_code == 422

def test_login(client):
    register(client)
    assert login(client).status_code == 200
    wrong = login(client, password="wrong password")
    missing = login(client, email="nobody@example.com")
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json() == missing.json()          # same answer either way: no account probing

def test_password_is_hashed(client):
    register(client)
    from app.db import SessionLocal, User
    with SessionLocal() as s:
        stored = s.query(User).one().password_hash
    assert stored.startswith("$argon2id$") and PASSWORD not in stored

def test_me(client):
    headers = bearer(register(client))
    assert client.get("/api/auth/me", headers=headers).json()["email"] == "carol@example.com"
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401

def test_expired_and_forged_tokens_are_rejected(client):
    register(client)
    user = auth.authenticate("carol@example.com", PASSWORD)
    claims = jwt.decode(auth.issue_access(user), options={"verify_signature": False})
    expired = jwt.encode(claims | {"exp": claims["iat"] - 1}, auth.JWT_SECRET, algorithm="HS256")
    forged = jwt.encode(claims, "a different secret of the same thirty-two plus bytes", algorithm="HS256")
    wrong_type = jwt.encode(claims | {"typ": "refresh"}, auth.JWT_SECRET, algorithm="HS256")
    for token in (expired, forged, wrong_type):
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401
        assert "invalid_token" in r.headers["www-authenticate"]

def test_bad_token_is_an_error_not_a_guest(client):
    # an expired session should make the client refresh, not quietly upload as a guest
    r = client.post("/api/upload", files={"file": ("s.csv", SALES_CSV, "text/csv")},
                    headers={"Authorization": "Bearer junk"})
    assert r.status_code == 401

# --- refresh -----------------------------------------------------------------

def test_refresh_rotates_the_cookie(client):
    first = register(client).cookies["iq_refresh"]
    r = client.post("/api/auth/refresh")
    assert r.status_code == 200 and r.json()["user"]["email"] == "carol@example.com"
    second = r.cookies["iq_refresh"]
    assert second != first
    assert client.get("/api/auth/me", headers=bearer(r)).status_code == 200

def test_refresh_without_a_cookie(client):
    assert client.post("/api/auth/refresh").status_code == 401

def test_replayed_refresh_token_revokes_the_family(client, monkeypatch):
    monkeypatch.setattr(auth, "REUSE_GRACE", timedelta(0))
    stolen = register(client).cookies["iq_refresh"]
    current = client.post("/api/auth/refresh").cookies["iq_refresh"]   # the real user moves on

    thief = TestClient(app, cookies={"iq_refresh": stolen})
    r = thief.post("/api/auth/refresh")
    assert r.status_code == 401
    assert 'iq_refresh=""' in r.headers["set-cookie"]                   # told to drop it

    # and the legitimate session is gone too: someone had a copy
    victim = TestClient(app, cookies={"iq_refresh": current})
    assert victim.post("/api/auth/refresh").status_code == 401

def test_concurrent_refresh_within_grace_keeps_the_session(client):
    first = register(client).cookies["iq_refresh"]
    current = client.post("/api/auth/refresh").cookies["iq_refresh"]
    other_tab = TestClient(app, cookies={"iq_refresh": first})
    assert other_tab.post("/api/auth/refresh").status_code == 401     # lost the race
    assert TestClient(app, cookies={"iq_refresh": current}).post("/api/auth/refresh").status_code == 200

def test_expired_refresh_token(client, monkeypatch):
    monkeypatch.setattr(auth, "REFRESH_TTL", timedelta(seconds=-1))
    register(client)
    assert client.post("/api/auth/refresh").status_code == 401

def test_logout_ends_the_session(client):
    token = register(client).cookies["iq_refresh"]
    r = client.post("/api/auth/logout")
    assert r.status_code == 204
    assert TestClient(app, cookies={"iq_refresh": token}).post("/api/auth/refresh").status_code == 401
    assert client.post("/api/auth/logout").status_code == 204          # already out: still fine

# --- ownership ---------------------------------------------------------------

def test_signed_in_uploads_are_private(client, alice, bob, fake_llm):
    a, a_headers = alice
    b, b_headers = bob
    dataset_id = upload_as(a, a_headers)
    fake_llm("SELECT 1 AS n")

    assert a.get(f"/api/datasets/{dataset_id}", headers=a_headers).status_code == 200
    for c, headers in ((b, b_headers), (client, None)):
        assert c.get(f"/api/datasets/{dataset_id}", headers=headers).status_code == 404
        assert c.post("/api/query", json={"dataset_id": dataset_id, "question": "q"},
                      headers=headers).status_code == 404
        assert c.put(f"/api/datasets/{dataset_id}/dictionary", json={"tables": {}},
                     headers=headers).status_code == 404

def test_guest_uploads_stay_open(client, alice):
    a, a_headers = alice
    dataset_id = upload_as(client)
    assert a.get(f"/api/datasets/{dataset_id}", headers=a_headers).status_code == 200
    assert client.get(f"/api/datasets/{dataset_id}").status_code == 200

def test_list_and_delete_datasets(client, alice, bob):
    a, a_headers = alice
    b, b_headers = bob
    mine = upload_as(a, a_headers)
    upload_as(b, b_headers)
    guest = upload_as(client)

    listed = a.get("/api/datasets", headers=a_headers).json()
    assert [d["dataset_id"] for d in listed] == [mine]
    assert listed[0]["filename"] == "sales.csv" and listed[0]["rows"] == 4
    assert client.get("/api/datasets").status_code == 401

    assert b.delete(f"/api/datasets/{mine}", headers=b_headers).status_code == 404
    assert a.delete(f"/api/datasets/{guest}", headers=a_headers).status_code == 403
    assert a.delete(f"/api/datasets/{mine}", headers=a_headers).status_code == 204
    assert a.get(f"/api/datasets/{mine}", headers=a_headers).status_code == 404

def test_auth_required_mode(client, monkeypatch):
    monkeypatch.setattr(deps, "AUTH_REQUIRED", True)
    r = upload(client, "sales.csv", SALES_CSV, "text/csv")
    assert r.status_code == 401
    headers = bearer(register(client))          # signing up still works
    assert upload_as(client, headers)

# --- rate limits -------------------------------------------------------------

def test_query_limit_is_per_account(client, alice, bob, fake_llm, monkeypatch):
    monkeypatch.setitem(rate_limit.LIMITS, "query", [(1, 60)])
    fake_llm("SELECT 1 AS n")
    a, a_headers = alice
    b, b_headers = bob
    ask = lambda c, h, d: c.post("/api/query", json={"dataset_id": d, "question": "q"}, headers=h)
    a_data, b_data = upload_as(a, a_headers), upload_as(b, b_headers)
    # same IP (the test client), different accounts
    assert ask(a, a_headers, a_data).status_code == 200
    assert ask(a, a_headers, a_data).status_code == 429
    assert ask(b, b_headers, b_data).status_code == 200

def test_sign_in_is_limited_per_ip(client, monkeypatch):
    monkeypatch.setitem(rate_limit.LIMITS, "auth", [(2, 60)])
    register(client)
    assert login(client, password="guess 1").status_code == 401
    assert login(client).status_code == 429             # even the right password, for now

def test_gateway_ip_header_needs_the_shared_token(client, sales, fake_llm, monkeypatch):
    monkeypatch.setattr(rate_limit, "GATEWAY_TOKEN", "gw-secret")
    monkeypatch.setitem(rate_limit.LIMITS, "query", [(1, 60)])
    fake_llm("SELECT 1 AS n")
    ask = lambda headers: client.post("/api/query", json={"dataset_id": sales["dataset_id"], "question": "q"},
                                      headers=headers)
    via_gateway = lambda ip: {"X-Gateway-Token": "gw-secret", "X-Real-IP": ip}
    assert ask(via_gateway("1.1.1.1")).status_code == 200
    assert ask(via_gateway("1.1.1.1")).status_code == 429
    assert ask(via_gateway("2.2.2.2")).status_code == 200
    # without the token X-Real-IP is ignored, so it can't be used to dodge the limit
    assert ask({"X-Real-IP": "3.3.3.3"}).status_code == 200      # first hit for the socket address
    assert ask({"X-Real-IP": "4.4.4.4"}).status_code == 429
    assert ask({"X-Gateway-Token": "wrong", "X-Real-IP": "5.5.5.5"}).status_code == 429

# --- request ids ---------------------------------------------------------------

@pytest.mark.parametrize("sent, kept", [("abc-123", True), ("", False), ("bad id with spaces", False)])
def test_request_id(client, sent, kept):
    r = client.get("/health", headers={"X-Request-ID": sent} if sent else {})
    rid = r.headers["x-request-id"]
    assert (rid == sent) is kept and rid
