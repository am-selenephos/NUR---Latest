import asyncio
import json
from typing import Any

from app.ai.errors import (
    AIOutputValidationError,
    AIProviderAuthenticationError,
    AIProviderError,
    AIProviderMisconfigured,
    AIProviderQuotaExceeded,
    AIProviderRateLimited,
    AIProviderTimeout,
    AIProviderUnavailable,
    AIProviderUnsupportedModel,
)
from app.ai.prompts import TALK_SYSTEM_PROMPT, talk_user_prompt
from app.ai.schemas import AIProviderResult, AIStreamSink, NURTalkOutput, TalkProviderRequest
from app.ai.structured_outputs import talk_json_schema
from app.core.config import get_settings

RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
AUTH_STATUS_CODES = {401, 403}


class OpenAITalkProvider:
    name = "openai"

    def __init__(self, settings: Any = None) -> None:
        s = settings or get_settings()
        if s.openai_api_key is None or not s.openai_model:
            raise AIProviderMisconfigured("OpenAI provider is missing OPENAI_API_KEY or NUR_OPENAI_MODEL.")
        try:
            from openai import AsyncOpenAI
        except Exception as exc:  # pragma: no cover - depends on installed optional package
            raise AIProviderMisconfigured("The openai Python package is not installed.") from exc
        self._settings = s
        self._client = AsyncOpenAI(
            api_key=s.openai_api_key.get_secret_value(),
            timeout=s.openai_request_timeout_seconds,
        )

    async def complete_private_talk(
        self,
        request: TalkProviderRequest,
        event_sink: AIStreamSink | None = None,
    ) -> AIProviderResult:
        payload = self._payload(request)
        response = (
            await self._stream_response(payload, event_sink)
            if event_sink is not None
            else await self._create_response(payload)
        )
        parsed = _extract_response_json(response)
        try:
            output = NURTalkOutput.model_validate(parsed)
        except Exception as exc:
            raise AIOutputValidationError("OpenAI response did not match NURTalkOutput.") from exc
        if event_sink is not None:
            await event_sink(
                "provider.completed",
                {"response_id": getattr(response, "id", None), "schema_valid": True},
            )
        return AIProviderResult(
            provider=self.name,
            model=request.model or self._settings.openai_model,
            available=True,
            output=output,
            usage=getattr(response, "usage", None).model_dump() if getattr(response, "usage", None) else {},
            raw_response_id=getattr(response, "id", None),
        )

    def _payload(self, request: TalkProviderRequest) -> dict:
        evidence = [r.model_dump() for r in request.retrieval]
        chosen_model = request.model or self._settings.openai_model
        system_content = request.system_prompt if request.system_prompt is not None else TALK_SYSTEM_PROMPT
        # Brain callers use an empty mapping to mean "use the canonical Talk
        # schema". Never forward that sentinel to Responses API as an empty
        # text.format object; the provider correctly rejects it as malformed.
        format_spec = request.output_schema or talk_json_schema()

        payload: dict[str, Any] = {
            "model": chosen_model,
            "input": [
                {"role": "system", "content": system_content},
                {
                    "role": "user",
                    "content": talk_user_prompt(
                        user_line=request.user_line,
                        evidence=evidence,
                        locale=request.locale,
                        writing_preference=request.writing_preference,
                        mode=request.mode,
                        omega_context=request.omega_context,
                    ),
                },
            ],
            "text": {"format": format_spec},
        }

        chosen_effort = request.reasoning_effort or self._settings.openai_reasoning_effort
        if _supports_reasoning_effort(chosen_model):
            payload["reasoning"] = {"effort": chosen_effort}
        elif request.temperature is not None:
            payload["temperature"] = request.temperature

        if request.max_output_tokens is not None:
            payload["max_output_tokens"] = request.max_output_tokens

        return payload

    async def _stream_response(self, payload: dict, event_sink: AIStreamSink):
        """Forward provider lifecycle and decoded direct-response deltas.

        Structured Outputs preserve schema key order, so `direct_response` is
        the first field. The extractor decodes that JSON string while the
        official Responses stream is still arriving; no completed response is
        split into pretend chunks.
        """
        for attempt in range(2):
            extractor = _DirectResponseDeltaExtractor()
            emitted_text = False
            try:
                if attempt:
                    await event_sink("provider.retry", {"attempt": attempt + 1})
                async with asyncio.timeout(self._settings.openai_request_timeout_seconds):
                    async with self._client.responses.stream(**payload) as stream:
                        async for event in stream:
                            event_type = getattr(event, "type", "")
                            if event_type == "response.created":
                                response = getattr(event, "response", None)
                                await event_sink(
                                    "provider.created",
                                    {"response_id": getattr(response, "id", None)},
                                )
                            elif event_type == "response.output_text.delta":
                                delta = getattr(event, "delta", "") or ""
                                visible = extractor.feed(delta)
                                if visible:
                                    emitted_text = True
                                    await event_sink("response.text.delta", {"delta": visible})
                            elif event_type in {"error", "response.error", "response.failed", "response.incomplete"}:
                                raise AIProviderError("OpenAI stream ended without a completed response.")
                        return await stream.get_final_response()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                mapped = _classify_provider_exception(exc)
                if attempt == 0 and not emitted_text and mapped.retryable:
                    continue
                if mapped is exc:
                    raise
                raise mapped from exc
        raise AIProviderUnavailable("OpenAI streaming request failed closed.")

    async def _create_response(self, payload: dict):
        """Retry transient provider failures once; never retry auth/config errors."""
        for attempt in range(2):
            try:
                return await self._client.responses.create(**payload)
            except Exception as exc:
                mapped = _classify_provider_exception(exc)
                if attempt == 0 and mapped.retryable:
                    continue
                if mapped is exc:
                    raise
                raise mapped from exc
        raise AIProviderUnavailable("OpenAI request failed closed.")


