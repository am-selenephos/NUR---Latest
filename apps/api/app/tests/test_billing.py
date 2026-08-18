import datetime as dt
import hashlib
import hmac
import json
import uuid

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import text

from app.billing.providers import (
    BillingProviderError,
    CheckoutRequest,
    LemonSqueezyBillingProvider,
)
from app.billing.service import checkout_binding
from app.core.config import Settings, get_settings
from app.tests.conftest import register_user


def H(client, **extra: str) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf"), **extra}


def configure_test_billing():
    settings = get_settings()
    settings.billing_provider = "test"
    settings.billing_test_mode = True
    settings.billing_live_enabled = False
    settings.billing_webhook_secret = SecretStr("test-webhook-secret-at-least-24-characters")
    settings.billing_terms_url = "https://nur.example/terms"
    settings.billing_privacy_url = "https://nur.example/privacy"
    settings.billing_refund_policy_url = "https://nur.example/refunds"
    return settings


async def create_test_checkout(client, *, plan_code: str = "founding_orbit"):
    response = await client.post(
        "/api/v1/billing/checkout",
        headers=H(client, **{"Idempotency-Key": f"checkout-{uuid.uuid4().hex}"}),
        json={"plan_code": plan_code},
    )
    assert response.status_code == 201, response.text
    return response.json()


def webhook_payload(
    *,
    settings,
    owner_user_id: str,
    checkout_session_id: str,
    event_name: str,
    event_id: str,
    event_at: dt.datetime,
    status: str,
    subscription_id: str | None = None,
    plan_code: str = "founding_orbit",
    ends_at: dt.datetime | None = None,
    resource_type: str = "subscriptions",
    resource_id: str | None = None,
) -> dict:
    subscription_id = subscription_id or f"test_subscription_{owner_user_id}"
    attributes = {
        "status": status,
        "variant_id": f"test:{plan_code}",
        "customer_id": f"test_customer_{owner_user_id}",
        "subscription_id": subscription_id,
        "created_at": event_at.isoformat(),
        "updated_at": event_at.isoformat(),
        "renews_at": (event_at + dt.timedelta(days=30)).isoformat(),
    }
    if ends_at is not None:
        attributes["ends_at"] = ends_at.isoformat()
    owner_uuid = uuid.UUID(owner_user_id)
    checkout_uuid = uuid.UUID(checkout_session_id)
    custom = {
        "nur_owner_user_id": owner_user_id,
        "nur_checkout_session_id": checkout_session_id,
        "nur_plan_code": plan_code,
        "nur_binding": checkout_binding(
            settings,
            provider="test",
            owner_user_id=owner_uuid,
            checkout_session_id=checkout_uuid,
            plan_code=plan_code,
        ),
    }
    return {
        "meta": {
            "event_name": event_name,
            "event_id": event_id,
            "test_mode": True,
            "custom_data": custom,
        },
        "data": {
            "type": resource_type,
            "id": resource_id or subscription_id,
            "attributes": attributes,
        },
    }


async def send_webhook(client, settings, payload: dict, *, signature: str | None = None):
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    if signature is None:
        signature = hmac.new(
            settings.billing_webhook_secret.get_secret_value().encode(),
            raw,
            hashlib.sha256,
        ).hexdigest()
    return await client.post(
        "/api/v1/billing/webhooks/test",
        content=raw,
        headers={"Content-Type": "application/json", "X-Signature": signature},
    )


async def test_plan_catalog_and_disabled_checkout_are_truthful(client):
    plans = await client.get("/api/v1/billing/plans")
    assert plans.status_code == 200
    by_code = {item["code"]: item for item in plans.json()}
    assert set(by_code) == {
        "orbit_scan_free",
        "founding_orbit",
        "nur_plus_monthly",
        "nur_plus_annual",
    }
    assert by_code["founding_orbit"]["price_minor"] == 9900
    assert by_code["founding_orbit"]["seat_cap"] == 50
    assert by_code["founding_orbit"]["seats_remaining"] == 50
    assert by_code["nur_plus_monthly"]["price_minor"] == 1299
    assert by_code["nur_plus_annual"]["price_minor"] == 12900
    founding_features = {
        item["feature_key"]: item for item in by_code["founding_orbit"]["features"]
    }
    assert founding_features["paid_continuity"]["allowed"] is True
    assert founding_features["ai.daily_requests"]["usage_limit"] == 200

    await register_user(client)
    no_csrf = await client.post(
        "/api/v1/billing/checkout",
        headers={"Idempotency-Key": "disabled-checkout"},
        json={"plan_code": "founding_orbit"},
    )
    assert no_csrf.status_code == 403
    disabled = await client.post(
        "/api/v1/billing/checkout",
        headers=H(client, **{"Idempotency-Key": "disabled-checkout"}),
        json={"plan_code": "founding_orbit"},
    )
    assert disabled.status_code == 503


