import hashlib
import json
import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.services.object_storage import bytes_stream, get_object_storage
from app.tests.conftest import register_user


def _csrf(client: AsyncClient) -> dict[str, str]:
    token = client.cookies.get("nur_csrf")
    assert token
    return {"x-csrf-token": token}


def _session_id(client: AsyncClient) -> uuid.UUID:
    value = client.cookies.get("nur_session")
    assert value
    return uuid.UUID(value.split(".", 1)[0])


def _second_client(client: AsyncClient) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=client.app), base_url="http://test")


async def test_owner_export_is_deterministic_portable_and_owner_isolated(
    client, super_engine
):
    from app.services.account_service import canonical_json_bytes

    first, _, _ = await register_user(client, chosen_name="First owner")
    first_id = uuid.UUID(first.json()["id"])
    first_orbit = uuid.UUID(first.json()["orbit"]["id"])
    first_csrf = _csrf(client)

    async with _second_client(client) as other:
        second, _, _ = await register_user(other, chosen_name="Second owner")
        second_id = uuid.UUID(second.json()["id"])

        project_id = uuid.uuid4()
        storage = get_object_storage()
        stored = await storage.put(bytes_stream(b"NUR\n"), max_bytes=1024)
        async with super_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO plans(id,owner_user_id,title,status) VALUES "
                    "(:first_plan,:first_id,'portable first plan','ACTIVE'),"
                    "(:second_plan,:second_id,'foreign second plan','ACTIVE')"
                ),
                {
                    "first_plan": uuid.uuid4(),
                    "first_id": first_id,
                    "second_plan": uuid.uuid4(),
                    "second_id": second_id,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO am_projects(id,owner_user_id,orbit_id,title,objective,status) "
                    "VALUES (:project,:owner,:orbit,'Portable project','Prove export','ACTIVE')"
                ),
                {"project": project_id, "owner": first_id, "orbit": first_orbit},
            )
            await conn.execute(
                text(
                    "INSERT INTO am_project_files("
                    "id,owner_user_id,project_id,object_key,original_filename,safe_filename,"
                    "media_type,byte_size,checksum_sha256,storage_backend,storage_state,"
                    "scan_state,provenance) VALUES ("
                    ":id,:owner,:project,:key,'notes.txt','notes.txt','text/plain',4,"
                    ":checksum,'local','STORED','SCAN_NOT_CONNECTED','OWNER_UPLOAD')"
                ),
                {
                    "id": uuid.uuid4(),
                    "owner": first_id,
                    "project": project_id,
                    "key": stored.object_key,
                    "checksum": stored.checksum_sha256,
                },
            )

        assert (await client.post("/api/v1/account/export")).status_code == 403
        cross_site = await client.post(
            "/api/v1/account/export",
            headers={
                **first_csrf,
                "origin": "https://attacker.example",
                "sec-fetch-site": "cross-site",
            },
        )
        assert cross_site.status_code == 403

        first_export = await client.post("/api/v1/account/export", headers=first_csrf)
        second_export = await client.post("/api/v1/account/export", headers=first_csrf)
        assert first_export.status_code == second_export.status_code == 200
        assert first_export.content == second_export.content
        assert first_export.headers["cache-control"] == "no-store"
        assert first_export.headers["content-disposition"] == (
            'attachment; filename="nur-owner-export-v1.json"'
        )

        manifest = first_export.json()
        assert manifest["schema"].endswith("/owner-export-manifest/v1")
        assert manifest["owner_user_id"] == str(first_id)
        checksum = manifest.pop("checksum")
        assert checksum["value"] == hashlib.sha256(
            canonical_json_bytes(manifest)
        ).hexdigest()
        assert first_export.headers["x-nur-export-checksum"] == checksum["value"]

        tables = {entry["name"]: entry for entry in manifest["tables"]}
        assert [row["title"] for row in tables["plans"]["rows"]] == [
            "portable first plan"
        ]
        assert manifest["objects"][0]["content"]["value"] == "TlVSCg=="
        body = first_export.text
        assert str(second_id) not in body
        assert "foreign second plan" not in body
        assert "password_hash" not in tables["users"]["rows"][0]
        assert all("session_secret_hash" not in row for row in tables["sessions"]["rows"])
        assert all(
            "receipt_token_digest" not in row
            for row in tables["account_deletion_requests"]["rows"]
        )
        assert all(
            "resource_ref" not in row
            for row in tables["account_cleanup_items"]["rows"]
        )
        assert storage.delete(stored.object_key) is True