def _supports_reasoning_effort(model: str) -> bool:
    """The Responses API rejects reasoning.effort on non-reasoning models
    (e.g. gpt-4.1) with 400 unsupported_parameter, so only send it to
    reasoning-capable families."""
    return model.lower().startswith(("o1", "o3", "o4", "gpt-5"))


def _extract_response_json(response) -> dict:
    text = getattr(response, "output_text", None)
    if not text:
        chunks: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                value = getattr(content, "text", None)
                if value:
                    chunks.append(value)
        text = "\n".join(chunks)
    if not text:
        raise AIOutputValidationError("OpenAI response contained no text output.")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIOutputValidationError("OpenAI response was not valid JSON.") from exc


def _status_code(exc: Exception) -> int | None:
    value = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _provider_error_code(exc: Exception) -> str:
    direct = getattr(exc, "code", None)
    if direct:
        return str(direct).lower()
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        payload = body.get("error") if isinstance(body.get("error"), dict) else body
        value = payload.get("code") or payload.get("type")
        if value:
            return str(value).lower()
    return ""


def _classify_provider_exception(exc: Exception) -> AIProviderError:
    if isinstance(exc, AIProviderError):
        return exc
    status = _status_code(exc)
    code = _provider_error_code(exc)
    name = exc.__class__.__name__.lower()
    if status in AUTH_STATUS_CODES or "auth" in name or "permission" in name:
        return AIProviderAuthenticationError("OpenAI rejected the server credential.")
    if code in {"insufficient_quota", "billing_hard_limit_reached", "usage_limit_reached"}:
        return AIProviderQuotaExceeded("OpenAI quota or billing prevented the request.")
    if code in {"model_not_found", "unsupported_model", "invalid_model"} or status == 404:
        return AIProviderUnsupportedModel("OpenAI rejected the configured model.")
    if status == 429 or "ratelimit" in name or "rate_limit" in code:
        return AIProviderRateLimited("OpenAI rate limited the request.")
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)) or "timeout" in name:
        return AIProviderTimeout("OpenAI timed out.")
    if status in {400, 409, 422}:
        return AIProviderMisconfigured("OpenAI rejected the request configuration.")
    if status in RETRYABLE_STATUS_CODES or "connection" in name:
        return AIProviderUnavailable("OpenAI was temporarily unavailable.")
    return AIProviderUnavailable("OpenAI request failed closed.")


class _DirectResponseDeltaExtractor:
    """Incrementally decode only the first structured `direct_response` value."""

    _MARKER = '"direct_response"'
    _ESCAPES = {
        '"': '"',
        "\\": "\\",
        "/": "/",
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
    }

    def __init__(self) -> None:
        self._buffer = ""
        self._cursor: int | None = None
        self._done = False

    def feed(self, chunk: str) -> str:
        if self._done or not chunk:
            return ""
        self._buffer += chunk
        if self._cursor is None:
            marker = self._buffer.find(self._MARKER)
            if marker < 0:
                return ""
            colon = self._buffer.find(":", marker + len(self._MARKER))
            if colon < 0:
                return ""
            cursor = colon + 1
            while cursor < len(self._buffer) and self._buffer[cursor].isspace():
                cursor += 1
            if cursor >= len(self._buffer):
                return ""
            if self._buffer[cursor] != '"':
                self._done = True
                return ""
            self._cursor = cursor + 1

        decoded: list[str] = []
        cursor = self._cursor
        assert cursor is not None
        while cursor < len(self._buffer):
            char = self._buffer[cursor]
            if char == '"':
                self._done = True
                cursor += 1
                break
            if char != "\\":
                decoded.append(char)
                cursor += 1
                continue
            if cursor + 1 >= len(self._buffer):
                break
            escaped = self._buffer[cursor + 1]
            if escaped in self._ESCAPES:
                decoded.append(self._ESCAPES[escaped])
                cursor += 2
                continue
            if escaped != "u" or cursor + 6 > len(self._buffer):
                break
            try:
                codepoint = int(self._buffer[cursor + 2 : cursor + 6], 16)
            except ValueError:
                self._done = True
                break
            if 0xD800 <= codepoint <= 0xDBFF:
                if cursor + 12 > len(self._buffer):
                    break
                if self._buffer[cursor + 6 : cursor + 8] != "\\u":
                    self._done = True
                    break
                try:
                    low = int(self._buffer[cursor + 8 : cursor + 12], 16)
                except ValueError:
                    self._done = True
                    break
                if not 0xDC00 <= low <= 0xDFFF:
                    self._done = True
                    break
                decoded.append(chr(0x10000 + ((codepoint - 0xD800) << 10) + (low - 0xDC00)))
                cursor += 12
                continue
            if 0xDC00 <= codepoint <= 0xDFFF:
                self._done = True
                break
            decoded.append(chr(codepoint))
            cursor += 6
        self._cursor = cursor
        return "".join(decoded)
