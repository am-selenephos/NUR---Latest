from redis.asyncio import Redis


async def test_healthz_returns_healthy(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy", "ai_provider": "disabled"}
    assert r.headers["content-security-policy"] == "default-src 'none'"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "camera=()" in r.headers["permissions-policy"]
    assert "strict-transport-security" not in r.headers


async def test_production_responses_enable_hsts(client, monkeypatch):
    import app.main as main

    settings = main.get_settings()
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: settings.model_copy(update={"app_env": "production"}),
    )

    r = await client.get("/healthz")

    assert r.status_code == 200
    assert (
        r.headers["strict-transport-security"]
        == "max-age=63072000; includeSubDomains; preload"
    )


async def test_readyz_reflects_dependencies_ok(client):
    r = await client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["checks"] == {"database": "ok", "redis": "ok"}


async def test_readyz_reports_broken_redis(client):
    good = client.app.state.redis
    client.app.state.redis = Redis.from_url("redis://localhost:6399/0",
                                            socket_connect_timeout=0.2)
    try:
        r = await client.get("/readyz")
        assert r.status_code == 503
        body = r.json()
        assert body["checks"]["redis"] == "error"
        assert body["checks"]["database"] == "ok"
    finally:
        await client.app.state.redis.aclose()
        client.app.state.redis = good


async def test_readyz_reports_draining_during_shutdown(client):
    # A draining instance must report not-ready even while its dependencies are
    # still momentarily healthy, so load balancers route new traffic away.
    client.app.state.ready = False
    try:
        r = await client.get("/readyz")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "draining"
        assert body["checks"] == {"lifecycle": "draining"}
    finally:
        client.app.state.ready = True


async def test_lifespan_drains_ready_and_disposes_engine():
    # Exercise the real graceful-shutdown path: entering marks ready; exiting
    # flips ready off and disposes the database connection pool.
    import app.db.session as dbs
    from app.main import create_app, lifespan

    app = create_app()
    dbs.get_engine()
    assert dbs._engine is not None

    async with lifespan(app):
        assert app.state.ready is True

    assert app.state.ready is False
    assert dbs._engine is None  # pool disposed on shutdown, not leaked


async def test_metrics_exposes_counters(client):
    await client.get("/healthz")
    r = await client.get("/metrics")
    assert r.status_code == 200
    assert "nur_http_requests_total" in r.text
    assert 'nur_ai_provider_configured{provider="disabled"} 1' in r.text
    assert 'route="/healthz"' in r.text


async def test_local_preview_origin_can_preflight_auth(client):
    r = await client.options(
        "/api/v1/auth/register",
        headers={
            "Origin": "http://localhost:4173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:4173"
    assert r.headers["access-control-allow-credentials"] == "true"
