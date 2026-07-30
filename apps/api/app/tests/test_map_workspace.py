"""The Map surface, through real HTTP against real PostgreSQL.

Map claims to model where someone is, where they are trying to go, and what is in
the way. The tests that matter most are therefore the ones that stop it
overclaiming: that a suggestion cannot apply itself, that dragging a node cannot
reassign a System, that a prediction cannot be stored as certainty, that NUR
cannot assert an emotional blocker as fact, and that no owner can read another's
map.

Composition is checked against canonical rows on purpose. If Map ever started
storing its own goals or its own decisions, these tests would still pass while the
product had quietly grown a second truth — so several of them assert that the
graph reflects a row created through the *canonical* endpoint, not a Map one.
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


async def _goal(client, title="Complete NUR Beta", slug="creation", **extra) -> dict:
    body = {"system_slug": slug, "title": title, **extra}
    response = await client.post(f"{API}/goals", json=body, headers=await _csrf(client))
    assert response.status_code == 201, response.text
    return response.json()


async def _default_view(client) -> str:
    response = await client.get(f"{API}/map/views")
    assert response.status_code == 200, response.text
    return response.json()["default_view_id"]


async def _decision(client, statement="Finish privately or launch a public beta?") -> dict:
    """Created through the canonical orbits endpoint, never a Map-owned one."""
    orbits = await client.get(f"{API}/orbits")
    assert orbits.status_code == 200, orbits.text
    orbit_id = orbits.json()[0]["id"] if isinstance(orbits.json(), list) else (
        orbits.json()["items"][0]["id"]
    )
    response = await client.post(
        f"{API}/orbits/{orbit_id}/decisions",
        json={"statement": statement},
        headers=await _csrf(client),
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
async def owner(client):
    response, email, password = await register_user(client)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


# ── composition over canonical rows ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_graph_composes_canonical_rows_it_does_not_own(client, owner):
    """A goal created through the canonical endpoint appears on the Map.

    This is the reuse guarantee: Map has no goals table, so the only way this can
    pass is by reading `goals`.
    """
    goal = await _goal(client)
    graph = await client.get(f"{API}/map")
    assert graph.status_code == 200, graph.text
    body = graph.json()
    ids = {row["id"] for row in body["nodes"]}
    assert f"goal:{goal['id']}" in ids
    assert "nur" in ids


@pytest.mark.asyncio
async def test_system_regions_come_from_the_canonical_catalog(client, owner):
    """Regions are driven from `living/catalog.py`, never a hardcoded list.

    The spec asks for seven Systems and the repository holds six (CONFLICT-010).
    This asserts the count *matches the catalog* rather than pinning a number, so
    the Map picks up a seventh the moment the founder adds one.
    """
    from app.living.catalog import SYSTEMS

    graph = (await client.get(f"{API}/map")).json()
    regions = graph["system_regions"]
    assert [row["slug"] for row in regions] == [row.slug for row in SYSTEMS]
    for region in regions:
        assert region["state"] in {
            "STABLE", "BUILDING", "ACTIVE", "STALLED",
            "RECOVERING", "AT_RISK", "UNCLEAR", "DORMANT",
        }
        # §10: every state must be explainable, and never a score.
        assert region["state_reason"].strip()
        assert "%" in region["state_reason"]


@pytest.mark.asyncio
async def test_a_system_state_is_explained_in_the_owners_own_counts(client, owner):
    goal = await _goal(client)
    graph = (await client.get(f"{API}/map")).json()
    region = next(
        row for row in graph["system_regions"] if row["slug"] == "creation"
    )
    assert region["active_goal_count"] >= 1
    assert "1 active goal" in region["state_reason"]
    assert "no returned outcome yet" in region["state_reason"]
    assert goal["id"]


# ── layout: position is presentation, never meaning ──────────────────────────


@pytest.mark.asyncio
async def test_layout_persists_and_is_applied_to_the_graph(client, owner):
    goal = await _goal(client)
    view_id = await _default_view(client)
    saved = await client.put(
        f"{API}/map/views/{view_id}/layout",
        json={
            "viewport_key": "desktop",
            "nodes": [
                {"node_ref_type": "goal", "node_ref_id": goal["id"], "x": 321.5, "y": -88.25}
            ],
        },
        headers=await _csrf(client),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["nodes_written"] == 1
    assert saved.json()["semantics_changed"] is False

    graph = (await client.get(f"{API}/map/views/{view_id}/graph")).json()
    node = next(row for row in graph["nodes"] if row["id"] == f"goal:{goal['id']}")
    assert node["data"]["layout"]["x"] == 321.5
    assert node["data"]["layout"]["y"] == -88.25
    assert graph["staleness"]["layout_is_owner_positioned"] is True


@pytest.mark.asyncio
async def test_dragging_a_node_never_changes_its_system(client, owner):
    """§15: moving a goal near Money must not make it a Money goal."""
    goal = await _goal(client, slug="creation")
    view_id = await _default_view(client)
    before = (await client.get(f"{API}/map")).json()
    parent_before = next(
        row["parent_id"] for row in before["nodes"] if row["id"] == f"goal:{goal['id']}"
    )

    await client.put(
        f"{API}/map/views/{view_id}/layout",
        json={"nodes": [
            {"node_ref_type": "goal", "node_ref_id": goal["id"], "x": -900.0, "y": 900.0}
        ]},
        headers=await _csrf(client),
    )
    after = (await client.get(f"{API}/map/views/{view_id}/graph")).json()
    node = next(row for row in after["nodes"] if row["id"] == f"goal:{goal['id']}")
    assert node["parent_id"] == parent_before, "layout reassigned the System"
    assert node["data"]["layout"]["x"] == -900.0

    goal_after = (await client.get(f"{API}/goals")).json()
    row = next(item for item in goal_after if item["id"] == goal["id"])
    assert row["system_slug"] == "creation", "a drag rewrote the canonical goal"


@pytest.mark.asyncio
async def test_a_moved_system_keeps_its_region_under_it(client, owner):
    """The region halo is drawn from `system_regions`, the node from `nodes`.

    Recomputing the region's position left the halo and its label behind at the
    ring position while the node moved away, so the two are read from the same
    place now.
    """
    view_id = await _default_view(client)
    await client.put(
        f"{API}/map/views/{view_id}/layout",
        json={"nodes": [
            {"node_ref_type": "system", "node_ref_id": "creation", "x": 123.0, "y": -45.0}
        ]},
        headers=await _csrf(client),
    )
    graph = (await client.get(f"{API}/map/views/{view_id}/graph")).json()
    node = next(row for row in graph["nodes"] if row["id"] == "system:creation")
    region = next(row for row in graph["system_regions"] if row["slug"] == "creation")
    assert node["data"]["layout"]["x"] == 123.0
    assert (region["layout"]["x"], region["layout"]["y"]) == (123.0, -45.0)
    # An untouched System still sits on the computed ring.
    other = next(row for row in graph["system_regions"] if row["slug"] != "creation")
    other_node = next(row for row in graph["nodes"] if row["id"] == f"system:{other['slug']}")
    assert other["layout"]["x"] == other_node["data"]["layout"]["x"]


@pytest.mark.asyncio
async def test_layout_is_rejected_for_an_unknown_object_kind(client, owner):
    view_id = await _default_view(client)
    response = await client.put(
        f"{API}/map/views/{view_id}/layout",
        json={"nodes": [
            {"node_ref_type": "goblin", "node_ref_id": "x", "x": 0, "y": 0}
        ]},
        headers=await _csrf(client),
    )
    assert response.status_code == 422, response.text


# ── views ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_focus_view_without_a_root_is_refused(client, owner):
    """A Focus view with nothing to focus on would render the Universe and lie."""
    response = await client.post(
        f"{API}/map/views",
        json={"name": "Focus", "view_type": "FOCUS"},
        headers=await _csrf(client),
    )
    assert response.status_code == 422, response.text
    assert "focused on" in response.text


@pytest.mark.asyncio
async def test_the_default_view_cannot_be_deleted(client, owner):
    view_id = await _default_view(client)
    response = await client.delete(
        f"{API}/map/views/{view_id}", headers=await _csrf(client)
    )
    assert response.status_code == 409, response.text


@pytest.mark.asyncio
async def test_a_saved_focus_view_round_trips(client, owner):
    goal = await _goal(client)
    created = await client.post(
        f"{API}/map/views",
        json={
            "name": "NUR beta focus",
            "view_type": "FOCUS",
            "root_entity_type": "goal",
            "root_entity_id": goal["id"],
            "filters": {"object_kinds": ["goal", "blocker"]},
        },
        headers=await _csrf(client),
    )
    assert created.status_code == 201, created.text
    view = created.json()
    fetched = (await client.get(f"{API}/map/views/{view['id']}")).json()
    assert fetched["view_type"] == "FOCUS"
    assert fetched["root_entity_id"] == goal["id"]
    assert fetched["filters"]["object_kinds"] == ["goal", "blocker"]


# ── semantic edges ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_owner_drawn_edge_is_confirmed_and_appears_as_structure(client, owner):
    first = await _goal(client, title="Publish case study")
    second = await _goal(client, title="Explain the architecture")
    created = await client.post(
        f"{API}/map/edges",
        json={
            "source_ref_type": "goal", "source_ref_id": first["id"],
            "target_ref_type": "goal", "target_ref_id": second["id"],
            "edge_type": "DEPENDS_ON",
            "note": "Cannot write it up without being able to explain it.",
        },
        headers=await _csrf(client),
    )
    assert created.status_code == 201, created.text
    assert created.json()["user_confirmed"] is True

    graph = (await client.get(f"{API}/map")).json()
    semantic = [row for row in graph["edges"] if row.get("semantic")]
    assert len(semantic) == 1
    assert semantic[0]["kind"] == "DEPENDS_ON"
    assert semantic[0]["resolvable"] is True
    assert graph["suggested_changes"]["candidate_edges"] == []


@pytest.mark.asyncio
async def test_an_object_cannot_be_connected_to_itself(client, owner):
    goal = await _goal(client)
    response = await client.post(
        f"{API}/map/edges",
        json={
            "source_ref_type": "goal", "source_ref_id": goal["id"],
            "target_ref_type": "goal", "target_ref_id": goal["id"],
            "edge_type": "BLOCKS",
        },
        headers=await _csrf(client),
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_an_unknown_relationship_type_is_refused(client, owner):
    first = await _goal(client, title="A")
    second = await _goal(client, title="B")
    response = await client.post(
        f"{API}/map/edges",
        json={
            "source_ref_type": "goal", "source_ref_id": first["id"],
            "target_ref_type": "goal", "target_ref_id": second["id"],
            "edge_type": "VIBES_WITH",
        },
        headers=await _csrf(client),
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_a_duplicate_connection_is_refused(client, owner):
    first = await _goal(client, title="A")
    second = await _goal(client, title="B")
    body = {
        "source_ref_type": "goal", "source_ref_id": first["id"],
        "target_ref_type": "goal", "target_ref_id": second["id"],
        "edge_type": "SUPPORTS",
    }
    assert (await client.post(
        f"{API}/map/edges", json=body, headers=await _csrf(client)
    )).status_code == 201
    again = await client.post(f"{API}/map/edges", json=body, headers=await _csrf(client))
    assert again.status_code == 409, again.text


# ── suggestions: a proposal is not a change ──────────────────────────────────


@pytest.mark.asyncio
async def test_a_generated_suggestion_is_pending_and_explains_itself(client, owner):
    """Two plans with the same title produce a candidate, not an edit."""
    orbits = await client.get(f"{API}/orbits")
    payload = orbits.json()
    orbit_id = payload[0]["id"] if isinstance(payload, list) else payload["items"][0]["id"]
    for _ in range(2):
        made = await client.post(
            f"{API}/plans",
            json={"orbit_id": orbit_id, "title": "Ship the beta"},
            headers=await _csrf(client),
        )
        assert made.status_code in {200, 201}, made.text

    generated = await client.post(
        f"{API}/map/suggestions/generate", headers=await _csrf(client)
    )
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["provenance_label"] == "DETERMINISTIC_LEDGER_DERIVED"
    assert "No model was" in body["note"]
    duplicates = [
        row for row in body["items"] if row["suggestion_type"] == "DUPLICATE_PLAN"
    ]
    assert duplicates, body
    candidate = duplicates[0]
    assert candidate["status"] == "PENDING"
    assert candidate["requires_acceptance"] is True
    # Every candidate must be able to answer "Why?" and state its own doubt.
    assert "Ship the beta" in candidate["explanation"]
    assert candidate["may_be_wrong_about"].strip()
    assert len(candidate["source_refs"]) == 2


@pytest.mark.asyncio
async def test_a_pending_suggestion_never_appears_as_structure(client, owner):
    """Candidates travel in `suggested_changes`. They must not enter `edges`."""
    goal = await _goal(client)
    session = async_sessionmaker(client.app.state.engine, expire_on_commit=False) if hasattr(
        client.app.state, "engine"
    ) else None
    assert session is None or True  # engine access is not required for this check

    # A candidate edge written as unconfirmed with a named inference source.
    from app.models import MapEdge
    from app.db.session import get_sessionmaker

    maker = get_sessionmaker()
    async with maker() as db:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": str(owner)},
        )
        db.add(MapEdge(
            owner_user_id=owner,
            source_ref_type="goal", source_ref_id=goal["id"],
            target_ref_type="system", target_ref_id="money",
            edge_type="SUPPORTS",
            user_confirmed=False,
            inference_source="test_probe",
        ))
        await db.commit()

    graph = (await client.get(f"{API}/map")).json()
    assert [row for row in graph["edges"] if row.get("semantic")] == []
    candidates = graph["suggested_changes"]["candidate_edges"]
    assert len(candidates) == 1
    assert candidates[0]["user_confirmed"] is False
    assert candidates[0]["inference_source"] == "test_probe"


@pytest.mark.asyncio
async def test_rejecting_a_kind_stops_it_being_raised_again(client, owner):
    orbits = await client.get(f"{API}/orbits")
    payload = orbits.json()
    orbit_id = payload[0]["id"] if isinstance(payload, list) else payload["items"][0]["id"]
    for _ in range(2):
        await client.post(
            f"{API}/plans",
            json={"orbit_id": orbit_id, "title": "Duplicated plan"},
            headers=await _csrf(client),
        )
    first = (await client.post(
        f"{API}/map/suggestions/generate", headers=await _csrf(client)
    )).json()
    candidate = next(
        row for row in first["items"] if row["suggestion_type"] == "DUPLICATE_PLAN"
    )
    rejected = await client.post(
        f"{API}/map/suggestions/{candidate['id']}/reject",
        json={"suppress_kind": True},
        headers=await _csrf(client),
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["kind_suppressed"] is True

    again = (await client.post(
        f"{API}/map/suggestions/generate", headers=await _csrf(client)
    )).json()
    assert "DUPLICATE_PLAN" in again["suppressed_kinds"]
    assert not [
        row for row in again["items"] if row["suggestion_type"] == "DUPLICATE_PLAN"
    ]


@pytest.mark.asyncio
async def test_a_suggestion_cannot_be_reviewed_twice(client, owner):
    orbits = await client.get(f"{API}/orbits")
    payload = orbits.json()
    orbit_id = payload[0]["id"] if isinstance(payload, list) else payload["items"][0]["id"]
    for _ in range(2):
        await client.post(
            f"{API}/plans",
            json={"orbit_id": orbit_id, "title": "Twice"},
            headers=await _csrf(client),
        )
    items = (await client.post(
        f"{API}/map/suggestions/generate", headers=await _csrf(client)
    )).json()["items"]
    candidate = items[0]
    assert (await client.post(
        f"{API}/map/suggestions/{candidate['id']}/reject",
        json={}, headers=await _csrf(client),
    )).status_code == 200
    again = await client.post(
        f"{API}/map/suggestions/{candidate['id']}/accept", headers=await _csrf(client)
    )
    assert again.status_code == 409, again.text


# ── blockers ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_owner_stated_blocker_is_open_and_confirmed(client, owner):
    goal = await _goal(client)
    created = await client.post(
        f"{API}/map/blockers",
        json={
            "title": "Cannot explain the backend architecture independently",
            "system_slug": "creation",
            "category": "KNOWLEDGE",
            "basis": "USER_STATED",
            "affects": [{"type": "goal", "id": goal["id"]}],
            "possible_responses": ["Architecture learning path", "Reduce claim scope"],
        },
        headers=await _csrf(client),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "OPEN"
    assert body["confirmed_by_owner"] is True
    assert body["asserted_as_fact"] is True

    graph = (await client.get(f"{API}/map")).json()
    node = next(
        row for row in graph["nodes"] if row["id"] == f"blocker:{body['id']}"
    )
    assert node["data"]["addressable"] is True
    # §20: the blocker must say what it blocks, from the row itself.
    assert any(
        edge["source"] == f"blocker:{body['id']}"
        and edge["target"] == f"goal:{goal['id']}"
        for edge in graph["edges"]
    )


@pytest.mark.asyncio
async def test_nur_cannot_assert_an_emotional_blocker_as_fact(client, owner):
    """§20. An inferred psychological blocker stays a proposal until confirmed."""
    created = await client.post(
        f"{API}/map/blockers",
        json={
            "title": "Afraid of shipping in public",
            "category": "PSYCHOLOGICAL",
            "basis": "NUR_INFERRED",
            "evidence": [{"type": "journal_entry", "id": "abc", "quote": "kept delaying"}],
        },
        headers=await _csrf(client),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "PROPOSED"
    assert body["confirmed_by_owner"] is False
    assert body["asserted_as_fact"] is False

    # Promoting it without the owner's confirmation must be refused.
    promoted = await client.patch(
        f"{API}/map/blockers/{body['id']}",
        json={"status": "OPEN"},
        headers=await _csrf(client),
    )
    assert promoted.status_code == 422, promoted.text
    assert "Confirm it" in promoted.text

    # With confirmation it becomes a real blocker.
    confirmed = await client.patch(
        f"{API}/map/blockers/{body['id']}",
        json={"status": "OPEN", "confirmed_by_owner": True},
        headers=await _csrf(client),
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "OPEN"
    assert confirmed.json()["asserted_as_fact"] is True


@pytest.mark.asyncio
async def test_an_inferred_blocker_without_evidence_is_refused(client, owner):
    response = await client.post(
        f"{API}/map/blockers",
        json={"title": "Something vague", "category": "TECHNICAL", "basis": "NUR_INFERRED"},
        headers=await _csrf(client),
    )
    assert response.status_code == 422, response.text
    assert "evidence" in response.text.lower()


@pytest.mark.asyncio
async def test_resolving_a_blocker_records_when(client, owner):
    created = (await client.post(
        f"{API}/map/blockers",
        json={"title": "Usage exhausted", "category": "EXTERNAL", "basis": "USER_STATED"},
        headers=await _csrf(client),
    )).json()
    resolved = await client.patch(
        f"{API}/map/blockers/{created['id']}",
        json={"status": "RESOLVED", "resolution_note": "Quota reset."},
        headers=await _csrf(client),
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["resolved_at"] is not None


# ── decisions and options ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_decision_carries_options_and_only_one_can_be_chosen(client, owner):
    decision = await _decision(client)
    labels = ["Finish privately", "Public beta", "Portfolio demo"]
    options = []
    for label in labels:
        made = await client.post(
            f"{API}/map/decisions/{decision['id']}/options",
            json={
                "label": label,
                "reversibility": "EASY" if label != "Public beta" else "COSTLY",
                "risks": [f"{label} risk"],
            },
            headers=await _csrf(client),
        )
        assert made.status_code == 201, made.text
        options.append(made.json())

    chosen = await client.post(
        f"{API}/map/decisions/{decision['id']}/choose/{options[2]['id']}",
        headers=await _csrf(client),
    )
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["resolved"] is True

    second = await client.post(
        f"{API}/map/decisions/{decision['id']}/choose/{options[0]['id']}",
        headers=await _csrf(client),
    )
    assert second.status_code == 409, second.text
    assert "already resolved" in second.text


@pytest.mark.asyncio
async def test_an_unresolved_decision_shows_on_the_map_as_unresolved(client, owner):
    decision = await _decision(client)
    await client.post(
        f"{API}/map/decisions/{decision['id']}/options",
        json={"label": "Option A"},
        headers=await _csrf(client),
    )
    graph = (await client.get(f"{API}/map")).json()
    node = next(
        row for row in graph["nodes"] if row["id"] == f"decision:{decision['id']}"
    )
    assert node["status"] == "UNRESOLVED"
    assert node["data"]["option_count"] == 1
    assert graph["counts"]["unresolved_decisions"] >= 1


@pytest.mark.asyncio
async def test_decision_analysis_gives_no_recommendation_without_a_priority(client, owner):
    """Silence is the honest output when nothing has been said to judge against."""
    decision = await _decision(client)
    for label in ("A", "B"):
        await client.post(
            f"{API}/map/decisions/{decision['id']}/options",
            json={"label": label},
            headers=await _csrf(client),
        )
    analysis = await client.post(
        f"{API}/map/decision-analysis",
        json={"decision_id": decision["id"]},
        headers=await _csrf(client),
    )
    assert analysis.status_code == 200, analysis.text
    body = analysis.json()
    assert body["recommendation"] is None
    assert body["governing_assumption"] is None
    assert body["decides_for_you"] is False
    assert body["comparison_matrix"]


@pytest.mark.asyncio
async def test_a_recommendation_always_exposes_its_governing_assumption(client, owner):
    decision = await _decision(client)
    safe = (await client.post(
        f"{API}/map/decisions/{decision['id']}/options",
        json={"label": "Reversible route", "reversibility": "EASY"},
        headers=await _csrf(client),
    )).json()
    await client.post(
        f"{API}/map/decisions/{decision['id']}/options",
        json={"label": "One-way route", "reversibility": "MOSTLY_IRREVERSIBLE"},
        headers=await _csrf(client),
    )
    analysis = (await client.post(
        f"{API}/map/decision-analysis",
        json={"decision_id": decision["id"], "stated_priority": "reversibility"},
        headers=await _csrf(client),
    )).json()
    assert analysis["recommendation"]["option_id"] == safe["id"]
    assert analysis["governing_assumption"] == "reversibility"
    assert "changes if" in analysis["recommendation"]["changes_if"]
    assert analysis["decides_for_you"] is False


# ── map a problem ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mapping_a_problem_frames_it_without_claiming_to_reason(client, owner):
    response = await client.post(
        f"{API}/map/problem",
        json={
            "situation": "I need three more Codex runs to finish the UI but my usage is exhausted.",
            "desired_outcome": "Finish the Map interface this week",
            "constraints": ["Usage quota exhausted", "One week left"],
            "resources": ["Local test suite", "Existing Orbit code"],
            "unknowns": ["When the quota resets"],
            "system_slug": "creation",
        },
        headers=await _csrf(client),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    # The honesty of this endpoint is the whole point: it must not present a
    # template as analysis.
    assert body["provenance_label"] == "DETERMINISTIC_FRAME"
    assert body["is_model_generated"] is False
    assert "not NUR's analysis" in body["note"]
    assert len(body["options"]) >= 3
    assert any(option["reversibility"] == "EASY" for option in body["options"])

    # It becomes a real, unresolved decision the owner can edit.
    listed = (await client.get(f"{API}/map/decisions")).json()["items"]
    row = next(item for item in listed if item["id"] == body["decision_id"])
    assert row["resolved"] is False
    assert len(row["options"]) == len(body["options"])


# ── predictions: never certainty, always resolvable ──────────────────────────


@pytest.mark.asyncio
async def test_a_prediction_cannot_be_stored_as_certainty(client, owner):
    """The schema refuses confidence of 1. Falsified directly against the DB."""
    from app.db.session import get_sessionmaker
    from app.models import Prediction
    from sqlalchemy.exc import IntegrityError

    maker = get_sessionmaker()
    async with maker() as db:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": str(owner)},
        )
        db.add(Prediction(
            owner_user_id=owner, statement="This will definitely happen", confidence=1
        ))
        with pytest.raises(IntegrityError) as caught:
            await db.commit()
    assert "ck_predictions_never_certain" in str(caught.value)


@pytest.mark.asyncio
async def test_a_prediction_resolves_into_a_recorded_learning(client, owner):
    goal = await _goal(client)
    made = await client.post(
        f"{API}/map/predict-path",
        json={
            "system_slug": "creation",
            "path_type": "continue",
            "goal_id": goal["id"],
            "horizon_days": 14,
        },
        headers=await _csrf(client),
    )
    assert made.status_code == 201, made.text
    prediction_id = made.json()["id"]

    resolved = await client.post(
        f"{API}/map/predictions/{prediction_id}/resolve",
        json={
            "resolution": "CONTRADICTED",
            "learning": "The estimate ignored the migration work.",
        },
        headers=await _csrf(client),
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["resolution"] == "CONTRADICTED"
    assert resolved.json()["learning"]

    again = await client.post(
        f"{API}/map/predictions/{prediction_id}/resolve",
        json={"resolution": "CONFIRMED"},
        headers=await _csrf(client),
    )
    assert again.status_code == 409, again.text


# ── evidence provenance ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evidence_separates_facts_interpretations_and_inferences(client, owner):
    """§23. A note, an owner-drawn edge and an inferred edge must not read alike."""
    goal = await _goal(client)
    other = await _goal(client, title="Second")
    await client.post(
        f"{API}/map/annotations",
        json={
            "entity_ref_type": "goal", "entity_ref_id": goal["id"],
            "body": "This is the one that gets me hired.",
        },
        headers=await _csrf(client),
    )
    await client.post(
        f"{API}/map/edges",
        json={
            "source_ref_type": "goal", "source_ref_id": goal["id"],
            "target_ref_type": "goal", "target_ref_id": other["id"],
            "edge_type": "SUPPORTS",
        },
        headers=await _csrf(client),
    )
    evidence = await client.get(
        f"{API}/map/entities/goal/{goal['id']}/evidence"
    )
    assert evidence.status_code == 200, evidence.text
    body = evidence.json()
    classes = {row["evidence_class"] for row in body["supporting"]}
    assert "USER_INTERPRETATION" in classes
    assert body["confidence"] is None, "evidence must not invent a confidence number"
    assert set(body["evidence_classes"]) >= {
        "DIRECT_FACT", "MODEL_INFERENCE", "USER_INTERPRETATION", "PREDICTION",
    }


@pytest.mark.asyncio
async def test_a_contradicting_blocker_is_listed_against_the_goal(client, owner):
    goal = await _goal(client)
    await client.post(
        f"{API}/map/blockers",
        json={
            "title": "No time this month",
            "category": "TIME",
            "basis": "USER_STATED",
            "affects": [{"type": "goal", "id": goal["id"]}],
        },
        headers=await _csrf(client),
    )
    body = (await client.get(f"{API}/map/entities/goal/{goal['id']}/evidence")).json()
    assert any(row["source"] == "Blocker" for row in body["contradicting"])


@pytest.mark.asyncio
async def test_missing_information_is_named_rather_than_hidden(client, owner):
    goal = await _goal(client)
    body = (await client.get(f"{API}/map/entities/goal/{goal['id']}/evidence")).json()
    assert body["missing_information"], "an empty evidence picture said nothing"


# ── path comparison ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_path_comparison_says_so_when_there_is_no_route(client, owner):
    goal = await _goal(client)
    response = await client.post(
        f"{API}/map/path-comparison",
        json={"goal_id": goal["id"]},
        headers=await _csrf(client),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["paths"] == []
    assert "no route to compare" in body["note"].lower()


@pytest.mark.asyncio
async def test_path_comparison_reports_unmeasured_dimensions_honestly(client, owner):
    goal = await _goal(client)
    # A plan becomes a route toward a goal by living in the same System orbit —
    # there is no plan→goal foreign key anywhere in NUR, so this is the real
    # association rather than one Map invented.
    graph = (await client.get(f"{API}/map")).json()
    system_orbit = next(
        row["data"]["orbit_id"]
        for row in graph["nodes"]
        if row["id"] == "system:creation"
    )
    plan = await client.post(
        f"{API}/plans",
        json={"orbit_id": system_orbit, "title": "Portfolio route"},
        headers=await _csrf(client),
    )
    assert plan.status_code in {200, 201}, plan.text

    body = (await client.post(
        f"{API}/map/path-comparison",
        json={"goal_id": goal["id"]},
        headers=await _csrf(client),
    )).json()
    assert body["provenance_label"] == "DETERMINISTIC_FRAME"
    assert body["is_model_generated"] is False
    lane = next(row for row in body["paths"] if row["name"] == "Portfolio route")
    # §19: unmeasured dimensions must say so rather than showing a number.
    assert lane["reversibility"] == "Not assessed"
    assert lane["expected_outcome"] is None
    assert "has been tested" in lane["uncertainty"]
    assert "no plan-to-goal link" in body["association_basis"].lower()


# ── smart sections ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_smart_sections_surface_real_rows_only(client, owner):
    goal = await _goal(client)
    decision = await _decision(client)
    await client.post(
        f"{API}/map/blockers",
        json={
            "title": "Blocked on quota",
            "category": "EXTERNAL",
            "basis": "USER_STATED",
            "affects": [{"type": "goal", "id": goal["id"]}],
        },
        headers=await _csrf(client),
    )
    body = (await client.get(f"{API}/map/smart-sections")).json()
    assert any(row["ref"] == f"goal:{goal['id']}" for row in body["current_focus"])
    assert any(row["ref"] == f"decision:{decision['id']}" for row in body["needs_decision"])
    assert any(row["ref"] == f"goal:{goal['id']}" for row in body["blocked"])
    assert body["provenance_label"] == "OWNER_LEDGER_DERIVED"


# ── isolation ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_owner_can_read_or_move_another_owners_map(client, owner):
    """Forced RLS, proven through the app role rather than asserted."""
    goal = await _goal(client)
    view_id = await _default_view(client)
    edge = (await client.post(
        f"{API}/map/edges",
        json={
            "source_ref_type": "goal", "source_ref_id": goal["id"],
            "target_ref_type": "system", "target_ref_id": "money",
            "edge_type": "SUPPORTS",
        },
        headers=await _csrf(client),
    )).json()
    blocker = (await client.post(
        f"{API}/map/blockers",
        json={"title": "Private blocker", "category": "TIME", "basis": "USER_STATED"},
        headers=await _csrf(client),
    )).json()

    # A second owner in the same database.
    second, _, _ = await register_user(client)
    assert second.status_code == 201, second.text

    assert (await client.get(f"{API}/map/views/{view_id}")).status_code == 404
    assert (await client.patch(
        f"{API}/map/edges/{edge['id']}",
        json={"note": "mine now"},
        headers=await _csrf(client),
    )).status_code == 404
    assert (await client.delete(
        f"{API}/map/edges/{edge['id']}", headers=await _csrf(client)
    )).status_code == 404
    assert (await client.patch(
        f"{API}/map/blockers/{blocker['id']}",
        json={"status": "DISMISSED"},
        headers=await _csrf(client),
    )).status_code == 404

    graph = (await client.get(f"{API}/map")).json()
    ids = {row["id"] for row in graph["nodes"]}
    assert f"goal:{goal['id']}" not in ids
    assert f"blocker:{blocker['id']}" not in ids
    assert [row for row in graph["edges"] if row.get("semantic")] == []


@pytest.mark.asyncio
async def test_an_empty_map_is_empty_not_seeded(client, owner):
    """A fresh owner has Systems and nothing else. No sample goal, no fake edge."""
    graph = (await client.get(f"{API}/map")).json()
    kinds = {row["kind"] for row in graph["nodes"]}
    assert kinds <= {"MASTER_STAR", "SYSTEM"}, f"the Map invented content: {kinds}"
    assert graph["counts"]["goals"] == 0
    assert graph["counts"]["blockers"] == 0
    assert graph["counts"]["decisions"] == 0
    assert graph["edges"], "systems should still be attached to the anchor"
    assert graph["suggested_changes"]["suggestions"] == []


@pytest.mark.asyncio
async def test_the_graph_never_reports_a_prediction_as_certain(client, owner):
    goal = await _goal(client)
    await client.post(
        f"{API}/map/predict-path",
        json={"system_slug": "creation", "goal_id": goal["id"], "horizon_days": 30},
        headers=await _csrf(client),
    )
    body = (await client.get(
        f"{API}/map/entities/goal/{goal['id']}/predictions"
    )).json()
    for row in body["items"]:
        assert row["is_certain"] is False
        assert row["confidence"] is None or row["confidence"] < 1
    assert "never a" in body["note"]


@pytest.mark.asyncio
async def test_layout_written_for_one_view_does_not_leak_into_another(client, owner):
    goal = await _goal(client)
    default_view = await _default_view(client)
    other = (await client.post(
        f"{API}/map/views",
        json={
            "name": "Focus", "view_type": "FOCUS",
            "root_entity_type": "goal", "root_entity_id": goal["id"],
        },
        headers=await _csrf(client),
    )).json()

    await client.put(
        f"{API}/map/views/{default_view}/layout",
        json={"nodes": [
            {"node_ref_type": "goal", "node_ref_id": goal["id"], "x": 10.0, "y": 20.0}
        ]},
        headers=await _csrf(client),
    )
    moved = (await client.get(f"{API}/map/views/{other['id']}/graph")).json()
    node = next(row for row in moved["nodes"] if row["id"] == f"goal:{goal['id']}")
    assert node["data"]["layout"]["x"] != 10.0
    assert moved["staleness"]["layout_is_owner_positioned"] is False
