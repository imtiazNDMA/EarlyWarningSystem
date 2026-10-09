"""Gateway to the language model: one typed call, whichever provider serves it."""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Self, TypedDict

import httpx
from pydantic import BaseModel, ValidationError

from ews.core.settings import Settings

logger = logging.getLogger(__name__)

Provider = Literal["lm_studio", "groq"]


@dataclass(frozen=True)
class ProviderDefaults:
    """What a provider uses when the matching setting is unset."""

    base_url: str
    model: str | None
    # A local server runs one generation at a time; a cloud API takes several
    max_concurrency: int
    # response_format used once JSON-schema output has been rejected
    json_mode: dict[str, str] | None


PROVIDER_DEFAULTS: dict[Provider, ProviderDefaults] = {
    "lm_studio": ProviderDefaults(
        base_url="http://localhost:1234/v1",
        model=None,
        max_concurrency=1,
        json_mode=None,
    ),
    "groq": ProviderDefaults(
        base_url="https://api.groq.com/openai/v1",
        model="openai/gpt-oss-120b",
        max_concurrency=2,
        json_mode={"type": "json_object"},
    ),
}

# Groq's code for output that did not match a best-effort JSON schema
SCHEMA_MISMATCH_CODE = "json_validate_failed"
# Floor on the wait after a 429, so a zero or missing Retry-After cannot spin
MIN_RETRY_WAIT_SECONDS = 1.0


class LLMError(Exception):
    """The model could not be reached or answered with something unusable."""

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider


class LLMRateLimitError(LLMError):
    """The provider's rate limit could not be waited out within the timeout."""


class LLMOutputError(LLMError):
    """The model's output did not match the requested type, even after a repair."""


class Message(TypedDict):
    """One chat message."""

    role: Literal["system", "user", "assistant"]
    content: str


class LLMCall(BaseModel):
    """What served one call, so a result can be reproduced and compared."""

    provider: Provider
    model: str
    prompt_version: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    # Requests the provider answered, counting rate-limit retries and the repair
    requests: int


@dataclass(frozen=True)
class Completion[T: BaseModel]:
    """A validated result and the record of the call that produced it."""

    output: T
    call: LLMCall


class ModelAvailability(BaseModel):
    """Whether the configured model can serve a call right now."""

    available: bool
    message: str


@dataclass
class _Usage:
    """Running totals across the requests of one call."""

    model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    requests: int = 0