async def test_checkout_is_idempotent_and_grants_nothing_before_webhook(
    client, super_engine
):
    registered, _, _ = await register_user(client)
    owner = registered.json()["id"]
    configure_test_billing()
    key = f"checkout-{uuid.uuid4().hex}"
    headers = H(client, **{"Idempotency-Key": key})
    first = await client.post(
        "/api/v1/billing/checkout",
        headers=headers,
        json={"plan_code": "founding_orbit"},
    )
    replay = await client.post(
        "/api/v1/billing/checkout",
        headers=headers,
        json={"plan_code": "founding_orbit"},
    )
    assert first.status_code == replay.status_code == 201
    assert first.json()["session_id"] == replay.json()["session_id"]
    assert first.json()["checkout_url"].startswith("https://billing.test/")
    assert first.json()["is_test"] is True
    assert first.json()["renews_automatically"] is True

    state = await client.get("/api/v1/billing/subscription")
    assert state.status_code == 200
    assert state.json()["subscription"] is None
    assert state.json()["entitlements"] == []

    wrong_plan = await client.post(
        "/api/v1/billing/checkout",
        headers=headers,
        json={"plan_code": "nur_plus_monthly"},
    )
    assert wrong_plan.status_code == 409
    parallel_checkout = await client.post(
        "/api/v1/billing/checkout",
        headers=H(
            client,
            **{"Idempotency-Key": f"parallel-{uuid.uuid4().hex}"},
        ),
        json={"plan_code": "nur_plus_monthly"},
    )
    assert parallel_checkout.status_code == 409
    assert "unexpired checkout" in parallel_checkout.json()["detail"]
    async with super_engine.connect() as connection:
        counts = (
            await connection.execute(
                text(
                    "SELECT "
                    "(SELECT count(*) FROM billing_checkout_sessions WHERE owner_user_id=:owner), "
                    "(SELECT count(*) FROM billing_subscriptions WHERE owner_user_id=:owner), "
                    "(SELECT count(*) FROM billing_entitlements WHERE owner_user_id=:owner)"
                ),
                {"owner": owner},
            )
        ).one()
    assert tuple(counts) == (1, 0, 0)
    async with super_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE billing_checkout_sessions SET reservation_expires_at=now() - interval '1 minute' "
                "WHERE owner_user_id=:owner"
            ),
            {"owner": owner},
        )
    replacement = await client.post(
        "/api/v1/billing/checkout",
        headers=H(
            client,
            **{"Idempotency-Key": f"replacement-{uuid.uuid4().hex}"},
        ),
        json={"plan_code": "nur_plus_monthly"},
    )
    assert replacement.status_code == 201
    async with super_engine.connect() as connection:
        statuses = (
            await connection.execute(
                text(
                    "SELECT status FROM billing_checkout_sessions "
                    "WHERE owner_user_id=:owner ORDER BY created_at"
                ),
                {"owner": owner},
            )
        ).scalars().all()
    assert statuses == ["EXPIRED", "CREATED"]