async def test_session_inventory_and_revocation_are_owner_scoped(client, super_engine):
    registered, email, password = await register_user(client)
    owner_id = uuid.UUID(registered.json()["id"])
    first_session = _session_id(client)
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200
    second_session = _session_id(client)

    async with _second_client(client) as other:
        foreign, _, _ = await register_user(other, chosen_name="Foreign owner")
        foreign_id = uuid.UUID(foreign.json()["id"])
        foreign_session = _session_id(other)

        inventory = await client.get("/api/v1/auth/sessions")
        assert inventory.status_code == 200
        assert {row["id"] for row in inventory.json()["sessions"]} == {
            str(first_session),
            str(second_session),
        }
        assert [row["id"] for row in inventory.json()["sessions"] if row["current"]] == [
            str(second_session)
        ]

        assert (
            await client.delete(f"/api/v1/auth/sessions/{first_session}")
        ).status_code == 403
        assert (
            await client.delete(
                f"/api/v1/auth/sessions/{foreign_session}", headers=_csrf(client)
            )
        ).status_code == 404
        own = await client.delete(
            f"/api/v1/auth/sessions/{first_session}", headers=_csrf(client)
        )
        assert own.status_code == 200
        assert own.json() == {"revoked_session_count": 1}
        assert (
            await client.delete(
                f"/api/v1/auth/sessions/{second_session}", headers=_csrf(client)
            )
        ).status_code == 400

        async with super_engine.connect() as conn:
            assert (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM sessions "
                        "WHERE user_id=:owner AND revoked_at IS NULL"
                    ),
                    {"owner": foreign_id},
                )
            ).scalar_one() == 1
            assert (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM sessions "
                        "WHERE user_id=:owner AND revoked_at IS NULL"
                    ),
                    {"owner": owner_id},
                )
            ).scalar_one() == 1


async def test_capsule_actor_reference_is_erased_with_recipient(client, super_engine):
    owner, _, _ = await register_user(client, chosen_name="Capsule owner")
    owner_id = uuid.UUID(owner.json()["id"])
    orbit_id = uuid.UUID(owner.json()["orbit"]["id"])
    async with _second_client(client) as recipient_client:
        recipient, _, _ = await register_user(
            recipient_client, chosen_name="Capsule recipient"
        )
        recipient_id = uuid.UUID(recipient.json()["id"])

    capsule_id, grant_id, event_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with super_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO context_capsules("
                "id,orbit_id,owner_user_id,title,purpose) "
                "VALUES (:capsule,:orbit,:owner,'Bounded capsule','Deletion proof')"
            ),
            {"capsule": capsule_id, "orbit": orbit_id, "owner": owner_id},
        )
        await conn.execute(
            text(
                "INSERT INTO capsule_grants(id,capsule_id,recipient_user_id) "
                "VALUES (:grant,:capsule,:recipient)"
            ),
            {"grant": grant_id, "capsule": capsule_id, "recipient": recipient_id},
        )
        await conn.execute(
            text(
                "INSERT INTO capsule_access_events("
                "id,capsule_id,grant_id,actor_user_id,event_kind) "
                "VALUES (:event,:capsule,:grant,:recipient,'VIEWED')"
            ),
            {
                "event": event_id,
                "capsule": capsule_id,
                "grant": grant_id,
                "recipient": recipient_id,
            },
        )
        await conn.execute(
            text("DELETE FROM users WHERE id=:recipient"),
            {"recipient": recipient_id},
        )
        actor, grant = (
            await conn.execute(
                text(
                    "SELECT actor_user_id, grant_id FROM capsule_access_events "
                    "WHERE id=:event"
                ),
                {"event": event_id},
            )
        ).one()
    assert actor is None
    assert grant is None


