#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  printf 'Missing .env. Run cp .env.example .env first.\n' >&2
  exit 1
fi

# `source .env` would overwrite anything the caller exported, so a seed aimed at
# a second instance silently went to the default one instead — it reported
# success while writing zero rows to the intended database. Caller-supplied
# values are captured first and restored afterwards, so an explicit
# API_ORIGIN/DATABASE_URL wins over the file.
__caller_api_origin="${API_ORIGIN:-}"
__caller_database_url="${DATABASE_URL:-}"
__caller_app_env="${APP_ENV:-}"

set -a
# shellcheck disable=SC1091
source .env
set +a

[[ -n "$__caller_api_origin" ]] && export API_ORIGIN="$__caller_api_origin"
[[ -n "$__caller_database_url" ]] && export DATABASE_URL="$__caller_database_url"
[[ -n "$__caller_app_env" ]] && export APP_ENV="$__caller_app_env"

if [[ "${APP_ENV:-development}" == "production" ]]; then
  printf 'seed-demo-nur.sh refuses to run when APP_ENV=production.\n' >&2
  exit 2
fi
printf 'seeding against %s\n' "${API_ORIGIN:-http://localhost:8000}" >&2

apps/api/.venv/bin/python - <<'PY'
import datetime as dt
import hashlib
import os
import pathlib
import sys

import httpx

API = os.environ.get("API_ORIGIN", "http://localhost:8000")
OWNER_EMAIL = os.environ.get("NUR_DEMO_OWNER_EMAIL", "owner@nur.app")
OWNER_PASSWORD = os.environ.get("NUR_DEMO_OWNER_PASSWORD", "owner-demo-pass-123")
RECIPIENT_EMAIL = os.environ.get("NUR_DEMO_RECIPIENT_EMAIL", "recipient@nur.app")
RECIPIENT_PASSWORD = os.environ.get("NUR_DEMO_RECIPIENT_PASSWORD", "recipient-demo-pass-123")


def csrf(client: httpx.Client) -> dict[str, str]:
    token = client.cookies.get("nur_csrf")
    return {"X-CSRF-Token": token} if token else {}


def ensure_user(client: httpx.Client, email: str, password: str, chosen_name: str) -> dict:
    r = client.post(f"{API}/api/v1/auth/register", json={
        "chosen_name": chosen_name,
        "email": email,
        "password": password,
        "consent": True,
    })
    if r.status_code == 201:
        return r.json()
    login = client.post(f"{API}/api/v1/auth/login", json={"email": email, "password": password})
    if login.status_code != 200:
        print(f"Could not register or login {email}: {r.status_code} {r.text} / {login.status_code} {login.text}", file=sys.stderr)
        raise SystemExit(1)
    return client.get(f"{API}/api/v1/auth/me").json()


def expect_json(response: httpx.Response, label: str) -> dict:
    if not response.is_success:
        print(f"{label} failed: {response.status_code} {response.text}", file=sys.stderr)
        response.raise_for_status()
    try:
        return response.json()
    except Exception as exc:
        print(f"{label} returned non-JSON: {response.status_code} {response.text[:600]}", file=sys.stderr)
        raise exc


def award_glow(client: httpx.Client, *, event_type: str, source_kind: str, source_id: str, orbit_id: str, idempotency_key: str) -> dict | None:
    response = client.post(f"{API}/api/v1/glow/rewards", headers=csrf(client), json={
        "event_type": event_type,
        "source_kind": source_kind,
        "source_id": source_id,
        "orbit_id": orbit_id,
        "idempotency_key": idempotency_key,
    })
    if response.status_code == 201:
        return response.json()
    if response.status_code == 409 and "cap" in response.text.lower():
        return None
    print(f"Glow seed failed: {response.status_code} {response.text}", file=sys.stderr)
    response.raise_for_status()
    return None


owner = httpx.Client(timeout=20)
recipient = httpx.Client(timeout=20)
owner_me = ensure_user(owner, OWNER_EMAIL, OWNER_PASSWORD, "Selene")
ensure_user(recipient, RECIPIENT_EMAIL, RECIPIENT_PASSWORD, "Recipient")