async def test_signature_binding_replay_persistence_and_portal(
    client, super_engine
):
    registered, email, password = await register_user(client)
    owner = registered.json()["id"]
    settings = configure_test_billing()
    checkout = await create_test_checkout(client)
    event_at = dt.datetime.now(dt.UTC).replace(microsecond=0)
    payload = webhook_payload(
        settings=settings,
        owner_user_id=owner,
        checkout_session_id=checkout["session_id"],
        event_name="subscription_created",
        event_id=f"event-{uuid.uuid4().hex}",
        event_at=event_at,
        status="active",
    )
    order = webhook_payload(
        settings=settings,
        owner_user_id=owner,
        checkout_session_id=checkout["session_id"],
        event_name="order_created",
        event_id=f"event-{uuid.uuid4().hex}",
        event_at=event_at,
        status="paid",
        resource_type="orders",
        resource_id="test_order_initial",
    )
    order["data"]["attributes"].update(
        {
            "subtotal": 9900,
            "currency": "usd",
            "urls": {
                "receipt": "https://billing.test/receipts/test_order_initial"
            },
        }
    )

    rejected = await send_webhook(client, settings, payload, signature="0" * 64)
    assert rejected.status_code == 400
    tampered = json.loads(json.dumps(payload))
    tampered["meta"]["custom_data"]["nur_plan_code"] = "nur_plus_annual"
    rejected_binding = await send_webhook(client, settings, tampered)
    assert rejected_binding.status_code == 422
    assert "ownership binding" in rejected_binding.json()["detail"]
    client.cookies.clear()
    recorded_order = await send_webhook(client, settings, order)
    assert recorded_order.status_code == 200
    assert recorded_order.json()["outcome_code"] == "ORDER_RECORDED"
    accepted = await send_webhook(client, settings, payload)
    assert accepted.status_code == 200
    assert accepted.json() == {
        "accepted": True,
        "duplicate": False,
        "processing_status": "PROCESSED",
        "outcome_code": "SUBSCRIPTION_PROJECTED",
    }
    replay = await send_webhook(client, settings, payload)
    assert replay.status_code == 200
    assert replay.json()["duplicate"] is True

    unauthenticated_state = await client.get("/api/v1/billing/subscription")
    assert unauthenticated_state.status_code == 401
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200

    state = await client.get("/api/v1/billing/subscription")
    assert state.status_code == 200
    assert state.json()["subscription"]["status"] == "active"
    assert state.json()["subscription"]["latest_receipt_url"].endswith(
        "/test_order_initial"
    )
    entitlements = {item["feature_key"]: item for item in state.json()["entitlements"]}
    assert entitlements["paid_continuity"]["allowed"] is True
    assert entitlements["ai.daily_requests"]["usage_limit"] == 200
    assert state.json()["portal_available"] is True

    duplicate_subscription = await client.post(
        "/api/v1/billing/checkout",
        headers=H(
            client,
            **{"Idempotency-Key": f"second-subscription-{uuid.uuid4().hex}"},
        ),
        json={"plan_code": "nur_plus_monthly"},
    )
    assert duplicate_subscription.status_code == 409
    assert "existing subscription" in duplicate_subscription.json()["detail"]

    portal = await client.post("/api/v1/billing/portal", headers=H(client))
    assert portal.status_code == 200
    assert portal.json()["url"].startswith("https://billing.test/portal/")
    assert portal.json()["purpose"] == "MANAGE_CANCEL_INVOICES"

    client.cookies.clear()
    relogin = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert relogin.status_code == 200
    retained = await client.get("/api/v1/billing/subscription")
    assert retained.json()["subscription"]["status"] == "active"
    assert any(item["allowed"] for item in retained.json()["entitlements"])

    async with super_engine.connect() as connection:
        receipts = (
            await connection.execute(
                text(
                    "SELECT payload_digest, signature_digest, processing_status "
                    "FROM billing_webhook_receipts WHERE owner_user_id=:owner"
                ),
                {"owner": owner},
            )
        ).all()
        event_payload = (
            await connection.execute(
                text(
                    "SELECT event_payload::text FROM domain_events "
                    "WHERE owner_user_id=:owner AND event_type='subscription.changed'"
                ),
                {"owner": owner},
            )
        ).scalar_one()
    assert len(receipts) == 2
    assert all(
        len(receipt.payload_digest) == len(receipt.signature_digest) == 64
        and receipt.processing_status == "PROCESSED"
        for receipt in receipts
    )
    assert email not in event_payload
    assert "test_customer_1" not in event_payload