async def test_deletion_request_shuts_access_immediately_and_can_be_cancelled(
    client, super_engine
):
    registered, email, password = await register_user(client, chosen_name="Grace owner")
    owner_id = uuid.UUID(registered.json()["id"])
    orbit_id = uuid.UUID(registered.json()["orbit"]["id"])
    workflow_id, step_id, project_id, run_id = (
        uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    )
    async with super_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO agent_workflows(id,owner_user_id,kind,title,objective,state) "
                "VALUES (:workflow,:owner,'OWNER_DEFINED','Deletion fence','Stop safely','QUEUED')"
            ),
            {"workflow": workflow_id, "owner": owner_id},
        )
        await conn.execute(
            text(
                "INSERT INTO agent_steps(id,owner_user_id,workflow_id,ordinal,key,state,role) "
                "VALUES (:step,:owner,:workflow,1,'bounded_step','QUEUED','researcher')"
            ),
            {"step": step_id, "owner": owner_id, "workflow": workflow_id},
        )
        await conn.execute(
            text(
                "INSERT INTO agent_dispatch_outbox("
                "owner_user_id,workflow_id,step_id,dispatch_key,state) "
                "VALUES (:owner,:workflow,:step,:key,'RETRYABLE')"
            ),
            {
                "owner": owner_id,
                "workflow": workflow_id,
                "step": step_id,
                "key": f"{step_id}:0",
            },
        )
        await conn.execute(
            text(
                "INSERT INTO am_projects(id,owner_user_id,orbit_id,title,objective,status) "
                "VALUES (:project,:owner,:orbit,'Deletion project','Stop safely','ACTIVE')"
            ),
            {"project": project_id, "owner": owner_id, "orbit": orbit_id},
        )
        await conn.execute(
            text(
                "INSERT INTO am_project_runs("
                "id,owner_user_id,project_id,role,request_summary,status) "
                "VALUES (:run,:owner,:project,'researcher','Bounded run','QUEUED')"
            ),
            {"run": run_id, "owner": owner_id, "project": project_id},
        )

    assert (
        await client.request(
            "DELETE",
            "/api/v1/account",
            json={"password": password, "confirmation": "DELETE MY NUR ACCOUNT"},
        )
    ).status_code == 403
    requested = await client.request(
        "DELETE",
        "/api/v1/account",
        headers=_csrf(client),
        json={"password": password, "confirmation": "DELETE MY NUR ACCOUNT"},
    )
    assert requested.status_code == 202
    deletion = requested.json()
    assert deletion["status"] == "PENDING"
    assert deletion["immediate_access_shutdown"] is True
    assert deletion["receipt_token"]
    assert client.cookies.get("nur_session") is None
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
    ).status_code == 401

    async with super_engine.connect() as conn:
        user_status = (
            await conn.execute(
                text("SELECT status FROM users WHERE id=:owner"), {"owner": owner_id}
            )
        ).scalar_one()
        request_status = (
            await conn.execute(
                text(
                    "SELECT status FROM account_deletion_requests "
                    "WHERE id=:request_id"
                ),
                {"request_id": uuid.UUID(deletion["request_id"])},
            )
        ).scalar_one()
        active_sessions = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM sessions "
                    "WHERE user_id=:owner AND revoked_at IS NULL"
                ),
                {"owner": owner_id},
            )
        ).scalar_one()
        execution_states = (
            await conn.execute(
                text(
                    "SELECT "
                    "(SELECT state FROM agent_workflows WHERE id=:workflow),"
                    "(SELECT state FROM agent_steps WHERE id=:step),"
                    "(SELECT state FROM agent_dispatch_outbox WHERE workflow_id=:workflow),"
                    "(SELECT status FROM am_project_runs WHERE id=:run)"
                ),
                {
                    "workflow": workflow_id,
                    "step": step_id,
                    "run": run_id,
                },
            )
        ).one()
    assert (user_status, request_status, active_sessions) == ("deletion_pending", "PENDING", 0)
    assert tuple(execution_states) == (
        "CANCELLED",
        "CANCELLED",
        "CANCELLED",
        "CANCELLED",
    )

    cross_site = await client.post(
        "/api/v1/account/deletion/cancel",
        headers={
            "origin": "https://attacker.example",
            "sec-fetch-site": "cross-site",
        },
        json={
            "email": email,
            "password": password,
            "confirmation": "CANCEL ACCOUNT DELETION",
        },
    )
    assert cross_site.status_code == 403
    wrong = await client.post(
        "/api/v1/account/deletion/cancel",
        json={
            "email": email,
            "password": "wrong-owner-password",
            "confirmation": "CANCEL ACCOUNT DELETION",
        },
    )
    assert wrong.status_code == 400
    cancelled = await client.post(
        "/api/v1/account/deletion/cancel",
        json={
            "email": email,
            "password": password,
            "confirmation": "CANCEL ACCOUNT DELETION",
        },
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json() == {
        "cancelled": True,
        "status": "CANCELLED",
        "login_required": True,
    }
    assert (
        await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
    ).status_code == 200


async def test_scheduled_purge_is_idempotent_owner_isolated_and_receipted(
    client, super_engine
):
    from app.services.account_service import purge_due_account_deletions

    registered, _, password = await register_user(client, chosen_name="Purge owner")
    owner_id = uuid.UUID(registered.json()["id"])
    orbit_id = uuid.UUID(registered.json()["orbit"]["id"])
    storage = get_object_storage()
    stored = await storage.put(bytes_stream(b"erase after grace"), max_bytes=1024)
    project_id = uuid.uuid4()

    async with _second_client(client) as other:
        foreign, _, _ = await register_user(other, chosen_name="Keep owner")
        foreign_id = uuid.UUID(foreign.json()["id"])
        async with super_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO am_projects(id,owner_user_id,orbit_id,title,objective,status) "
                    "VALUES (:project,:owner,:orbit,'Private project','Delete me','ACTIVE')"
                ),
                {"project": project_id, "owner": owner_id, "orbit": orbit_id},
            )
            await conn.execute(
                text(
                    "INSERT INTO am_project_files("
                    "id,owner_user_id,project_id,object_key,original_filename,safe_filename,"
                    "media_type,byte_size,checksum_sha256,storage_backend,storage_state,"
                    "scan_state,provenance) VALUES ("
                    ":id,:owner,:project,:key,'private.txt','private.txt','text/plain',"
                    ":size,:checksum,'local','STORED','SCAN_NOT_CONNECTED','OWNER_UPLOAD')"
                ),
                {
                    "id": uuid.uuid4(),
                    "owner": owner_id,
                    "project": project_id,
                    "key": stored.object_key,
                    "size": stored.byte_size,
                    "checksum": stored.checksum_sha256,
                },
            )

        requested = await client.request(
            "DELETE",
            "/api/v1/account",
            headers=_csrf(client),
            json={"password": password, "confirmation": "DELETE MY NUR ACCOUNT"},
        )
        assert requested.status_code == 202
        deletion = requested.json()
        async with super_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE account_deletion_requests "
                    "SET purge_after=now() - interval '1 second' WHERE id=:id"
                ),
                {"id": uuid.UUID(deletion["request_id"])},
            )

        result = await purge_due_account_deletions()
        assert result["purged"] == 1
        assert result["failed_retryable"] == 0
        assert storage.exists(stored.object_key) is False
        assert (await purge_due_account_deletions())["processed"] == 0
        assert (await other.get("/api/v1/auth/me")).status_code == 200

        receipt = await client.post(
            "/api/v1/account/deletion/receipt",
            json={
                "request_id": deletion["request_id"],
                "receipt_token": deletion["receipt_token"],
            },
        )
        assert receipt.status_code == 200
        assert receipt.json()["status"] == "PURGED"
        assert receipt.json()["cleanup_summary"]["local_objects"]["done"] == 1
        assert (
            await client.post(
                "/api/v1/account/deletion/receipt",
                json={
                    "request_id": deletion["request_id"],
                    "receipt_token": "not-the-receipt-token",
                },
            )
        ).status_code == 404

        async with super_engine.connect() as conn:
            owner_count = (
                await conn.execute(
                    text("SELECT count(*) FROM users WHERE id=:id"), {"id": owner_id}
                )
            ).scalar_one()
            foreign_count = (
                await conn.execute(
                    text("SELECT count(*) FROM users WHERE id=:id"), {"id": foreign_id}
                )
            ).scalar_one()
            persisted = (
                await conn.execute(
                    text(
                        "SELECT owner_user_id,status,receipt_token_digest,cleanup_summary "
                        "FROM account_deletion_requests WHERE id=:id"
                    ),
                    {"id": uuid.UUID(deletion["request_id"])},
                )
            ).one()
        assert (owner_count, foreign_count) == (0, 1)
        assert persisted.owner_user_id is None
        assert persisted.status == "PURGED"
        assert persisted.receipt_token_digest != deletion["receipt_token"]
        assert str(owner_id) not in json.dumps(persisted.cleanup_summary)


