import json
import uuid

from app.ai.errors import AIProviderRateLimited
from app.ai.schemas import AIProviderResult, NURTalkOutput
from app.tests.conftest import register_user


def H(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf")}


def sse_events(raw: str) -> list[tuple[str, dict]]:
    parsed: list[tuple[str, dict]] = []
    for block in raw.replace("\r\n", "\n").split("\n\n"):
        event = "message"
        data: list[str] = []
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data.append(line.removeprefix("data: "))
        if data:
            parsed.append((event, json.loads("\n".join(data))))
    return parsed


class StreamingProvider:
    name = "openai"

    async def complete_private_talk(self, request, event_sink=None):
        assert event_sink is not None
        await event_sink("provider.created", {"response_id": "resp_test_stream"})
        await event_sink("response.text.delta", {"delta": "Real semantic "})
        await event_sink("response.text.delta", {"delta": "stream."})
        return AIProviderResult(
            provider="openai",
            model="test-model",
            available=True,
            raw_response_id="resp_test_stream",
            usage={"input_tokens": 20, "output_tokens": 10},
            output=NURTalkOutput(
                direct_response="Real semantic stream.",
                observed=[],
                inferred=[],
                hypotheses=[],
                uncertainty=[],
                next_move="Keep the durable turn.",
                memory_candidates=[],
                source_refs=[],
            ),
        )


class RateLimitedProvider:
    name = "openai"

    async def complete_private_talk(self, request, event_sink=None):  # noqa: ARG002
        raise AIProviderRateLimited("Synthetic provider rate limit.")


class UngroundedProvider:
    name = "openai"

    async def complete_private_talk(self, request, event_sink=None):  # noqa: ARG002
        return AIProviderResult(
            provider="openai",
            model="test-model",
            available=True,
            raw_response_id="resp_ungrounded",
            usage={"input_tokens": 5, "output_tokens": 5},
            output=NURTalkOutput(
                direct_response="This claim has no retrieved support.",
                observed=["An unsupported observation."],
                inferred=[],
                hypotheses=[],
                uncertainty=[],
                next_move="Ask for evidence.",
                memory_candidates=[],
                source_refs=[],
            ),
        )


async def test_semantic_sse_persists_and_replays_idempotently(client, monkeypatch):
    await register_user(client)
    monkeypatch.setattr("app.cognition.intelligence_kernel.get_ai_provider", lambda: StreamingProvider())
    orbit_id = (await client.get("/api/v1/orbits")).json()[0]["id"]
    request_id = str(uuid.uuid4())
    payload = {
        "request_id": request_id,
        "message": "Prove this live stream is durable.",
        "orbit_id": orbit_id,
        "locale": "en",
        "writing_preference": "default",
    }

    response = await client.post("/api/v1/cognition/talk/stream", headers=H(client), json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = sse_events(response.text)
    names = [name for name, _ in events]
    assert names[:5] == [
        "stream.open",
        "talk.scope.resolved",
        "talk.capability.resolved",
        "talk.accepted",
        "provider.created",
    ]
    assert [data["delta"] for name, data in events if name == "response.text.delta"] == [
        "Real semantic ",
        "stream.",
    ]
    completed = next(data for name, data in events if name == "talk.completed")
    assert completed["durable"] is True
    assert completed["result"]["provider_available"] is True
    assert completed["result"]["output"]["direct_response"] == "Real semantic stream."

    status = (await client.get(f"/api/v1/cognition/talk-runs/{request_id}")).json()
    assert status["status"] == "COMPLETED"
    assert status["response_event_id"] == completed["result"]["response_event_id"]
    assert status["schema_valid"] is True
    assert status["verification_verdict"] in {"PASS", "WARN"}
    assert status["provider_response_id_present"] is True
    assert status["usage_recorded"] is True
    assert len(status["evidence_digest"]) == 64
    assert status["evidence_source_count"] == len(completed["result"]["evidence"]["retrieval"])
    thread = (await client.get(f"/api/v1/cognition/talk-thread?orbit_id={orbit_id}")).json()
    assert [row["who"] for row in thread][-2:] == ["user", "nur"]
    assert thread[-1]["text"] == "Real semantic stream."
    assert thread[-1]["structured_payload"]["model_run_id"] == status["model_run_id"]

    replay = await client.post("/api/v1/cognition/talk/stream", headers=H(client), json=payload)
    assert replay.status_code == 200
    replay_events = sse_events(replay.text)
    assert next(data for name, data in replay_events if name == "talk.completed")["result"]["model_run_id"] == status["model_run_id"]
    thread_after = (await client.get(f"/api/v1/cognition/talk-thread?orbit_id={orbit_id}")).json()
    assert len(thread_after) == len(thread)


async def test_stream_request_id_cannot_be_rebound_to_different_message(client, monkeypatch):
    await register_user(client)
    monkeypatch.setattr("app.cognition.intelligence_kernel.get_ai_provider", lambda: StreamingProvider())
    request_id = str(uuid.uuid4())
    base = {
        "request_id": request_id,
        "message": "First payload.",
        "locale": "en",
        "writing_preference": "default",
    }
    assert (await client.post("/api/v1/cognition/talk/stream", headers=H(client), json=base)).status_code == 200
    changed = {**base, "message": "Different payload."}
    response = await client.post("/api/v1/cognition/talk/stream", headers=H(client), json=changed)
    assert response.status_code == 409


async def test_disabled_stream_ends_with_durable_error_and_no_fake_response(client):
    await register_user(client)
    request_id = str(uuid.uuid4())
    payload = {
        "request_id": request_id,
        "message": "Hold this without pretending AI replied.",
        "locale": "en",
        "writing_preference": "default",
    }

    response = await client.post("/api/v1/cognition/talk/stream", headers=H(client), json=payload)
    assert response.status_code == 200
    events = sse_events(response.text)
    names = [name for name, _ in events]
    assert "provider.disabled" in names
    assert "talk.failed" in names
    assert "talk.completed" not in names
    error = next(data for name, data in events if name == "talk.error")
    assert error["code"] == "provider_disabled"
    assert error["durable"] is True
    assert error["retryable"] is False

    status = (await client.get(f"/api/v1/cognition/talk-runs/{request_id}")).json()
    assert status["status"] == "ERROR"
    assert status["failure_code"] == "provider_disabled"
    assert status["response_event_id"] is None
    assert status["schema_valid"] is False
    thread = (await client.get("/api/v1/cognition/talk-thread")).json()
    assert [row["who"] for row in thread][-1:] == ["user"]

    replay = await client.post("/api/v1/cognition/talk/stream", headers=H(client), json=payload)
    replay_events = sse_events(replay.text)
    replay_error = next(data for name, data in replay_events if name == "talk.error")
    assert replay_error["model_run_id"] == error["model_run_id"]
    thread_after = (await client.get("/api/v1/cognition/talk-thread")).json()
    assert len(thread_after) == len(thread)


async def test_provider_rate_limit_returns_typed_error_without_assistant_message(client, monkeypatch):
    await register_user(client)
    monkeypatch.setattr("app.cognition.intelligence_kernel.get_ai_provider", lambda: RateLimitedProvider())

    response = await client.post(
        "/api/v1/cognition/talk",
        headers=H(client),
        json={"message": "Do not convert a provider failure into a reply.", "locale": "en"},
    )
    assert response.status_code == 429
    detail = response.json()["detail"]
    assert detail["code"] == "provider_rate_limited"
    assert detail["retryable"] is True
    assert detail["model_run_id"]
    thread = (await client.get("/api/v1/cognition/talk-thread")).json()
    assert [row["who"] for row in thread][-1:] == ["user"]


async def test_unverified_provider_output_is_blocked_before_response_persistence(client, monkeypatch):
    await register_user(client)
    monkeypatch.setattr("app.cognition.intelligence_kernel.get_ai_provider", lambda: UngroundedProvider())

    response = await client.post(
        "/api/v1/cognition/talk",
        headers=H(client),
        json={"message": "Only return verified claims.", "locale": "en"},
    )
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["code"] == "provider_output_invalid"
    thread = (await client.get("/api/v1/cognition/talk-thread")).json()
    assert [row["who"] for row in thread][-1:] == ["user"]


def test_direct_response_delta_extractor_handles_chunked_escapes_and_unicode():
    from app.ai.openai_provider import _DirectResponseDeltaExtractor

    extractor = _DirectResponseDeltaExtractor()
    chunks = [
        '{"direct_res',
        'ponse":"Line one\\nA ',
        'star \\u2728 and astral ',
        '\\ud83c\\udf0c", "observed":[]}',
    ]
    assert "".join(extractor.feed(chunk) for chunk in chunks) == "Line one\nA star ✨ and astral 🌌"