orbits = owner.get(f"{API}/api/v1/orbits").json()
# The System set comes from the API's own catalog module, not from a copy.
#
# It used to be a hard-coded list of the original seven — Ambition, Rebuild,
# Study, Money, Body, Connection, Creation. When the product moved to six
# (Study, Money and Body retired; Growth and Introspection added) this list was
# never updated, so the seed created three orbits for Systems that no longer
# exist and none for the two that do. `owned_system_orbit` resolves a System by
# *title*, so the first request touching a new System failed with
# "Introspection System not found."
#
# The catalog cannot be read over HTTP here: `GET /api/v1/systems` builds a
# snapshot per System, and each snapshot calls `owned_system_orbit`, so that
# endpoint is the very thing that 404s before the orbits exist. Importing the
# module is therefore both the correct source and the only one available at this
# point in the seed. This script already runs under `apps/api/.venv`.
sys.path.insert(0, str(pathlib.Path("apps/api").resolve()))
from app.living.catalog import SYSTEMS as CATALOG_SYSTEMS  # noqa: E402

# Orbit kinds are a presentation detail of the demo owner, not part of the
# catalog contract; anything unlisted seeds as CREATIVE.
SYSTEM_ORBIT_KINDS = {
    "ambition": "CREATIVE",
    "rebuild": "CARE",
    "creation": "CREATIVE",
    "growth": "RESEARCH",
    "introspection": "CARE",
    "connection": "CARE",
}
core_systems = [
    (
        system.title,
        SYSTEM_ORBIT_KINDS.get(system.slug, "CREATIVE"),
        system.definition.split(".")[0].strip() + ".",
    )
    for system in CATALOG_SYSTEMS
]
if not core_systems:
    raise SystemExit("seed aborted: the System catalog is empty")

by_title = {row["title"]: row for row in orbits if row.get("kind") != "PERSONAL_BRIDGE"}
for title, kind, description in core_systems:
    if title in by_title:
        continue
    by_title[title] = expect_json(owner.post(f"{API}/api/v1/orbits", headers=csrf(owner), json={
        "title": title,
        "kind": kind,
        "description": description,
    }), f"create demo System {title}")

# Fail loudly here rather than three steps later inside an unrelated request.
missing = [title for title, _, _ in core_systems if title not in by_title]
if missing:
    raise SystemExit(f"seed aborted: Systems missing after seeding: {', '.join(missing)}")
orbit = by_title["Ambition"]
owner.patch(f"{API}/api/v1/profile/preferences", headers=csrf(owner), json={
    "active_orbit_id": orbit["id"],
    "default_boundary": "PRIVATE_ORBIT",
    "timezone": "Asia/Karachi",
}).raise_for_status()
diagnostic = expect_json(owner.post(f"{API}/api/v1/systems/ambition/diagnostics", headers=csrf(owner), json={
    "answers": {"private_direction": "Ship one exact V197-backed NUR slice."},
    "ratings": {"clarity": 8, "protection": 7, "movement": 6},
    "blockers": ["expanding scope before proof"],
    "strengths": ["continuity", "source fidelity"],
}), "create Ambition diagnostic")
# Reseeding an existing demo owner must not stack duplicate open actions:
# reuse the still-scheduled seed action instead of creating another copy.
existing_schedules = expect_json(owner.get(f"{API}/api/v1/schedules"), "list schedules")
seed_schedule = next((
    row for row in existing_schedules
    if row.get("title") == "Review the exact V197 Today and Systems hydration"
    and row.get("status") == "SCHEDULED"
    and row.get("system_action_id")
), None)
if seed_schedule is not None:
    living_goal = {"id": seed_schedule["goal_id"]}
    living_objective = {"id": seed_schedule["objective_id"]}
    living_action = {"id": seed_schedule["system_action_id"], "title": seed_schedule["title"]}