class LLMGateway:
    """Calls an OpenAI-compatible chat-completions endpoint for typed results."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        provider: Provider,
        base_url: str,
        model: str | None,
        api_key: str | None,
        temperature: float,
        timeout_seconds: float,
        max_concurrency: int,
        json_mode: dict[str, str] | None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._http = http
        self._provider: Provider = provider
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._temperature = temperature
        self._timeout_seconds = timeout_seconds
        self._slots = asyncio.Semaphore(max_concurrency)
        self._json_mode = json_mode
        self._sleep = sleep
        # Cleared for good the first time the provider rejects a JSON schema
        self._schema_supported = True

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        http: httpx.AsyncClient,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> Self:
        """Build the gateway for the configured provider."""
        defaults = PROVIDER_DEFAULTS[settings.llm_provider]
        key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else ""
        return cls(
            http,
            provider=settings.llm_provider,
            base_url=settings.llm_base_url or defaults.base_url,
            model=settings.llm_model or defaults.model,
            api_key=key or None,
            temperature=settings.llm_temperature,
            timeout_seconds=settings.llm_timeout_seconds,
            max_concurrency=settings.llm_max_concurrency or defaults.max_concurrency,
            json_mode=defaults.json_mode,
            sleep=sleep,
        )

    async def complete[T: BaseModel](
        self, messages: Sequence[Message], output_type: type[T], *, prompt_version: str
    ) -> Completion[T]:
        """Ask the model for an object of the given type.

        Args:
            messages: The conversation to send
            output_type: Model the reply must validate against
            prompt_version: Version of the prompt in use, kept on the call record

        Returns:
            The validated object and the record of what served it

        Raises:
            LLMOutputError: If the reply is still invalid after one repair
            LLMRateLimitError: If a rate limit outlasts the timeout
            LLMError: On a network failure, an error status or a bad response
        """
        started = time.monotonic()
        usage = _Usage()
        conversation = list(messages)
        problems = ""

        # The request itself, then one repair
        for _ in range(2):
            reply = await self._generate(conversation, output_type, usage)
            try:
                output = output_type.model_validate_json(_json_object(reply))
            except ValidationError as error:
                problems = json.dumps(
                    error.errors(include_url=False, include_input=False), default=str
                )
                conversation += [
                    {"role": "assistant", "content": reply},
                    {
                        "role": "user",
                        "content": "That reply was not valid: "
                        f"{problems}. Reply again with only the corrected JSON object.",
                    },
                ]
                continue

            call = LLMCall(
                provider=self._provider,
                model=usage.model or self._model or "unknown",
                prompt_version=prompt_version,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                latency_ms=round((time.monotonic() - started) * 1000),
                requests=usage.requests,
            )
            logger.info("LLM call served: %s", call.model_dump_json())
            return Completion(output=output, call=call)

        raise LLMOutputError(
            self._provider,
            f"output did not match {output_type.__name__} after one repair: {problems}",
        )

    async def availability(self, timeout_seconds: float) -> ModelAvailability:
        """Report whether the configured model can serve a call; never raises."""
        try:
            async with asyncio.timeout(timeout_seconds):
                return await self._availability()
        except TimeoutError:
            return self._unavailable("timed out")
        except httpx.HTTPError:
            return self._unavailable("unreachable")
        except (ValueError, KeyError, TypeError, AttributeError):
            return self._unavailable("unusable response")

    async def _availability(self) -> ModelAvailability:
        if self._provider == "lm_studio":
            # The OpenAI-compatible listing includes models that are only
            # downloaded; LM Studio's own API says which are loaded
            url = str(httpx.URL(self._base_url).copy_with(path="/api/v0/models"))
        else:
            url = f"{self._base_url}/models"
        response = await self._http.get(url, headers=self._headers())
        if response.status_code != httpx.codes.OK:
            return self._unavailable(f"HTTP {response.status_code}")

        models = response.json()["data"]
        if self._provider == "lm_studio":
            ready = "loaded"
            ids = [
                model["id"]
                for model in models
                if model.get("state") == "loaded" and model.get("type") != "embeddings"
            ]
        else:
            ready = "available"
            ids = [model["id"] for model in models]

        wanted = self._model or (ids[0] if ids else None)
        if wanted is None:
            return self._unavailable(f"no model is {ready}")
        if wanted not in ids:
            return self._unavailable(f"{wanted} is not {ready}")
        return ModelAvailability(
            available=True, message=f"{self._provider}: {wanted} is {ready}"
        )

    def _unavailable(self, reason: str) -> ModelAvailability:
        return ModelAvailability(available=False, message=f"{self._provider}: {reason}")

    async def _generate(
        self, conversation: list[Message], output_type: type[BaseModel], usage: _Usage
    ) -> str:
        """Return the model's reply text for the conversation."""
        schema = output_type.model_json_schema()
        if self._schema_supported:
            response = await self._post(
                conversation,
                {
                    "type": "json_schema",
                    "json_schema": {"name": output_type.__name__, "schema": schema},
                },
                usage,
            )
            if response.status_code != httpx.codes.BAD_REQUEST:
                return self._reply(response, usage)
            error = _error_body(response)
            if error.get("code") == SCHEMA_MISMATCH_CODE:
                # The model failed, not the format: hand it back for the repair
                return str(error.get("failed_generation") or "")
            logger.warning(
                "%s rejected a JSON-schema response format (%s); using JSON mode",
                self._provider,
                self._redact(str(error.get("message") or response.text[:200])),
            )
            self._schema_supported = False

        instruction: Message = {
            "role": "system",
            "content": "Reply with a single JSON object and nothing else. "
            f"It must match this JSON Schema: {json.dumps(schema)}",
        }
        response = await self._post(
            [instruction, *conversation], self._json_mode, usage
        )
        return self._reply(response, usage)

    async def _post(
        self,
        conversation: Sequence[Message],
        response_format: dict[str, Any] | None,
        usage: _Usage,
    ) -> httpx.Response:
        """Send one request, waiting out rate limits within the timeout."""
        body: dict[str, Any] = {
            "messages": conversation,
            "temperature": self._temperature,
        }
        if self._model:
            body["model"] = self._model
        if response_format:
            body["response_format"] = response_format

        waited = 0.0
        async with self._slots:
            while True:
                try:
                    response = await self._http.post(
                        f"{self._base_url}/chat/completions",
                        json=body,
                        headers=self._headers(),
                        timeout=self._timeout_seconds,
                    )
                except httpx.HTTPError as error:
                    raise LLMError(
                        self._provider, f"request failed: {self._redact(str(error))}"
                    ) from error
                usage.requests += 1
                if response.status_code != httpx.codes.TOO_MANY_REQUESTS:
                    return response

                wait = max(_retry_after(response), MIN_RETRY_WAIT_SECONDS)
                if waited + wait > self._timeout_seconds:
                    raise LLMRateLimitError(
                        self._provider,
                        f"rate limited; retrying after {wait:g}s would exceed the "
                        f"{self._timeout_seconds:g}s timeout",
                    )
                logger.warning(
                    "%s rate limit reached; retrying in %gs", self._provider, wait
                )
                await self._sleep(wait)
                waited += wait

    def _reply(self, response: httpx.Response, usage: _Usage) -> str:
        """Read the reply text and add the request's token counts to the totals."""
        if response.status_code != httpx.codes.OK:
            reason = _error_body(response).get("message") or response.text[:200]
            raise LLMError(
                self._provider,
                f"HTTP {response.status_code}: {self._redact(str(reason))}",
            )
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            tokens = body.get("usage") or {}
            usage.prompt_tokens += int(tokens.get("prompt_tokens") or 0)
            usage.completion_tokens += int(tokens.get("completion_tokens") or 0)
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
            raise LLMError(self._provider, "unusable response") from error
        usage.model = body.get("model") or usage.model
        return str(content or "")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

    def _redact(self, text: str) -> str:
        """Remove the API key from text bound for a log or an error."""
        return text.replace(self._api_key, "[redacted]") if self._api_key else text


def _error_body(response: httpx.Response) -> dict[str, Any]:
    """The provider's error object, or an empty one when it sent none."""
    try:
        error = response.json()["error"]
    except (ValueError, KeyError, TypeError):
        return {}
    return error if isinstance(error, dict) else {}


def _retry_after(response: httpx.Response) -> float:
    """Seconds the provider asked for; zero when it did not say."""
    try:
        return float(response.headers.get("retry-after", 0))
    except ValueError:
        return 0.0


def _json_object(reply: str) -> str:
    """Cut a reply down to its JSON object, dropping fences or prose around it."""
    start, end = reply.find("{"), reply.rfind("}")
    return reply[start : end + 1] if 0 <= start < end else reply