async def test_out_of_order_event_cannot_resurrect_expired_access(client):
    registered, _, _ = await register_user(client)
    owner = registered.json()["id"]
    settings = configure_test_billing()
    checkout = await create_test_checkout(client)
    base = dt.datetime.now(dt.UTC).replace(microsecond=0)
    created = webhook_payload(
        settings=settings,
        owner_user_id=owner,
        checkout_session_id=checkout["session_id"],
        event_name="subscription_created",
        event_id=f"event-{uuid.uuid4().hex}",
        event_at=base,
        status="active",
    )
    expired = webhook_payload(
        settings=settings,
        owner_user_id=owner,
        checkout_session_id=checkout["session_id"],
        event_name="subscription_expired",
        event_id=f"event-{uuid.uuid4().hex}",
        event_at=base + dt.timedelta(minutes=10),
        status="expired",
    )
    stale_active = webhook_payload(
        settings=settings,
        owner_user_id=owner,
        checkout_session_id=checkout["session_id"],
        event_name="subscription_updated",
        event_id=f"event-{uuid.uuid4().hex}",
        event_at=base + dt.timedelta(minutes=5),
        status="active",
    )
    assert (await send_webhook(client, settings, created)).status_code == 200
    assert (await send_webhook(client, settings, expired)).status_code == 200
    ignored = await send_webhook(client, settings, stale_active)
    assert ignored.status_code == 200
    assert ignored.json()["outcome_code"] == "STALE_EVENT"

    state = (await client.get("/api/v1/billing/subscription")).json()
    assert state["subscription"]["status"] == "expired"
    assert all(not item["allowed"] for item in state["entitlements"])
    assert state["portal_available"] is False


async def test_cancel_grace_then_refund_revokes_and_records_state(client):
    registered, _, _ = await register_user(client)
    owner = registered.json()["id"]
    settings = configure_test_billing()
    checkout = await create_test_checkout(client)
    base = dt.datetime.now(dt.UTC).replace(microsecond=0)
    created = webhook_payload(
        settings=settings,
        owner_user_id=owner,
        checkout_session_id=checkout["session_id"],
        event_name="subscription_created",
        event_id=f"event-{uuid.uuid4().hex}",
        event_at=base,
        status="active",
    )
    cancelled = webhook_payload(
        settings=settings,
        owner_user_id=owner,
        checkout_session_id=checkout["session_id"],
        event_name="subscription_cancelled",
        event_id=f"event-{uuid.uuid4().hex}",
        event_at=base + dt.timedelta(minutes=1),
        status="cancelled",
        ends_at=base + dt.timedelta(days=20),
    )
    partial_refund = webhook_payload(
        settings=settings,
        owner_user_id=owner,
        checkout_session_id=checkout["session_id"],
        event_name="order_refunded",
        event_id=f"event-{uuid.uuid4().hex}",
        event_at=base + dt.timedelta(minutes=2),
        status="partial_refund",
        resource_type="orders",
        resource_id="test_order_1",
    )
    partial_refund["data"]["attributes"].update(
        {
            "refund_id": "test_refund_partial",
            "refunded": False,
            "refunded_amount": 1000,
            "total": 9900,
            "currency": "usd",
        }
    )
    refunded = webhook_payload(
        settings=settings,
        owner_user_id=owner,
        checkout_session_id=checkout["session_id"],
        event_name="order_refunded",
        event_id=f"event-{uuid.uuid4().hex}",
        event_at=base + dt.timedelta(minutes=3),
        status="refunded",
        resource_type="orders",
        resource_id="test_order_1",
    )
    refunded["data"]["attributes"].update(
        {
            "refund_id": "test_refund_1",
            "refunded": True,
            "refunded_amount": 9900,
            "total": 9900,
            "currency": "usd",
        }
    )
    await send_webhook(client, settings, created)
    await send_webhook(client, settings, cancelled)
    grace = (await client.get("/api/v1/billing/subscription")).json()
    assert grace["subscription"]["status"] == "cancel_at_period_end"
    assert all(item["allowed"] for item in grace["entitlements"])

    partial = await send_webhook(client, settings, partial_refund)
    assert partial.status_code == 200
    assert partial.json()["outcome_code"] == "PARTIAL_REFUND_RECORDED"
    partial_state = (await client.get("/api/v1/billing/subscription")).json()
    assert partial_state["subscription"]["status"] == "cancel_at_period_end"
    assert all(item["allowed"] for item in partial_state["entitlements"])
    assert partial_state["refunds"][0]["status"] == "PARTIALLY_REFUNDED"

    response = await send_webhook(client, settings, refunded)
    assert response.status_code == 200
    final = (await client.get("/api/v1/billing/subscription")).json()
    assert final["subscription"]["status"] == "refunded"
    assert all(not item["allowed"] for item in final["entitlements"])
    assert final["refunds"][0]["status"] == "REFUNDED"
    assert final["refunds"][0]["amount_minor"] == 9900


