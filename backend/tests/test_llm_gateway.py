"""Tests for the LLM gateway, against a stand-in chat-completions endpoint."""

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from ews.core.settings import Settings
from ews.llm.gateway import (
    LLMError,
    LLMGateway,
    LLMOutputError,
    LLMRateLimitError,
    Message,
)

GROQ_KEY = "gsk-test-key"
ASK: list[Message] = [{"role": "user", "content": "How severe is this?"}]

Handler = Callable[[httpx.Request], httpx.Response]


class Assessment(BaseModel):
    """The typed result the tests ask the model for."""

    severity: str
    confidence: float


def completion(
    content: str, model: str = "served-model", prompt: int = 11, output: int = 7
) -> httpx.Response:
    """A chat-completions response carrying the content."""
    return httpx.Response(
        200,
        json={
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": output},
        },
    )


GOOD = '{"severity": "severe", "confidence": 0.8}'


class Provider:
    """Stand-in endpoint: answers each request with the next scripted response."""

    def __init__(self, *responses: httpx.Response | Handler) -> None:
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        # The last response repeats, so one entry scripts a constant provider
        response = (
            self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        )
        return response(request) if callable(response) else response

    def body(self, index: int) -> dict[str, Any]:
        body: dict[str, Any] = json.loads(self.requests[index].content)
        return body