async def test_object_cleanup_failure_retries_without_false_purge(
    client, super_engine, monkeypatch
):
    from app.services.account_service import purge_due_account_deletions

    registered, _, password = await register_user(client, chosen_name="Retry owner")
    owner_id = uuid.UUID(registered.json()["id"])
    orbit_id = uuid.UUID(registered.json()["orbit"]["id"])
    storage = get_object_storage()
    stored = await storage.put(bytes_stream(b"must eventually erase"), max_bytes=1024)
    project_id = uuid.uuid4()
    async with super_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO am_projects(id,owner_user_id,orbit_id,title,objective,status) "
                "VALUES (:project,:owner,:orbit,'Retry project','Retry purge','ACTIVE')"
            ),
            {"project": project_id, "owner": owner_id, "orbit": orbit_id},
        )
        await conn.execute(
            text(
                "INSERT INTO am_project_files("
                "id,owner_user_id,project_id,object_key,original_filename,safe_filename,"
                "media_type,byte_size,checksum_sha256,storage_backend,storage_state,"
                "scan_state,provenance) VALUES ("
                ":id,:owner,:project,:key,'retry.txt','retry.txt','text/plain',"
                ":size,:checksum,'local','STORED','SCAN_NOT_CONNECTED','OWNER_UPLOAD')"
            ),
            {
                "id": uuid.uuid4(),
                "owner": owner_id,
                "project": project_id,
                "key": stored.object_key,
                "size": stored.byte_size,
                "checksum": stored.checksum_sha256,
            },
        )

    requested = await client.request(
        "DELETE",
        "/api/v1/account",
        headers=_csrf(client),
        json={"password": password, "confirmation": "DELETE MY NUR ACCOUNT"},
    )
    request_id = uuid.UUID(requested.json()["request_id"])
    async with super_engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE account_deletion_requests "
                "SET purge_after=now() - interval '1 second' WHERE id=:id"
            ),
            {"id": request_id},
        )

    original_delete = storage.delete
    monkeypatch.setattr(storage, "delete", lambda _key: False)
    failed = await purge_due_account_deletions()
    assert failed["failed_retryable"] == 1
    assert failed["purged"] == 0
    async with super_engine.connect() as conn:
        assert (
            await conn.execute(
                text("SELECT status FROM users WHERE id=:owner"), {"owner": owner_id}
            )
        ).scalar_one() == "deletion_pending"
        request_state = (
            await conn.execute(
                text(
                    "SELECT status,failure_code FROM account_deletion_requests WHERE id=:id"
                ),
                {"id": request_id},
            )
        ).one()
    assert request_state.status == "PENDING"
    assert request_state.failure_code == "local_object_cleanup_failed"
    assert storage.exists(stored.object_key) is True

    monkeypatch.setattr(storage, "delete", original_delete)
    async with super_engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE account_deletion_requests "
                "SET purge_after=now() - interval '1 second' WHERE id=:id"
            ),
            {"id": request_id},
        )
    retried = await purge_due_account_deletions()
    assert retried["purged"] == 1
    assert storage.exists(stored.object_key) is False


async def test_account_privacy_routes_and_worker_schedule_are_registered(client):
    from app.workers.celery_app import celery

    paths = (await client.get("/openapi.json")).json()["paths"]
    assert "post" in paths["/api/v1/account/export"]
    assert "delete" in paths["/api/v1/account"]
    assert "post" in paths["/api/v1/account/deletion/cancel"]
    assert "post" in paths["/api/v1/account/deletion/receipt"]
    assert "get" in paths["/api/v1/auth/sessions"]
    assert "post" in paths["/api/v1/auth/sessions/revoke-others"]
    assert "delete" in paths["/api/v1/auth/sessions/{session_id}"]
    schedule = celery.conf.beat_schedule["nur-account-deletion-purge"]
    assert schedule["task"] == "nur.account_deletion_purge"
    assert schedule["schedule"] >= 60
