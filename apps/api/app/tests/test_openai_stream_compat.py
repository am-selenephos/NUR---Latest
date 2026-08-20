import json
from types import SimpleNamespace

from app.ai.openai_provider import OpenAITalkProvider
from app.ai.schemas import TalkProviderRequest


def _valid_payload() -> str:
    return json.dumps({
        "direct_response": "Held.",
        "observed": [],
        "inferred": [],
        "hypotheses": [],
        "uncertainty": [],
        "next_move": "Write one next line.",
        "memory_candidates": [],
        "source_refs": [],
    })


class MissingCompletionStream:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration

    async def get_final_response(self):
        raise RuntimeError("Didn't receive a `response.completed` event.")


class CompatibleResponses:
    def __init__(self):
        self.stream_calls = 0
        self.create_calls = 0

    def stream(self, **_payload):
        self.stream_calls += 1
        return MissingCompletionStream()

    async def create(self, **_payload):
        self.create_calls += 1
        return SimpleNamespace(output_text=_valid_payload(), usage=None, id="resp-fallback")


def _provider() -> tuple[OpenAITalkProvider, CompatibleResponses]:
    provider = object.__new__(OpenAITalkProvider)
    provider._settings = SimpleNamespace(
        openai_model="gpt-4.1-mini",
        openai_reasoning_effort="high",
        openai_request_timeout_seconds=5,
    )
    responses = CompatibleResponses()
    provider._client = SimpleNamespace(responses=responses)
    return provider, responses


async def test_streaming_gateway_without_completion_event_uses_real_response_fallback():
    provider, responses = _provider()
    events: list[tuple[str, dict]] = []

    async def sink(event: str, data: dict):
        events.append((event, data))

    result = await provider.complete_private_talk(
        TalkProviderRequest(user_line="hold this", locale="en", mode="talk", model="gpt-4.1-mini"),
        event_sink=sink,
    )

    assert responses.stream_calls == 1
    assert responses.create_calls == 1
    assert result.available is True
    assert result.raw_response_id == "resp-fallback"
    assert result.output.direct_response == "Held."
    assert [event for event, _data in events] == [
        "provider.fallback",
        "provider.created",
        "response.text.delta",
        "provider.completed",
    ]
    assert events[1][1]["response_id"] == "resp-fallback"
    assert events[2][1]["delta"] == "Held."