class Sleeper:
    """Records the waits the gateway asks for instead of sleeping."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def gateway_for(
    provider: Provider, sleeper: Sleeper | None = None, **settings: Any
) -> LLMGateway:
    """A gateway whose HTTP calls are answered by the stand-in provider."""
    http = httpx.AsyncClient(transport=httpx.MockTransport(provider.handle))
    return LLMGateway.from_settings(
        Settings(_env_file=None, **settings), http, sleep=sleeper or Sleeper()
    )


def groq(
    provider: Provider, sleeper: Sleeper | None = None, **settings: Any
) -> LLMGateway:
    return gateway_for(
        provider, sleeper, llm_provider="groq", llm_api_key=GROQ_KEY, **settings
    )


class TestProviderSelection:
    """Test cases for choosing the provider from settings"""

    async def test_lm_studio_is_the_default_and_needs_no_key(self) -> None:
        provider = Provider(completion(GOOD))
        gateway = gateway_for(provider)

        result = await gateway.complete(ASK, Assessment, prompt_version="v1")

        request = provider.requests[0]
        assert str(request.url) == "http://localhost:1234/v1/chat/completions"
        assert result.call.provider == "lm_studio"

    async def test_groq_is_called_at_its_own_url_with_the_key(self) -> None:
        provider = Provider(completion(GOOD))
        gateway = groq(provider)

        result = await gateway.complete(ASK, Assessment, prompt_version="v1")

        request = provider.requests[0]
        assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
        assert request.headers["authorization"] == f"Bearer {GROQ_KEY}"
        assert provider.body(0)["model"] == "openai/gpt-oss-120b"
        assert result.call.provider == "groq"

    async def test_base_url_model_and_temperature_are_configurable(self) -> None:
        provider = Provider(completion(GOOD))
        gateway = gateway_for(
            provider,
            llm_base_url="http://gpu-box:8080/v1/",
            llm_model="qwen-local",
            llm_temperature=0.7,
        )

        await gateway.complete(ASK, Assessment, prompt_version="v1")

        assert (
            str(provider.requests[0].url) == "http://gpu-box:8080/v1/chat/completions"
        )
        assert provider.body(0)["model"] == "qwen-local"
        assert provider.body(0)["temperature"] == 0.7

    def test_groq_without_a_key_fails_fast(self) -> None:
        with pytest.raises(ValidationError, match="EWS_LLM_API_KEY is required"):
            Settings(_env_file=None, llm_provider="groq")

    def test_a_blank_key_counts_as_missing(self) -> None:
        with pytest.raises(ValidationError, match="EWS_LLM_API_KEY is required"):
            Settings(_env_file=None, llm_provider="groq", llm_api_key="")


class TestStructuredOutput:
    """Test cases for LLMGateway.complete returning a validated object"""

    async def test_returns_the_validated_object(self) -> None:
        gateway = gateway_for(Provider(completion(GOOD)))

        result = await gateway.complete(ASK, Assessment, prompt_version="v1")

        assert result.output == Assessment(severity="severe", confidence=0.8)

    async def test_requests_the_json_schema_of_the_output_type(self) -> None:
        provider = Provider(completion(GOOD))
        gateway = gateway_for(provider)

        await gateway.complete(ASK, Assessment, prompt_version="v1")

        response_format = provider.body(0)["response_format"]
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["name"] == "Assessment"
        assert response_format["json_schema"]["schema"]["required"] == [
            "severity",
            "confidence",
        ]

    async def test_invalid_output_is_repaired_once(self) -> None:
        provider = Provider(completion('{"severity": "severe"}'), completion(GOOD))
        gateway = gateway_for(provider)

        result = await gateway.complete(ASK, Assessment, prompt_version="v1")

        assert result.output.confidence == 0.8
        assert len(provider.requests) == 2
        repair = provider.body(1)["messages"]
        assert repair[-2] == {"role": "assistant", "content": '{"severity": "severe"}'}
        assert repair[-1]["role"] == "user"
        assert "confidence" in repair[-1]["content"]

    async def test_output_still_invalid_after_the_repair_raises(self) -> None:
        provider = Provider(completion("not json at all"))
        gateway = gateway_for(provider)

        with pytest.raises(LLMOutputError, match="Assessment"):
            await gateway.complete(ASK, Assessment, prompt_version="v1")

        assert len(provider.requests) == 2

    async def test_falls_back_to_json_mode_when_schemas_are_unsupported(self) -> None:
        unsupported = httpx.Response(
            400, json={"error": {"message": "response_format json_schema unsupported"}}
        )
        provider = Provider(unsupported, completion(GOOD))
        gateway = groq(provider, llm_model="llama-3.3-70b-versatile")

        result = await gateway.complete(ASK, Assessment, prompt_version="v1")

        assert result.output.severity == "severe"
        fallback = provider.body(1)
        assert fallback["response_format"] == {"type": "json_object"}
        assert '"confidence"' in fallback["messages"][0]["content"]

        # The gateway remembers, so later calls do not pay for the rejection again
        await gateway.complete(ASK, Assessment, prompt_version="v1")
        assert len(provider.requests) == 3

    async def test_fallback_output_wrapped_in_prose_is_still_read(self) -> None:
        unsupported = httpx.Response(400, json={"error": {"message": "unsupported"}})
        provider = Provider(
            unsupported, completion(f"Here you go:\n```json\n{GOOD}\n```")
        )
        gateway = gateway_for(provider)

        result = await gateway.complete(ASK, Assessment, prompt_version="v1")

        assert result.output.confidence == 0.8
        assert "response_format" not in provider.body(1)

    async def test_schema_mismatch_reported_by_the_provider_is_repaired(self) -> None:
        mismatch = httpx.Response(
            400,
            json={
                "error": {
                    "message": "Generated JSON does not match the expected schema.",
                    "code": "json_validate_failed",
                    "failed_generation": '{"severity": 3}',
                }
            },
        )
        provider = Provider(mismatch, completion(GOOD))
        gateway = groq(provider)

        result = await gateway.complete(ASK, Assessment, prompt_version="v1")

        assert result.output.severity == "severe"
        # Still a schema request: the model failed, not the response format
        assert provider.body(1)["response_format"]["type"] == "json_schema"
        assert provider.body(1)["messages"][-2]["content"] == '{"severity": 3}'


class TestFailures:
    """Test cases for provider failures surfacing as typed errors"""

    async def test_error_status_raises_with_the_providers_message(self) -> None:
        provider = Provider(
            httpx.Response(503, json={"error": {"message": "model is overloaded"}})
        )
        gateway = gateway_for(provider)

        with pytest.raises(LLMError, match=r"lm_studio: HTTP 503: model is overloaded"):
            await gateway.complete(ASK, Assessment, prompt_version="v1")

    async def test_network_failure_raises(self) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        gateway = gateway_for(Provider(refuse))

        with pytest.raises(LLMError, match="connection refused"):
            await gateway.complete(ASK, Assessment, prompt_version="v1")

    async def test_response_without_a_message_raises(self) -> None:
        gateway = gateway_for(Provider(httpx.Response(200, json={"choices": []})))

        with pytest.raises(LLMError, match="unusable response"):
            await gateway.complete(ASK, Assessment, prompt_version="v1")


class TestRateLimits:
    """Test cases for 429 responses"""

    async def test_waits_for_retry_after_then_succeeds(self) -> None:
        limited = httpx.Response(429, headers={"retry-after": "7"})
        provider = Provider(limited, completion(GOOD))
        sleeper = Sleeper()
        gateway = groq(provider, sleeper)

        result = await gateway.complete(ASK, Assessment, prompt_version="v1")

        assert sleeper.waits == [7.0]
        assert result.output.severity == "severe"
        assert result.call.requests == 2

    async def test_wait_longer_than_the_timeout_budget_raises(self) -> None:
        provider = Provider(httpx.Response(429, headers={"retry-after": "600"}))
        sleeper = Sleeper()
        gateway = groq(provider, sleeper, llm_timeout_seconds=30)

        with pytest.raises(LLMRateLimitError, match="600"):
            await gateway.complete(ASK, Assessment, prompt_version="v1")

        assert sleeper.waits == []
        assert len(provider.requests) == 1

    async def test_repeated_limits_stop_once_the_budget_is_spent(self) -> None:
        provider = Provider(httpx.Response(429, headers={"retry-after": "20"}))
        sleeper = Sleeper()
        gateway = groq(provider, sleeper, llm_timeout_seconds=30)

        with pytest.raises(LLMRateLimitError):
            await gateway.complete(ASK, Assessment, prompt_version="v1")

        assert sleeper.waits == [20.0]


class TestConcurrency:
    """Test cases for the per-provider concurrency limit"""

    @pytest.mark.parametrize(
        ("settings", "limit"),
        [
            ({}, 1),
            ({"llm_provider": "groq", "llm_api_key": GROQ_KEY}, 2),
            ({"llm_max_concurrency": 3}, 3),
        ],
    )
    async def test_no_more_than_the_limit_run_at_once(
        self, settings: dict[str, Any], limit: int
    ) -> None:
        running = 0
        peak = 0

        async def slow(_request: httpx.Request) -> httpx.Response:
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            running -= 1
            return completion(GOOD)

        http = httpx.AsyncClient(transport=httpx.MockTransport(slow))
        gateway = LLMGateway.from_settings(Settings(_env_file=None, **settings), http)

        await asyncio.gather(
            *(gateway.complete(ASK, Assessment, prompt_version="v1") for _ in range(6))
        )

        assert peak == limit


class TestCallRecord:
    """Test cases for the record of what served a call"""

    async def test_records_provider_model_prompt_version_tokens_and_latency(
        self,
    ) -> None:
        provider = Provider(completion(GOOD, model="openai/gpt-oss-120b"))
        gateway = groq(provider)

        result = await gateway.complete(ASK, Assessment, prompt_version="analyst-v3")

        call = result.call
        assert call.provider == "groq"
        assert call.model == "openai/gpt-oss-120b"
        assert call.prompt_version == "analyst-v3"
        assert call.prompt_tokens == 11
        assert call.completion_tokens == 7
        assert call.requests == 1
        assert call.latency_ms >= 0

    async def test_tokens_are_summed_across_the_repair(self) -> None:
        provider = Provider(
            completion("{}", prompt=10, output=2), completion(GOOD, prompt=30, output=8)
        )
        gateway = gateway_for(provider)

        result = await gateway.complete(ASK, Assessment, prompt_version="v1")

        assert result.call.prompt_tokens == 40
        assert result.call.completion_tokens == 10
        assert result.call.requests == 2

    async def test_the_model_that_answered_is_recorded_when_none_is_configured(
        self,
    ) -> None:
        provider = Provider(completion(GOOD, model="qwen3-loaded"))
        gateway = gateway_for(provider)

        result = await gateway.complete(ASK, Assessment, prompt_version="v1")

        assert "model" not in provider.body(0)
        assert result.call.model == "qwen3-loaded"


class TestKeySecrecy:
    """Test cases for the API key staying out of errors and logs"""

    async def test_key_echoed_by_the_provider_is_redacted(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        def echo(request: httpx.Request) -> httpx.Response:
            message = f"bad credentials: {request.headers['authorization']}"
            return httpx.Response(401, json={"error": {"message": message}})

        gateway = groq(Provider(echo))

        with (
            caplog.at_level(logging.DEBUG),
            pytest.raises(LLMError, match="HTTP 401") as raised,
        ):
            await gateway.complete(ASK, Assessment, prompt_version="v1")

        assert GROQ_KEY not in str(raised.value)
        assert GROQ_KEY not in caplog.text

    def test_key_is_not_shown_when_settings_are_printed(self) -> None:
        settings = Settings(_env_file=None, llm_provider="groq", llm_api_key=GROQ_KEY)

        assert GROQ_KEY not in repr(settings)
        assert GROQ_KEY not in settings.model_dump_json()


class TestAvailability:
    """Test cases for LLMGateway.availability"""

    async def test_lm_studio_reports_the_loaded_model(self) -> None:
        models = {
            "data": [
                {"id": "nomic-embed", "type": "embeddings", "state": "loaded"},
                {"id": "qwen3-8b", "type": "llm", "state": "loaded"},
                {"id": "qwen3-14b", "type": "llm", "state": "not-loaded"},
            ]
        }
        provider = Provider(httpx.Response(200, json=models))
        gateway = gateway_for(provider)

        availability = await gateway.availability(timeout_seconds=1)

        assert str(provider.requests[0].url) == "http://localhost:1234/api/v0/models"
        assert availability.available
        assert availability.message == "lm_studio: qwen3-8b is loaded"

    async def test_lm_studio_configured_model_must_be_the_loaded_one(self) -> None:
        models = {"data": [{"id": "qwen3-8b", "type": "llm", "state": "not-loaded"}]}
        gateway = gateway_for(
            Provider(httpx.Response(200, json=models)), llm_model="qwen3-8b"
        )

        availability = await gateway.availability(timeout_seconds=1)

        assert not availability.available
        assert availability.message == "lm_studio: qwen3-8b is not loaded"

    async def test_lm_studio_with_nothing_loaded(self) -> None:
        gateway = gateway_for(Provider(httpx.Response(200, json={"data": []})))

        availability = await gateway.availability(timeout_seconds=1)

        assert not availability.available
        assert availability.message == "lm_studio: no model is loaded"

    async def test_groq_reports_whether_the_key_can_use_the_model(self) -> None:
        provider = Provider(
            httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}]})
        )
        gateway = groq(provider)

        availability = await gateway.availability(timeout_seconds=1)

        request = provider.requests[0]
        assert str(request.url) == "https://api.groq.com/openai/v1/models"
        assert request.headers["authorization"] == f"Bearer {GROQ_KEY}"
        assert availability.available
        assert availability.message == "groq: openai/gpt-oss-120b is available"

    async def test_groq_model_missing_from_the_keys_models(self) -> None:
        provider = Provider(httpx.Response(200, json={"data": [{"id": "other"}]}))
        gateway = groq(provider)

        availability = await gateway.availability(timeout_seconds=1)

        assert not availability.available
        assert availability.message == "groq: openai/gpt-oss-120b is not available"

    async def test_unreachable_provider_is_reported_not_raised(self) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        availability = await gateway_for(Provider(refuse)).availability(
            timeout_seconds=1
        )

        assert not availability.available
        assert availability.message == "lm_studio: unreachable"

    async def test_rejected_key_is_reported_without_the_key(self) -> None:
        gateway = groq(Provider(httpx.Response(401, json={"error": GROQ_KEY})))

        availability = await gateway.availability(timeout_seconds=1)

        assert not availability.available
        assert availability.message == "groq: HTTP 401"

    async def test_slow_provider_is_cut_off_at_the_timeout(self) -> None:
        async def hang(_request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(5)
            return httpx.Response(200, json={"data": []})

        http = httpx.AsyncClient(transport=httpx.MockTransport(hang))
        gateway = LLMGateway.from_settings(Settings(_env_file=None), http)

        availability = await gateway.availability(timeout_seconds=0.05)

        assert not availability.available
        assert availability.message == "lm_studio: timed out"