else:
    living_goal = expect_json(owner.post(f"{API}/api/v1/goals", headers=csrf(owner), json={
        "system_slug": "ambition",
        "title": "Make exact V197 operate on the real owner ledger",
        "why": "The backend adapts to V197; V197 never gets replaced by the backend.",
    }), "create living Goal")
    living_objective = expect_json(owner.post(
        f"{API}/api/v1/goals/{living_goal['id']}/objectives",
        headers=csrf(owner),
        json={"title": "Return one browser-proven V197 action"},
    ), "create living Objective")
    living_action = expect_json(owner.post(f"{API}/api/v1/systems/ambition/actions", headers=csrf(owner), json={
        "title": "Review the exact V197 Today and Systems hydration",
        "description": "Confirm geometry, persistence, Glow, and Timeline together.",
        "diagnostic_id": diagnostic["id"],
        "goal_id": living_goal["id"],
        "objective_id": living_objective["id"],
        "effort_minutes": 20,
    }), "create living System action")
    expect_json(owner.post(f"{API}/api/v1/schedules", headers=csrf(owner), json={
        "system_slug": "ambition",
        "title": living_action["title"],
        "scheduled_for": dt.datetime.now(dt.UTC).isoformat(),
        "duration_minutes": 20,
        "goal_id": living_goal["id"],
        "objective_id": living_objective["id"],
        "system_action_id": living_action["id"],
    }), "schedule living System action")
