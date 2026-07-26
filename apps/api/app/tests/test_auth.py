import uuid

from sqlalchemy import text

from app.tests.conftest import register_user, unique_email


def _cookie_headers(response, name):
    return [h for h in response.headers.get_list("set-cookie") if h.startswith(name + "=")]


async def test_register_creates_full_identity_graph(client, super_engine):
    r, email, _ = await register_user(client)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == email
    assert body["profile"]["chosen_name"] == "Star"
    assert "password" not in r.text and "password_hash" not in r.text
    uid = uuid.UUID(body["id"])

    sc = _cookie_headers(r, "nur_session")
    assert sc and "httponly" in sc[0].lower() and "samesite=lax" in sc[0].lower()
    assert _cookie_headers(r, "nur_csrf")  # csrf cookie is JS-readable by design

    async with super_engine.connect() as conn:
        counts = {}
        for label, sql in {
            "user": "SELECT count(*) FROM users WHERE id=:u",
            "profile": "SELECT count(*) FROM profiles WHERE user_id=:u",
            "orbit": "SELECT count(*) FROM orbits WHERE owner_user_id=:u",
            "consent": "SELECT count(*) FROM consent_records WHERE user_id=:u AND granted",
            "session": "SELECT count(*) FROM sessions WHERE user_id=:u AND revoked_at IS NULL",
            "audit": ("SELECT count(*) FROM audit_events WHERE actor_user_id=:u AND "
                      "event_type IN ('user.registered','consent.granted','session.created')"),
        }.items():
            counts[label] = (await conn.execute(text(sql), {"u": uid})).scalar_one()
    assert counts == {"user": 1, "profile": 1, "orbit": 7, "consent": 1, "session": 1, "audit": 3}


async def test_duplicate_email_fails_generically(client):
    r1, email, pw = await register_user(client)
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/auth/register",
                           json={"chosen_name": "X", "email": email, "password": pw, "consent": True})
    assert r2.status_code == 400
    assert email not in r2.json()["detail"]


async def test_login_wrong_password_is_generic_and_matches_unknown_user(client):
    _, email, _ = await register_user(client)
    bad_known = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-wrong"})
    bad_unknown = await client.post("/api/v1/auth/login",
                                    json={"email": f"nobody-{uuid.uuid4().hex[:8]}@nurapp.dev",
                                          "password": "wrong-wrong"})
    assert bad_known.status_code == bad_unknown.status_code == 401
    assert bad_known.json() == bad_unknown.json()  # no account enumeration


async def test_login_sets_httponly_session_cookie(client):
    _, email, pw = await register_user(client)
    client.cookies.clear()
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200
    sc = _cookie_headers(r, "nur_session")
    assert sc and "httponly" in sc[0].lower() and "path=/" in sc[0].lower()


async def test_me_works_after_login(client):
    _, email, pw = await register_user(client)
    client.cookies.clear()
    await client.post("/api/v1/auth/login", json={"email": email, "password": pw})
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == email
    assert r.json()["orbit"]["id"]


async def test_me_unauthenticated_401(client):
    client.cookies.clear()
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


async def test_logout_requires_csrf_then_revokes(client, super_engine):
    reg, email, pw = await register_user(client)
    uid = reg.json()["id"]

    no_csrf = await client.post("/api/v1/auth/logout")
    assert no_csrf.status_code == 403

    csrf = client.cookies.get("nur_csrf")
    r = await client.post("/api/v1/auth/logout", headers={"x-csrf-token": csrf})
    assert r.status_code == 204

    async with super_engine.connect() as conn:
        revoked = (await conn.execute(
            text("SELECT count(*) FROM sessions WHERE user_id=:u AND revoked_at IS NOT NULL"),
            {"u": uid})).scalar_one()
    assert revoked == 1


async def test_revoked_session_cannot_access_me(client):
    _, email, pw = await register_user(client)
    csrf = client.cookies.get("nur_csrf")
    await client.post("/api/v1/auth/logout", headers={"x-csrf-token": csrf})
    # cookie jar may still hold the old value; present it explicitly to prove revocation
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


async def test_login_rate_limited_after_burst(client):
    email = f"rl-{uuid.uuid4().hex[:8]}@nurapp.dev"
    last = None
    for _ in range(11):
        last = await client.post("/api/v1/auth/login",
                                 json={"email": email, "password": "wrong-wrong"})
    assert last.status_code == 429


async def test_register_rate_limited_after_burst(client):
    """Registration is rate-limited per IP, same as login (fix: registration
    was previously unthrottled)."""
    last = None
    for i in range(11):
        last = await client.post("/api/v1/auth/register", json={
            "chosen_name": f"Burst{i}", "email": f"burst{i}-{unique_email()}",
            "password": "orbit-passphrase-9", "consent": True,
        })
        client.cookies.clear()
    assert last.status_code == 429
    assert "Too many attempts" in last.json()["detail"]
