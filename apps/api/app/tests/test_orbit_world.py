"""The Orbit relational surface, through real HTTP against real PostgreSQL.

Orbit holds the most sensitive material in NUR — who matters to someone, and what
they believe about them — so the tests that matter most here are the refusals:
that an inference cannot become a fact, that a suggestion cannot become a move,
that a private person cannot be shared, and that no owner can see another's
relational world.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.tests.conftest import register_user

API = "/api/v1"


async def _csrf(client) -> dict:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf")}


async def _person(client, name="Ayesha", **extra) -> dict:
    body = {"display_name": name, "relationship_type": "Close friend", **extra}
    response = await client.post(f"{API}/orbits/people", json=body, headers=await _csrf(client))
    assert response.status_code == 201, response.text
    return response.json()


async def _patch(client, person_id, **fields):
    return await client.patch(
        f"{API}/orbit-entities/{person_id}", json=fields, headers=await _csrf(client)
    )


@pytest.fixture()
async def owner(client):
    response, email, password = await register_user(client)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


# ── entities and bands ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_new_person_starts_unplaced_and_closed(client, owner):
    """A person the owner just typed in has no band yet, and no permission they
    did not grant. Defaulting a band would be NUR deciding someone's importance."""
    person = await _person(client)
    got = await client.get(f"{API}/orbit-entities/{person['id']}")
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["orbit_level"] is None, "a new person was auto-placed into a band"
    assert body["memory_allowed"] is True
    assert body["inference_allowed"] is False
    assert body["sharing_allowed"] is False
    assert body["capsule_eligible"] is False