expect_json(owner.post(f"{API}/api/v1/today/check-in", headers=csrf(owner), json={
    "energy": 7,
    "pain": 3,
    "sleep_quality": 7,
    "nourishment": 7,
    "movement": 5,
    "emotional_load": 4,
    "clarity": 8,
    "note": "Demo capacity is measured, not invented.",
}), "create structured Today check-in")
expect_json(owner.post(f"{API}/api/v1/feasibility", headers=csrf(owner), json={
    "system_slug": "ambition",
    "subject_kind": "ACTION",
    "subject_id": living_action["id"],
    "title": "Twenty-minute V197 proof pass",
    "desired_outcome": "Produce one persisted browser proof without exceeding current capacity.",
    "capacity_required": 35,
    "time_required_minutes": 20,
    "time_available_minutes": 30,
    "money_required_cents": 0,
    "money_available_cents": 0,
    "risk_level": "LOW",
}), "create feasibility assessment")
expect_json(owner.post(f"{API}/api/v1/map/predict-path", headers=csrf(owner), json={
    "system_slug": "ambition",
    "path_type": "continue",
    "goal_id": living_goal["id"],
    "horizon_days": 14,
}), "create future Map path")
project = expect_json(owner.post(f"{API}/api/v1/projects", headers=csrf(owner), json={
    "title": "V197 owner-ledger release",
    "objective": "Verify the exact V197 bridge, package the source, and preserve evidence.",
    "system_slug": "creation",
    "deadline": (dt.datetime.now(dt.UTC) + dt.timedelta(days=7)).isoformat(),
    "budget_cents": 0,
}), "create demo AM Project")
project_task = expect_json(owner.post(
    f"{API}/api/v1/projects/{project['id']}/tasks",
    headers=csrf(owner),
    json={
        "title": "Run the V197 acceptance suite",
        "description": "Prove the owner route on the canonical runtime.",
        "acceptance_criteria": "The isolated backend and browser evidence gates pass.",
        "status": "READY",
        "priority": 90,
        "assigned_role": "verifier",
    },
), "create demo AM Project task")
project_test_path = pathlib.Path("apps/api/app/tests/test_am_projects.py")
project_test_sha = hashlib.sha256(project_test_path.read_bytes()).hexdigest()
expect_json(owner.post(f"{API}/api/v1/projects/{project['id']}/evidence", headers=csrf(owner), json={
    "task_id": project_task["id"],
    "evidence_kind": "TEST_SOURCE",
    "summary": "The AM Project acceptance test is present and checks owner/RLS boundaries.",
    "locator": str(project_test_path),
    "checksum_sha256": project_test_sha,
    "verification_status": "PASSED",
    "verifier": "demo-seed-sha256",
}), "create verified AM Project evidence")
expect_json(owner.patch(
    f"{API}/api/v1/projects/tasks/{project_task['id']}",
    headers=csrf(owner),
    json={"status": "DONE"},
), "complete demo AM Project task")
project_run = expect_json(owner.post(
    f"{API}/api/v1/projects/{project['id']}/runs",
    headers=csrf(owner),
    json={
        "task_id": project_task["id"],
        "role": "verifier",
        "request_summary": "Re-run the bounded local acceptance suite.",
        "tool_policy": {"filesystem_read": True},
        "budget_cents": 0,
    },
), "propose demo AM Project run")
expect_json(owner.post(
    f"{API}/api/v1/projects/runs/{project_run['id']}/approve",
    headers=csrf(owner),
), "approve demo AM Project run")
project_spec_path = pathlib.Path("docs/am-projects-product-spec.md")
project_spec_sha = hashlib.sha256(project_spec_path.read_bytes()).hexdigest()
expect_json(owner.post(f"{API}/api/v1/projects/{project['id']}/artifacts", headers=csrf(owner), json={
    "task_id": project_task["id"],
    "run_id": project_run["id"],
    "artifact_kind": "SPECIFICATION",
    "title": "AM Projects product specification",
    "locator": str(project_spec_path),
    "checksum_sha256": project_spec_sha,
    "provenance_label": "OWNER_REPOSITORY",
}), "create demo AM Project artifact")
expect_json(owner.post(f"{API}/api/v1/projects/{project['id']}/reviews", headers=csrf(owner), json={
    "task_id": project_task["id"],
    "run_id": project_run["id"],
    "decision": "APPROVE",
    "note": "Demo evidence is checksummed and owner-scoped; the run remains a record, not an autonomous action.",
}), "review demo AM Project")
plan = expect_json(owner.post(f"{API}/api/v1/plans", headers=csrf(owner), json={
    "title": "Omega v1 boot demo",
    "orbit_id": orbit["id"],
    "steps": [{"title": "Return one real outcome", "body": "Seeded by boot demo."}],
}), "create demo plan")
award_glow(owner, event_type="plan_created", source_kind="PLAN", source_id=plan["id"], orbit_id=orbit["id"], idempotency_key=f"seed-plan:{plan['id']}:created")
step_id = plan["steps"][0]["id"]
owner.post(f"{API}/api/v1/omega/predictions", headers=csrf(owner), json={
    "prediction_text": "The boot demo outcome will resolve the seeded prediction.",
    "expected_observation": "Boot demo outcome persisted",
    "plan_step_id": step_id,
    "confidence": 0.72,
}).raise_for_status()
owner.patch(f"{API}/api/v1/plan-steps/{step_id}", headers=csrf(owner), json={"done": True}).raise_for_status()
award_glow(owner, event_type="plan_step_completed", source_kind="PLAN_STEP", source_id=step_id, orbit_id=orbit["id"], idempotency_key=f"seed-step:{step_id}:completed")
outcome = expect_json(owner.post(f"{API}/api/v1/outcomes", headers=csrf(owner), json={
    "plan_step_id": step_id,
    "observed_result": "Boot demo outcome persisted and can resolve predictions.",
}), "create demo outcome")
award_glow(owner, event_type="outcome_returned", source_kind="OUTCOME", source_id=outcome["id"], orbit_id=orbit["id"], idempotency_key=f"seed-outcome:{outcome['id']}:returned")
owner.post(f"{API}/api/v1/cognition/events", headers=csrf(owner), json={
    "event_kind": "MODEL_RESPONSE",
    "content_text": "Model response: identity expansion may be a sensitive inferred preference and must wait for owner review.",
}).raise_for_status()
owner.post(f"{API}/api/v1/omega/claims", headers=csrf(owner), json={
    "claim_text": "Capsule law must not send raw owner memory to recipients.",
    "claim_type": "CONSTRAINT",
    "truth_status": "OBSERVED",
    "provenance_label": "OWNER_WRITTEN",
}).raise_for_status()
owner.post(f"{API}/api/v1/omega/claims", headers=csrf(owner), json={
    "claim_text": "We will send raw owner memory to recipients.",
    "claim_type": "DECISION",
    "truth_status": "HYPOTHESIS",
    "provenance_label": "MODEL_GENERATED",
}).raise_for_status()
owner.post(f"{API}/api/v1/omega/consolidate", headers=csrf(owner), json={"run_kind": "MANUAL"}).raise_for_status()
people = owner.get(f"{API}/api/v1/orbits/people").json()
amina = next((row for row in people if row["display_name"] == "Amina Rahman"), None)
all_orbits = owner.get(f"{API}/api/v1/orbits").json()
person_orbit = next((row for row in all_orbits if row["kind"] == "PERSON" and row["title"] == "Amina Rahman"), None)
if amina is None or person_orbit is None:
    social = expect_json(owner.post(f"{API}/api/v1/orbits/from-conversation", headers=csrf(owner), json={
        "display_name": "Amina Rahman",
        "relationship_type": "trusted collaborator",
        "conversation_summary": "Review whether the V197 release evidence is understandable without private owner memory.",
        "unresolved_count": 1,
        "shared_goal_count": 1,
    }), "create demo Person Orbit")
    amina = social["person"]
    person_orbit = social["orbit"]