async def test_billing_rows_are_owner_isolated_at_rls_layer(
    client, app_engine
):
    first, _, _ = await register_user(client)
    owner_a = first.json()["id"]
    settings = configure_test_billing()
    checkout = await create_test_checkout(client)
    event_at = dt.datetime.now(dt.UTC).replace(microsecond=0)
    await send_webhook(
        client,
        settings,
        webhook_payload(
            settings=settings,
            owner_user_id=owner_a,
            checkout_session_id=checkout["session_id"],
            event_name="subscription_created",
            event_id=f"event-{uuid.uuid4().hex}",
            event_at=event_at,
            status="active",
        ),
    )
    second, _, _ = await register_user(client)
    owner_b = second.json()["id"]
    async with app_engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :owner, true)"),
            {"owner": owner_b},
        )
        private_counts = []
        for table_name in (
            "billing_checkout_sessions",
            "billing_customers",
            "billing_subscriptions",
            "billing_entitlements",
            "billing_entitlement_events",
            "billing_webhook_receipts",
        ):
            private_counts.append(
                (
                    await connection.execute(
                        text(f"SELECT count(*) FROM {table_name}")
                    )
                ).scalar_one()
            )
        public_plans = (
            await connection.execute(text("SELECT count(*) FROM billing_plans"))
        ).scalar_one()
    assert private_counts == [0, 0, 0, 0, 0, 0]
    assert public_plans == 4


