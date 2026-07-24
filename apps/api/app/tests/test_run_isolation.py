"""Regression proof for test-run isolation.

History: a full-suite run once reported two rate-limit failures that looked like a
product defect. They were not. A second pytest process was running concurrently
against the same PostgreSQL and Redis, and the per-test `flushdb()` in the client
fixture wiped the other run's limiter counters mid-test, so the eleventh request
was allowed through. The limiter was always sound; the test system was not isolated.

These tests fail if that isolation is ever removed:

  * limiter keys must be namespaced per run;
  * one run's cleanup must not touch another run's keys;
  * a foreign run reaching the eleventh request must not reset this run's window;
  * the shared database name must be per-run, not a fixed `nur_test`.
"""
import os

import pytest
from redis.asyncio import Redis

from app.core.config import get_settings
from app.services.rate_limit import allow_login, namespaced

from .conftest import REDIS_NAMESPACE, RUN_ID, TEST_DB, clear_run_keys


def test_shared_resource_names_are_per_run():
    assert RUN_ID, "every run needs an id"
    assert TEST_DB == f"nur_test_{RUN_ID}", "database name must be per-run"
    assert TEST_DB != "nur_test", "a fixed database name lets concurrent runs drop each other"
    assert REDIS_NAMESPACE == f"nurtest:{RUN_ID}"
    assert get_settings().redis_key_namespace == REDIS_NAMESPACE


def test_limiter_keys_carry_the_run_namespace():
    key = namespaced("rl:login:127.0.0.1:fp")
    assert key.startswith(f"{REDIS_NAMESPACE}:"), "an unnamespaced key is shared with every other run"


async def test_foreign_run_cleanup_cannot_clear_this_run_state(client):
    """A second run's cleanup deletes only its own keys."""
    redis: Redis = client.app.state.redis
    mine = namespaced("rl:login:127.0.0.1:isolation-probe")
    foreign_namespace = f"nurtest:foreign-{RUN_ID}"
    theirs = f"{foreign_namespace}:rl:login:127.0.0.1:isolation-probe"

    await redis.set(mine, 7)
    await redis.set(theirs, 7)

    # The other run tears down exactly the way this run does.
    deleted = await clear_run_keys(redis, foreign_namespace)

    assert deleted == 1, "foreign cleanup should remove only the foreign key"
    assert await redis.get(mine) == "7", "this run's limiter state must survive another run's cleanup"
    assert await redis.get(theirs) is None

    await redis.delete(mine)


async def test_foreign_run_traffic_cannot_reopen_a_closed_window(client):
    """Exhausting the limiter in a foreign namespace leaves this run's window closed.

    This is the exact corruption that produced the phantom failures: a foreign run
    burning through its own budget must not hand this run a fresh allowance.
    """
    redis: Redis = client.app.state.redis
    settings = get_settings()
    ip, fingerprint = "203.0.113.7", "isolation-fp"

    for _ in range(settings.login_rate_limit_max):
        assert await allow_login(redis, ip=ip, email_fp=fingerprint) is True
    assert await allow_login(redis, ip=ip, email_fp=fingerprint) is False, "window should now be closed"

    # A concurrent run: same server, same logical bucket, different namespace.
    foreign_namespace = f"nurtest:foreign-{RUN_ID}"
    original = settings.redis_key_namespace
    try:
        settings.redis_key_namespace = foreign_namespace
        for _ in range(settings.login_rate_limit_max + 1):
            await allow_login(redis, ip=ip, email_fp=fingerprint)
        await clear_run_keys(redis, foreign_namespace)
    finally:
        settings.redis_key_namespace = original

    assert await allow_login(redis, ip=ip, email_fp=fingerprint) is False, (
        "a foreign run's traffic and cleanup must not reopen this run's rate-limit window"
    )

    await redis.delete(namespaced(f"rl:login:{ip}:{fingerprint}"))


def test_client_fixture_does_not_flush_the_server():
    """`flushdb` is server-wide: it would delete every concurrent run's keys."""
    conftest_source = os.path.join(os.path.dirname(__file__), "conftest.py")
    with open(conftest_source, encoding="utf-8") as handle:
        source = handle.read()
    active = [line for line in source.splitlines() if ".flushdb(" in line]
    assert active == [], f"conftest must not call flushdb; found: {active}"


@pytest.mark.parametrize("script", ["flushall", "flushdb"])
def test_no_server_wide_redis_wipe_anywhere_in_the_suite(script):
    tests_dir = os.path.dirname(__file__)
    offenders = []
    for name in os.listdir(tests_dir):
        if not name.endswith(".py") or name == os.path.basename(__file__):
            continue
        with open(os.path.join(tests_dir, name), encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                # Match the call itself, so prose describing the hazard is allowed.
                if f".{script}(" in line:
                    offenders.append(f"{name}:{number}")
    assert offenders == [], f"server-wide redis {script} breaks run isolation: {offenders}"