all_orbits = owner.get(f"{API}/api/v1/orbits").json()
group_orbit = next((row for row in all_orbits if row["kind"] == "GROUP" and row["title"] == "NUR release room"), None)
if group_orbit is None:
    group_orbit = expect_json(owner.post(f"{API}/api/v1/orbits", headers=csrf(owner), json={
        "title": "NUR release room",
        "kind": "GROUP",
        "description": "A bounded group Orbit for release review; no personal memory is copied.",
        "privacy_scope": "PRIVATE_ORBIT",
        "metadata": {"group_memory_separate": True},
    }), "create demo Group Orbit")
    expect_json(owner.post(f"{API}/api/v1/orbits/{group_orbit['id']}/members", headers=csrf(owner), json={
        "person_id": amina["id"],
        "role": "REVIEWER",
        "closeness_score": 72,
        "recent_activity_score": 64,
        "unresolved_count": 1,
        "shared_goal_count": 1,
    }), "add demo Group member")

all_orbits = owner.get(f"{API}/api/v1/orbits").json()
council_orbit = next((
    row for row in all_orbits
    if row["kind"] == "COUNCIL" and row["title"] == "Evidence release council"
), None)
if council_orbit is None:
    council_result = expect_json(owner.post(f"{API}/api/v1/orbits/{person_orbit['id']}/start-council", headers=csrf(owner), json={
        "title": "Evidence release council",
        "purpose": "Decide whether source, test, and privacy evidence are sufficient for release.",
        "person_ids": [amina["id"]],
    }), "create demo Council Orbit")
    council_orbit = council_result["council"]

# Group NUR is a real bounded multi-user ledger, not a decorative Community
# card. Demo-marked rows are visible as DEMO and intentionally earn no Glow.
rooms = expect_json(owner.get(f"{API}/api/v1/community/rooms"), "list demo Group NUR rooms")
group_room = next((row for row in rooms if row["title"] == "NUR release room"), None)
if group_room is None:
    group_room = expect_json(owner.post(f"{API}/api/v1/community/rooms", headers=csrf(owner), json={
        "title": "NUR release room",
        "description": "Bounded demo room. It contains shared room content only, never owner private memory.",
        "room_kind": "GROUP",
        "orbit_id": group_orbit["id"],
        "language_tag": "en",
        "is_demo": True,
    }), "create bounded demo Group NUR room")
group_members = expect_json(
    owner.get(f"{API}/api/v1/community/rooms/{group_room['id']}/members"),
    "list demo Group NUR members",
)
if len(group_members) < 2:
    expect_json(owner.post(
        f"{API}/api/v1/community/rooms/{group_room['id']}/members",
        headers=csrf(owner),
        json={"email": RECIPIENT_EMAIL, "role": "MEMBER"},
    ), "add recipient to bounded demo Group NUR room")
group_messages = expect_json(
    owner.get(f"{API}/api/v1/community/rooms/{group_room['id']}/messages"),
    "list demo Group NUR messages",
)
if not group_messages:
    expect_json(owner.post(
        f"{API}/api/v1/community/rooms/{group_room['id']}/messages",
        headers=csrf(owner),
        json={
            "body": "DEMO: Review the release evidence without opening private owner memory.",
            "language_tag": "en",
            "is_demo": True,
        },
    ), "create demo Group NUR message")