async def test_founding_orbit_real_seat_cap_is_server_enforced(
    client, super_engine, monkeypatch
):
    await register_user(client)
    settings = configure_test_billing()
    settings.billing_provider = "lemon_squeezy"
    settings.billing_test_mode = False
    settings.billing_live_enabled = True

    class NeverCalledProvider:
        name = "lemon_squeezy"

        async def create_checkout(self, request):
            del request
            raise AssertionError("A sold-out plan must not reach the payment provider.")

        async def customer_portal_url(self, provider_subscription_id):
            del provider_subscription_id
            raise AssertionError("Not used in this test.")

    monkeypatch.setattr(
        "app.billing.service.build_billing_provider",
        lambda configured: NeverCalledProvider(),
    )
    now = dt.datetime.now(dt.UTC)
    async with super_engine.begin() as connection:
        await connection.execute(
            text(
                "WITH capacity_users AS ("
                "INSERT INTO users (id, email, password_hash) "
                "SELECT gen_random_uuid(), 'capacity-' || value || '@nur.example', "
                "'not-a-login-hash' FROM generate_series(1, 50) AS value "
                "RETURNING id), numbered AS ("
                "SELECT id, row_number() OVER () AS value FROM capacity_users) "
                "INSERT INTO billing_subscriptions ("
                "owner_user_id, plan_code, provider, provider_subscription_id, "
                "provider_status, status, is_test, last_provider_event_at, "
                "last_provider_event_rank, last_provider_event_key"
                ") SELECT id, 'founding_orbit', 'lemon_squeezy', "
                "'capacity-sub-' || value, 'active', 'active', false, :now, 10, "
                "'capacity-event-' || value FROM numbered"
            ),
            {"now": now},
        )
    plans = await client.get("/api/v1/billing/plans")
    founding = next(item for item in plans.json() if item["code"] == "founding_orbit")
    assert founding["seats_remaining"] == 0

    blocked = await client.post(
        "/api/v1/billing/checkout",
        headers=H(client, **{"Idempotency-Key": f"sold-out-{uuid.uuid4().hex}"}),
        json={"plan_code": "founding_orbit"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "This limited plan is sold out."


def test_billing_configuration_fails_closed():
    with pytest.raises(ValidationError, match="WEBHOOK"):
        Settings(billing_provider="test")
    with pytest.raises(ValidationError, match="requires NUR_BILLING_TEST_MODE"):
        Settings(
            billing_provider="test",
            billing_test_mode=False,
            billing_live_enabled=True,
            billing_webhook_secret="x" * 32,
        )
    with pytest.raises(ValidationError, match="NUR_BILLING_LIVE_ENABLED"):
        Settings(
            billing_provider="lemon_squeezy",
            billing_test_mode=False,
            billing_live_enabled=False,
            billing_webhook_secret="w" * 32,
            billing_terms_url="https://nur.example/terms",
            billing_privacy_url="https://nur.example/privacy",
            billing_refund_policy_url="https://nur.example/refunds",
            lemon_squeezy_api_key="server-only-" + "api-key",
            lemon_squeezy_store_id="123",
            lemon_squeezy_founding_orbit_variant_id="456",
            lemon_squeezy_plus_monthly_variant_id="457",
            lemon_squeezy_plus_annual_variant_id="458",
        )
    with pytest.raises(ValidationError, match="cannot run in production"):
        Settings(
            app_env="production",
            session_secret="s" * 32,
            csrf_secret="c" * 32,
            web_origin="https://nur.example",
            password_reset_public_origin="https://nur.example",
            password_reset_delivery="smtp",
            password_reset_from_email="security@nur.example",
            password_reset_smtp_host="smtp.nur.example",
            billing_provider="test",
            billing_webhook_secret="w" * 32,
        )


async def test_lemon_provider_binds_expiry_variant_and_catalog_price(monkeypatch):
    settings = Settings(
        billing_provider="lemon_squeezy",
        billing_test_mode=True,
        billing_webhook_secret="w" * 32,
        billing_terms_url="https://nur.example/terms",
        billing_privacy_url="https://nur.example/privacy",
        billing_refund_policy_url="https://nur.example/refunds",
        lemon_squeezy_api_key="server-only-" + "api-key",
        lemon_squeezy_store_id="123",
        lemon_squeezy_founding_orbit_variant_id="456",
        lemon_squeezy_plus_monthly_variant_id="457",
        lemon_squeezy_plus_annual_variant_id="458",
    )
    observed = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": {
                    "id": "checkout_1",
                    "attributes": {
                        "url": "https://store.lemonsqueezy.com/checkout/checkout_1",
                        "preview": {"subtotal": 9900, "currency": "USD"},
                    },
                }
            }

    class FakeClient:
        def __init__(self, *, timeout):
            observed["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, *, headers, json):
            observed.update(url=url, headers=headers, payload=json)
            return FakeResponse()

    monkeypatch.setattr("app.billing.providers.httpx.AsyncClient", FakeClient)
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=30)
    request = CheckoutRequest(
        session_id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        plan_code="founding_orbit",
        customer_email="owner@nur.example",
        custom_data={"nur_binding": "bound"},
        redirect_url="https://nur.example/settings/billing",
        idempotency_key="checkout-idempotency",
        expires_at=expires_at,
        expected_price_minor=9900,
        expected_currency="USD",
    )
    result = await LemonSqueezyBillingProvider(settings).create_checkout(request)
    assert result.provider_checkout_id == "checkout_1"
    attributes = observed["payload"]["data"]["attributes"]
    assert attributes["expires_at"] == expires_at.isoformat()
    assert attributes["preview"] is True
    assert attributes["product_options"]["enabled_variants"] == [456]
    assert attributes["checkout_data"]["custom"] == {"nur_binding": "bound"}
    assert ("server-only-" + "api-key") not in json.dumps(observed["payload"])

    mismatched = CheckoutRequest(
        **{**request.__dict__, "expected_price_minor": 12900}
    )
    with pytest.raises(BillingProviderError, match="does not match"):
        await LemonSqueezyBillingProvider(settings).create_checkout(mismatched)