@pytest.mark.asyncio
async def test_the_owner_can_place_and_relabel_a_person(client, owner):
    person = await _person(client)
    response = await _patch(
        client, person["id"], orbit_level="INNER", relational_state="STABLE",
        tags=["family", "study"], user_summary="Knows the whole history.",
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["orbit_level"] == "INNER"
    assert body["relational_state"] == "STABLE"
    assert body["tags"] == ["family", "study"]
    assert body["user_summary"] == "Knows the whole history."


@pytest.mark.asyncio
async def test_an_unknown_band_is_refused(client, owner):
    person = await _person(client)
    response = await _patch(client, person["id"], orbit_level="BEST_FRIEND_FOREVER")
    assert response.status_code == 422, response.text
    assert "orbit_level" in response.text


@pytest.mark.asyncio
async def test_a_suggestion_never_moves_anyone(client, owner):
    """The core guardrail on bands: NUR may propose, and the proposal sits beside
    the placement rather than replacing it."""
    person = await _person(client)
    await _patch(client, person["id"], orbit_level="NEAR")

    suggested = await client.post(
        f"{API}/orbit-entities/{person['id']}/level-suggestion",
        json={
            "orbit_level_suggestion": "OUTER",
            "reason": "Activity has declined for 90 days. Organizational suggestion only.",
        },
        headers=await _csrf(client),
    )
    assert suggested.status_code == 200, suggested.text
    body = suggested.json()
    assert body["orbit_level"] == "NEAR", "a suggestion moved the person"
    assert body["orbit_level_suggestion"] == "OUTER"
    assert "90 days" in body["orbit_level_suggestion_reason"]


@pytest.mark.asyncio
async def test_a_suggestion_without_a_reason_is_refused(client, owner):
    """An unexplained suggested move is the silent reclassification this forbids."""
    person = await _person(client)
    response = await client.post(
        f"{API}/orbit-entities/{person['id']}/level-suggestion",
        json={"orbit_level_suggestion": "OUTER", "reason": ""},
        headers=await _csrf(client),
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_accepting_a_placement_clears_the_pending_suggestion(client, owner):
    person = await _person(client)
    await client.post(
        f"{API}/orbit-entities/{person['id']}/level-suggestion",
        json={"orbit_level_suggestion": "OUTER", "reason": "Quiet for a season."},
        headers=await _csrf(client),
    )
    answered = await _patch(client, person["id"], orbit_level="OUTER")
    assert answered.json()["orbit_level_suggestion"] is None, (
        "the interface would keep asking a question the owner already answered"
    )


@pytest.mark.asyncio
async def test_archiving_is_dormancy_not_deletion(client, owner):
    person = await _person(client)
    response = await client.post(
        f"{API}/orbit-entities/{person['id']}/archive", headers=await _csrf(client)
    )
    assert response.status_code == 200, response.text
    assert response.json()["archived_at"] is not None
    assert response.json()["orbit_level"] == "DORMANT"

    # Gone from the default field, still retrievable — the history survives.
    listed = await client.get(f"{API}/orbit-entities")
    assert person["id"] not in {row["id"] for row in listed.json()}
    with_archived = await client.get(f"{API}/orbit-entities?include_archived=true")
    assert person["id"] in {row["id"] for row in with_archived.json()}


# ── signals: the inference boundary ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_inferred_signal_is_refused_without_permission(client, owner):
    """`inference_allowed` is a stored permission, so "no inference beyond explicit
    notes" holds per person rather than being a UI preference."""
    person = await _person(client)
    response = await client.put(
        f"{API}/orbit-entities/{person['id']}/signals",
        json={
            "signal_kind": "TRUST", "basis": "NUR_INFERRED", "value": 40,
            "evidence": [{"kind": "TALK", "note": "two cancellations"}],
        },
        headers=await _csrf(client),
    )
    assert response.status_code == 403, response.text
    assert "inference is not permitted" in response.text


@pytest.mark.asyncio
async def test_an_inferred_signal_must_carry_evidence(client, owner):
    """Permitted is not the same as unevidenced. A reading with nothing behind it
    could not answer "Why is NUR showing this?"."""
    person = await _person(client)
    await _patch(client, person["id"], inference_allowed=True)
    response = await client.put(
        f"{API}/orbit-entities/{person['id']}/signals",
        json={"signal_kind": "TENSION", "basis": "NUR_INFERRED", "value": 60, "evidence": []},
        headers=await _csrf(client),
    )
    assert response.status_code == 422, response.text
    assert "evidence" in response.text


@pytest.mark.asyncio
async def test_a_stated_signal_needs_no_permission_and_no_evidence(client, owner):
    """The owner's own word about their own relationship is not an inference."""
    person = await _person(client)
    response = await client.put(
        f"{API}/orbit-entities/{person['id']}/signals",
        json={"signal_kind": "TRUST", "basis": "USER_STATED", "value": 90},
        headers=await _csrf(client),
    )
    assert response.status_code == 200, response.text
    assert response.json()["basis"] == "USER_STATED"


@pytest.mark.asyncio
async def test_stated_and_inferred_signals_coexist(client, owner):
    """They are different claims about the same thing and must not overwrite each
    other — the interface shows the owner's reading beside the model's."""
    person = await _person(client)
    await _patch(client, person["id"], inference_allowed=True)
    headers = await _csrf(client)
    for basis, value in (("USER_STATED", 90), ("NUR_INFERRED", 35)):
        body = {"signal_kind": "TRUST", "basis": basis, "value": value}
        if basis == "NUR_INFERRED":
            body["evidence"] = [{"kind": "TALK", "note": "two cancellations"}]
            body["contradictory_evidence"] = [{"kind": "JOURNAL", "note": "she was ill"}]
        response = await client.put(
            f"{API}/orbit-entities/{person['id']}/signals", json=body, headers=headers
        )
        assert response.status_code == 200, response.text

    signals = (await client.get(f"{API}/orbit-entities/{person['id']}/signals")).json()
    by_basis = {row["basis"]: row for row in signals}
    assert by_basis["USER_STATED"]["value"] == 90
    assert by_basis["NUR_INFERRED"]["value"] == 35
    assert by_basis["NUR_INFERRED"]["contradictory_evidence"], (
        "the case against a reading must be as durable as the case for it"
    )


@pytest.mark.asyncio
async def test_revoking_inference_removes_what_it_produced(client, owner):
    """Withdrawing permission has to delete the inferred readings, or they outlive
    their own consent."""
    person = await _person(client)
    await _patch(client, person["id"], inference_allowed=True)
    await client.put(
        f"{API}/orbit-entities/{person['id']}/signals",
        json={
            "signal_kind": "TENSION", "basis": "NUR_INFERRED", "value": 55,
            "evidence": [{"kind": "TALK", "note": "sharp exchange"}],
        },
        headers=await _csrf(client),
    )
    assert len((await client.get(f"{API}/orbit-entities/{person['id']}/signals")).json()) == 1

    await _patch(client, person["id"], inference_allowed=False)
    remaining = (await client.get(f"{API}/orbit-entities/{person['id']}/signals")).json()
    assert remaining == [], "inferred readings survived the withdrawal of consent"


# ── groups and Group NUR isolation ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_group_nur_cannot_run_on_a_private_organizer_view(client, owner):
    """Group NUR is a shared workspace. Enabling it on a private view would give
    a group assistant context no member agreed to share."""
    response = await client.post(
        f"{API}/orbit-groups",
        json={
            "name": "NUR Build Circle", "privacy_mode": "PRIVATE_ORGANIZER",
            "group_nur_enabled": True,
        },
        headers=await _csrf(client),
    )
    assert response.status_code == 422, response.text
    assert "shared" in response.text.lower()


@pytest.mark.asyncio
async def test_a_shared_context_group_may_enable_group_nur(client, owner):
    response = await client.post(
        f"{API}/orbit-groups",
        json={
            "name": "Creation Circle", "purpose": "Ship the portfolio",
            "privacy_mode": "SHARED_CONTEXT", "group_nur_enabled": True,
        },
        headers=await _csrf(client),
    )
    assert response.status_code == 201, response.text
    assert response.json()["group_nur_enabled"] is True


@pytest.mark.asyncio
async def test_a_private_person_cannot_join_with_shared_memory_consent(client, owner):
    """One member's consent cannot be assumed from the group's mode."""
    group = (
        await client.post(
            f"{API}/orbit-groups",
            json={"name": "Study Pod", "privacy_mode": "SHARED_CONTEXT"},
            headers=await _csrf(client),
        )
    ).json()
    person = await _person(client, "Bilal")
    response = await client.post(
        f"{API}/orbit-groups/{group['id']}/members",
        json={"person_id": person["id"], "consent_scope": "SHARED_MEMORY"},
        headers=await _csrf(client),
    )
    assert response.status_code == 422, response.text
    assert "not marked shareable" in response.text

    # Context-only membership is fine, and is the honest default.
    allowed = await client.post(
        f"{API}/orbit-groups/{group['id']}/members",
        json={"person_id": person["id"], "consent_scope": "CONTEXT_ONLY"},
        headers=await _csrf(client),
    )
    assert allowed.status_code == 201, allowed.text
    assert allowed.json()["consent_scope"] == "CONTEXT_ONLY"


@pytest.mark.asyncio
async def test_member_count_is_real(client, owner):
    group = (
        await client.post(
            f"{API}/orbit-groups", json={"name": "Family Orbit"},
            headers=await _csrf(client),
        )
    ).json()
    assert group["member_count"] == 0
    for name in ("Amma", "Abba", "Zara"):
        person = await _person(client, name)
        await client.post(
            f"{API}/orbit-groups/{group['id']}/members",
            json={"person_id": person["id"]}, headers=await _csrf(client),
        )
    groups = (await client.get(f"{API}/orbit-groups")).json()
    assert next(g for g in groups if g["id"] == group["id"])["member_count"] == 3


# ── context links and privacy scope ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_private_person_cannot_have_context_shared_wider(client, owner):
    person = await _person(client)
    response = await client.post(
        f"{API}/orbit-context-links",
        json={
            "person_id": person["id"], "source_type": "JOURNAL_ENTRY",
            "visibility_scope": "ORBIT_SHARED",
        },
        headers=await _csrf(client),
    )
    assert response.status_code == 422, response.text
    assert "private-reference only" in response.text


@pytest.mark.asyncio
async def test_capsule_scope_requires_capsule_eligibility(client, owner):
    person = await _person(client)
    await _patch(client, person["id"], sharing_allowed=True)
    response = await client.post(
        f"{API}/orbit-context-links",
        json={
            "person_id": person["id"], "source_type": "PLAN",
            "visibility_scope": "CAPSULE_SHARED",
        },
        headers=await _csrf(client),
    )
    assert response.status_code == 422, response.text
    assert "Capsule-eligible" in response.text


@pytest.mark.asyncio
async def test_a_private_link_carries_its_reason_and_can_be_unlinked(client, owner):
    person = await _person(client)
    created = await client.post(
        f"{API}/orbit-context-links",
        json={
            "person_id": person["id"], "source_type": "DECISION",
            "link_reason": "She was part of this decision.",
        },
        headers=await _csrf(client),
    )
    assert created.status_code == 201, created.text
    assert created.json()["link_reason"] == "She was part of this decision."

    listed = await client.get(f"{API}/orbit-entities/{person['id']}/context")
    assert len(listed.json()) == 1

    removed = await client.delete(
        f"{API}/orbit-context-links/{created.json()['id']}", headers=await _csrf(client)
    )
    assert removed.status_code == 204
    assert (await client.get(f"{API}/orbit-entities/{person['id']}/context")).json() == []


# ── relationships ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_edge_needs_exactly_one_target(client, owner):
    a = await _person(client, "A")
    b = await _person(client, "B")
    both = await client.post(
        f"{API}/orbit-relationships",
        json={
            "source_person_id": a["id"], "target_person_id": b["id"],
            "target_group_id": str(uuid.uuid4()),
        },
        headers=await _csrf(client),
    )
    assert both.status_code == 422, both.text

    neither = await client.post(
        f"{API}/orbit-relationships",
        json={"source_person_id": a["id"]}, headers=await _csrf(client),
    )
    assert neither.status_code == 422, neither.text


@pytest.mark.asyncio
async def test_a_person_cannot_orbit_themselves(client, owner):
    a = await _person(client, "A")
    response = await client.post(
        f"{API}/orbit-relationships",
        json={"source_person_id": a["id"], "target_person_id": a["id"]},
        headers=await _csrf(client),
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_a_real_edge_is_created_and_listed(client, owner):
    a = await _person(client, "A")
    b = await _person(client, "B")
    created = await client.post(
        f"{API}/orbit-relationships",
        json={
            "source_person_id": a["id"], "target_person_id": b["id"],
            "relationship_type": "Collaborators", "strength_user": 70,
        },
        headers=await _csrf(client),
    )
    assert created.status_code == 201, created.text
    assert created.json()["strength_user"] == 70
    # Derived scores start at zero rather than being invented.
    assert created.json()["activity_score"] == 0
    assert len((await client.get(f"{API}/orbit-relationships")).json()) == 1


# ── layout persistence ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_layout_persists_and_a_partial_save_preserves_other_nodes(client, owner):
    """A drag saves only what moved. Replace-all would silently discard every
    other node's position."""
    a = await _person(client, "A")
    b = await _person(client, "B")
    first = await client.put(
        f"{API}/orbit-layout",
        json=[
            {"entity_type": "PERSON", "entity_id": a["id"], "x": 120.5, "y": -40.0},
            {"entity_type": "PERSON", "entity_id": b["id"], "x": -60.0, "y": 88.25},
        ],
        headers=await _csrf(client),
    )
    assert first.status_code == 200, first.text

    await client.put(
        f"{API}/orbit-layout",
        json=[{"entity_type": "PERSON", "entity_id": a["id"], "x": 200.0, "y": 10.0,
               "pinned": True}],
        headers=await _csrf(client),
    )
    layout = {row["entity_id"]: row for row in (await client.get(f"{API}/orbit-layout")).json()}
    assert layout[a["id"]]["x"] == 200.0
    assert layout[a["id"]]["pinned"] is True
    assert layout[b["id"]]["x"] == -60.0, "an untouched node lost its position"


@pytest.mark.asyncio
async def test_layout_is_per_viewport(client, owner):
    """A desktop arrangement must not dictate mobile."""
    a = await _person(client, "A")
    headers = await _csrf(client)
    await client.put(
        f"{API}/orbit-layout?viewport=desktop",
        json=[{"entity_type": "PERSON", "entity_id": a["id"], "x": 10.0, "y": 10.0}],
        headers=headers,
    )
    await client.put(
        f"{API}/orbit-layout?viewport=mobile",
        json=[{"entity_type": "PERSON", "entity_id": a["id"], "x": 999.0, "y": 5.0}],
        headers=headers,
    )
    desktop = (await client.get(f"{API}/orbit-layout?viewport=desktop")).json()
    mobile = (await client.get(f"{API}/orbit-layout?viewport=mobile")).json()
    assert desktop[0]["x"] == 10.0
    assert mobile[0]["x"] == 999.0


@pytest.mark.asyncio
async def test_moving_a_node_does_not_change_its_band(client, owner):
    """Layout is visual. The band is semantic and only the owner sets it, so a
    drag alone must never reclassify a relationship."""
    person = await _person(client)
    await _patch(client, person["id"], orbit_level="OUTER")
    await client.put(
        f"{API}/orbit-layout",
        json=[{"entity_type": "PERSON", "entity_id": person["id"], "x": 0.0, "y": 0.0}],
        headers=await _csrf(client),
    )
    after = (await client.get(f"{API}/orbit-entities/{person['id']}")).json()
    assert after["orbit_level"] == "OUTER"


# ── the field ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_empty_orbit_reports_empty_rather_than_inventing_gravity(client, owner):
    field = await client.get(f"{API}/orbit-field")
    assert field.status_code == 200, field.text
    body = field.json()
    assert body["people"] == []
    assert body["groups"] == []
    assert body["relationships"] == []
    assert body["thread_counts"] == {}


@pytest.mark.asyncio
async def test_the_field_returns_the_whole_world_in_one_read(client, owner):
    a = await _person(client, "A")
    b = await _person(client, "B")
    await _patch(client, a["id"], orbit_level="INNER")
    group = (
        await client.post(
            f"{API}/orbit-groups", json={"name": "Study Pod"}, headers=await _csrf(client)
        )
    ).json()
    await client.post(
        f"{API}/orbit-relationships",
        json={"source_person_id": a["id"], "target_person_id": b["id"]},
        headers=await _csrf(client),
    )
    await client.put(
        f"{API}/orbit-layout",
        json=[{"entity_type": "PERSON", "entity_id": a["id"], "x": 1.0, "y": 2.0}],
        headers=await _csrf(client),
    )

    body = (await client.get(f"{API}/orbit-field")).json()
    assert len(body["people"]) == 2
    assert len(body["groups"]) == 1
    assert len(body["relationships"]) == 1
    assert len(body["layout"]) == 1
    assert group["id"] in {g["id"] for g in body["groups"]}


# ── cross-owner isolation ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_another_owner_sees_none_of_this_relational_world(client, owner):
    """The whole surface, checked as a second owner. Orbit is the most sensitive
    data in the product and a leak here is a release failure."""
    person = await _person(client, "Ayesha")
    await _patch(client, person["id"], orbit_level="INNER", user_summary="private note")
    group = (
        await client.post(
            f"{API}/orbit-groups", json={"name": "Family Orbit"}, headers=await _csrf(client)
        )
    ).json()
    await client.put(
        f"{API}/orbit-layout",
        json=[{"entity_type": "PERSON", "entity_id": person["id"], "x": 5.0, "y": 5.0}],
        headers=await _csrf(client),
    )

    # A second registration replaces the session on this client.
    stranger, _e, _p = await register_user(client, chosen_name="Bee")
    assert stranger.status_code == 201, stranger.text

    assert (await client.get(f"{API}/orbit-entities")).json() == []
    assert (await client.get(f"{API}/orbit-groups")).json() == []
    assert (await client.get(f"{API}/orbit-relationships")).json() == []
    assert (await client.get(f"{API}/orbit-layout")).json() == []

    field = (await client.get(f"{API}/orbit-field")).json()
    assert field["people"] == [] and field["groups"] == []

    # Direct id access is a 404, not another owner's row.
    assert (await client.get(f"{API}/orbit-entities/{person['id']}")).status_code == 404
    assert (
        await client.get(f"{API}/orbit-groups/{group['id']}/members")
    ).status_code == 404
    # And no write can reach across either.
    assert (await _patch(client, person["id"], orbit_level="DORMANT")).status_code == 404


@pytest.mark.asyncio
async def test_rls_denies_cross_owner_rows_at_the_database(client, owner, app_engine):
    """Not only the API. The row-level policy is what holds if a future service
    forgets its filter."""
    await _person(client, "Ayesha")
    await client.post(
        f"{API}/orbit-groups", json={"name": "Private Circle"}, headers=await _csrf(client)
    )

    stranger = uuid.uuid4()
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as db:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"),
            {"o": str(stranger)},
        )
        for table in (
            "orbit_groups", "orbit_group_members", "orbit_relationships",
            "orbit_context_links", "orbit_layout_nodes", "orbit_threads",
            "orbit_relational_insights", "orbit_relational_signals",
        ):
            visible = (
                await db.execute(text(f"SELECT count(*) FROM {table}"))
            ).scalar()
            assert visible == 0, f"{table}: another owner's rows are visible"

        # And a forged insert claiming this owner is refused by WITH CHECK.
        with pytest.raises(Exception) as caught:
            await db.execute(
                text(
                    "INSERT INTO orbit_groups (owner_user_id, name) VALUES (:o, 'forged')"
                ),
                {"o": owner},
            )
        assert "row-level security" in str(caught.value), str(caught.value)


@pytest.mark.asyncio
async def test_every_orbit_write_requires_csrf(client, owner):
    """State-changing routes are CSRF-protected, so a cross-site form cannot
    rearrange someone's relationships."""
    person = await _person(client)
    for method, url, body in (
        ("patch", f"{API}/orbit-entities/{person['id']}", {"orbit_level": "INNER"}),
        ("post", f"{API}/orbit-groups", {"name": "X"}),
        ("post", f"{API}/orbit-context-links",
         {"person_id": person["id"], "source_type": "PLAN"}),
        ("put", f"{API}/orbit-layout",
         [{"entity_type": "PERSON", "entity_id": person["id"], "x": 0.0, "y": 0.0}]),
    ):
        response = await getattr(client, method)(url, json=body)
        assert response.status_code in (401, 403), f"{url} accepted a write with no CSRF token"