rooms = expect_json(owner.get(f"{API}/api/v1/community/rooms"), "refresh demo Community rooms")
council_room = next((row for row in rooms if row["title"] == "Evidence release council"), None)
if council_room is None:
    council_room = expect_json(owner.post(f"{API}/api/v1/community/rooms", headers=csrf(owner), json={
        "title": "Evidence release council",
        "description": "Bounded demo Council for release evidence.",
        "room_kind": "COUNCIL",
        "orbit_id": council_orbit["id"],
        "language_tag": "en",
        "is_demo": True,
    }), "create bounded demo Council room")
council_members = expect_json(
    owner.get(f"{API}/api/v1/community/rooms/{council_room['id']}/members"),
    "list demo Council members",
)
if len(council_members) < 2:
    expect_json(owner.post(
        f"{API}/api/v1/community/rooms/{council_room['id']}/members",
        headers=csrf(owner),
        json={"email": RECIPIENT_EMAIL, "role": "MEMBER"},
    ), "add recipient to bounded demo Council")
council_summary = expect_json(
    owner.get(f"{API}/api/v1/community/rooms/{council_room['id']}/summary"),
    "read demo Council summary",
)
if council_summary["counts"]["positions"] == 0:
    expect_json(recipient.post(
        f"{API}/api/v1/community/rooms/{council_room['id']}/positions",
        headers=csrf(recipient),
        json={
            "position": "DEMO: Release only after browser and privacy evidence are attached.",
            "evidence": ["demo acceptance boundary"],
            "is_minority": True,
            "is_demo": True,
        },
    ), "create recipient demo Council position")
if council_summary["counts"]["decisions"] == 0:
    expect_json(owner.post(
        f"{API}/api/v1/community/rooms/{council_room['id']}/decision",
        headers=csrf(owner),
        json={
            "decision": "DEMO: Return after WebKit and RLS proof are attached.",
            "rationale": "The release boundary is evidence-first.",
            "minority_opinion": "The member requested one additional visual pass.",
            "is_demo": True,
        },
    ), "record owner demo Council decision")

# A real bounded Consultation lifecycle is seeded as DEMO and intentionally
# earns no Glow. It stays at RETURN so the owner can inspect the complete
# ORIENT/GATHER/MAP/MOVE evidence path before recording an outcome.
consultations = expect_json(owner.get(f"{API}/api/v1/consultations"), "list demo Consultations")
consultation = next((row for row in consultations if row["title"] == "Release readiness return"), None)
if consultation is None:
    consultation = expect_json(owner.post(
        f"{API}/api/v1/consultations",
        headers=csrf(owner),
        json={
            "title": "Release readiness return",
            "question": "What evidence is enough to call this release ready?",
            "purpose": "Keep disagreement and proof inside one bounded decision path.",
            "desired_outcome": "A release decision with a verifiable return check.",
            "scope_statement": "Only room contributions and explicit Consultation records.",
            "room_id": group_room["id"],
            "orbit_id": group_orbit["id"],
            "system_slug": "ambition",
            "is_demo": True,
        },
    ), "create demo bounded Consultation")

# Load the current Consultation state once — it carries both the contributions and
# the true current_stage, so re-seeding is decided from persisted truth.
detail = expect_json(
    owner.get(f"{API}/api/v1/consultations/{consultation['id']}"),
    "load demo Consultation state",
)

# Idempotent contribution: add the DEMO counterexample only if it is absent, so a
# rerun (fresh or resumed) never manufactures a duplicate contribution.
demo_counterexample = "DEMO: visual proof cannot replace recipient-isolation proof."
if not any(row.get("body") == demo_counterexample for row in detail.get("contributions", [])):
    expect_json(recipient.post(
        f"{API}/api/v1/consultations/{consultation['id']}/contributions",
        headers=csrf(recipient),
        json={
            "contribution_type": "COUNTEREXAMPLE",
            "body": demo_counterexample,
            "evidence": ["DEMO boundary assertion"],
            "language_tag": "en",
            "is_demo": True,
        },
    ), "add demo Consultation counterexample")

# Contract-aware, resume-safe stage advancement. Only the stages that are still
# pending are posted, advancing from the Consultation's actual current_stage, and
# the Consultation is intentionally left AT RETURN — the RETURN outcome is never
# fabricated by the seed. A second run with current_stage == RETURN is a no-op.
demo_stage_payloads = {
    "ORIENT": {"actual_question": "What evidence is enough?", "affected_people": ["owner", "recipient"]},
    "GATHER": {"facts": ["WebKit proof required"], "constraints": ["RLS must remain forced"]},
    "MAP": {"options": ["release", "hold"], "minority_positions": ["run one more privacy pass"]},
    "MOVE": {"selected_action": "run the owner/recipient boundary suite", "success_signal": "all tests pass"},
}
stage_order = ["ORIENT", "GATHER", "MAP", "MOVE", "RETURN"]
consultation_state = detail.get("consultation", {})
if consultation_state.get("status") == "ACTIVE":
    start = stage_order.index(consultation_state.get("current_stage", "ORIENT"))
    for stage in stage_order[start:stage_order.index("RETURN")]:
        expect_json(owner.post(
            f"{API}/api/v1/consultations/{consultation['id']}/stages/{stage}",
            headers=csrf(owner),
            json={"payload": demo_stage_payloads[stage]},
        ), f"complete demo Consultation {stage}")

# Notifications are factual owner-authored re-entry cues. Re-seeding reuses the
# existing demo reminder so boot never manufactures an expanding unread count.
notifications = expect_json(owner.get(f"{API}/api/v1/notifications"), "list demo notifications")
if not any(row.get("title") == "Return to the V197 release proof" for row in notifications):
    expect_json(owner.post(
        f"{API}/api/v1/notifications/reminders",
        headers=csrf(owner),
        json={
            "category": "PROGRESS",
            "title": "Return to the V197 release proof",
            "body": "Run one owner-scoped browser check, then record the real result.",
            "route": "/projects",
            "is_demo": True,
        },
    ), "create truthful demo notification")

timeline_rows = owner.get(f"{API}/api/v1/timeline").json()
if not any(row.get("event_type") == "GOAL_MILESTONE" and row.get("goal_id") == living_goal["id"] for row in timeline_rows):
    expect_json(owner.post(f"{API}/api/v1/timeline/from-goal", headers=csrf(owner), json={
        "goal_id": living_goal["id"],
        "scheduled_for": (dt.datetime.now(dt.UTC) + dt.timedelta(days=3)).isoformat(),
    }), "create demo future Timeline milestone")

insight_rows = owner.get(f"{API}/api/v1/insights").json()
if not insight_rows:
    demo_insight = expect_json(owner.post(f"{API}/api/v1/insights/generate", headers=csrf(owner), json={
        "system_slug": "ambition",
    }), "generate demo evidence-linked Insight")
    expect_json(owner.post(
        f"{API}/api/v1/insights/{demo_insight['id']}/add-to-timeline",
        headers=csrf(owner),
    ), "add demo Insight review to Timeline")
print(
    "Seed skipped live Talk model call; "
    + (
        "openai-smoke-local.sh validates provider output separately."
        if os.environ.get("NUR_AI_PROVIDER") == "openai"
        else "the disabled provider must not fabricate an assistant turn."
    )
)
journal = expect_json(owner.post(f"{API}/api/v1/journal", headers=csrf(owner), json={
    "body": "Boot demo journal: the interface must stay visual, private, and source-bound.",
    "orbit_id": orbit["id"],
}), "create demo Journal entry")
award_glow(owner, event_type="journal_saved", source_kind="JOURNAL_ENTRY", source_id=journal["id"], orbit_id=orbit["id"], idempotency_key=f"seed-journal:{journal['id']}:saved")
owner.post(f"{API}/api/v1/research-drafts", headers=csrf(owner), json={
    "question": "Which outside signal should be checked before claiming NUR is market-ready?",
    "notes": "Seeded research question; no live web fetch is performed.",
    "orbit_id": orbit["id"],
}).raise_for_status()
brief = expect_json(owner.post(f"{API}/api/v1/research/briefs", headers=csrf(owner), json={
    "question": "Which outside signal should be checked before claiming NUR is market-ready?",
    "summary": "Seeded local research brief; no live web fetch is performed.",
    "orbit_id": orbit["id"],
}), "create demo research brief")
owner.post(f"{API}/api/v1/research/source-notes", headers=csrf(owner), json={
    "title": "Local research source note",
    "note": "Owner-supplied source note for beta readiness; not fetched from the web.",
    "orbit_id": orbit["id"],
    "research_brief_id": brief["id"],
}).raise_for_status()
owner.post(f"{API}/api/v1/community/consultation-notes", headers=csrf(owner), json={
    "title": "Collaborator boundary review",
    "note": "Ask a collaborator whether the Orbit boundary is understandable without onboarding.",
    "collaborator_label": "future reviewer",
    "orbit_id": orbit["id"],
}).raise_for_status()
web_question = expect_json(owner.post(f"{API}/api/v1/web-signals/questions", headers=csrf(owner), json={
    "question": "Check whether privacy-first personal context tools explain revocation clearly.",
    "orbit_id": orbit["id"],
}), "create demo web signal question")
owner.post(f"{API}/api/v1/web-signals/notes", headers=csrf(owner), json={
    "title": "Revocation clarity signal",
    "note": "Local note only; no live web connector is enabled.",
    "orbit_id": orbit["id"],
    "web_signal_question_id": web_question["id"],
}).raise_for_status()
owner.get(f"{API}/api/v1/provider-capabilities").raise_for_status()

decision = expect_json(owner.post(f"{API}/api/v1/orbits/{orbit['id']}/decisions", headers=csrf(owner), json={
    "statement": "Capsules share only approved sources, never Omega owner memory.",
    "rationale": "Boot demo source boundary.",
}), "create capsule source decision")
reference = expect_json(owner.post(f"{API}/api/v1/orbits/{orbit['id']}/references", headers=csrf(owner), json={
    "title": "V197 visual contract",
    "body": "Bodoni, Crimson, deep black void, warm glass, holographic NUR, source-faithful stars.",
    "kind": "REFERENCE",
}), "create orbit reference")
constraint = expect_json(owner.post(f"{API}/api/v1/orbits/{orbit['id']}/references", headers=csrf(owner), json={
    "title": "Recipient boundary constraint",
    "body": "Recipients can ask only against included Capsule sources.",
    "kind": "CONSTRAINT",
}), "create orbit constraint")
source = expect_json(owner.post(f"{API}/api/v1/orbits/{orbit['id']}/sources", headers=csrf(owner), json={
    "source_kind": "DECISION",
    "source_id": decision["id"],
}), "attach capsule source")
owner.post(f"{API}/api/v1/orbits/{orbit['id']}/sources", headers=csrf(owner), json={
    "source_kind": "REFERENCE",
    "source_id": reference["id"],
}).raise_for_status()
owner.post(f"{API}/api/v1/orbits/{orbit['id']}/sources", headers=csrf(owner), json={
    "source_kind": "REFERENCE",
    "source_id": constraint["id"],
}).raise_for_status()
capsule = expect_json(owner.post(f"{API}/api/v1/orbits/{orbit['id']}/capsules", headers=csrf(owner), json={
    "title": "Omega isolation boot capsule",
    "purpose": "Show recipient sees approved context only.",
    "capability": "ASK_SCOPED_QUESTIONS",
    "orbit_source_ids": [source["id"]],
    "representations": {source["id"]: "FULL"},
}), "create demo capsule")
owner.post(f"{API}/api/v1/capsules/{capsule['id']}/grants", headers=csrf(owner), json={
    "recipient_email": RECIPIENT_EMAIL,
    "capability": "ASK_SCOPED_QUESTIONS",
}).raise_for_status()

print("Demo seed complete")
print(f"Owner: {OWNER_EMAIL} / {OWNER_PASSWORD}")
print(f"Recipient: {RECIPIENT_EMAIL} / {RECIPIENT_PASSWORD}")
web = os.environ.get('WEB_ORIGIN', 'http://localhost:5173')
print(f"Owner app: {web}")
print(f"Owner Talk: {web}/talk")
print(f"Owner Systems: {web}/systems")
print(f"Omega: {web}/universe/omega")
print(f"Omega Review: {web}/universe/omega/review")
print(f"Consultations: {web}/consultations")
print(f"Demo Consultation: {web}/consultations/{consultation['id']}")
print(f"Owner Notifications: {web}/notifications")
print(f"Recipient Capsule: {web}/capsule/{capsule['id']}")
print(f"Owner user id: {owner_me['id']}")
PY
