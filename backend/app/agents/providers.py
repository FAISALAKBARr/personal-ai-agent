import json
import time
from abc import ABC, abstractmethod

import httpx

from ..core.config import Settings


class AIProvider(ABC):
    @abstractmethod
    async def complete_json(self, system_prompt: str, user_message: str) -> dict:
        """Return a parsed dict. Implementations must force valid JSON output —
        do not rely on the model's native 'tool calling' API. Small local models
        are unreliable at that; asking for plain constrained JSON and parsing it
        ourselves is the more robust pattern (see architecture doc §9)."""
        raise NotImplementedError


class OllamaProvider(AIProvider):
    def __init__(self, host: str, model: str):
        self.host = host.rstrip("/")
        self.model = model

    async def complete_json(self, system_prompt: str, user_message: str) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "format": "json",  # Ollama grammar-constrains output to valid JSON
                    "stream": False,
                    # Reasoning models (qwen3, deepseek-r1, etc.) think out loud
                    # before answering by default — fine for chat, bad for a
                    # latency-sensitive tool-call path.
                    "think": False,
                },
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"]
            return json.loads(content)


class OpenRouterProvider(AIProvider):
    """OpenAI-compatible OpenRouter provider.

    Uses OpenRouter's free-model router ('openrouter/free') by default, which
    picks a currently-available free model filtered for structured-output
    support. Note: the agent does NOT rely on native model tool-calling —
    the model only ever returns structured JSON here; the orchestrator
    (app/agents/orchestrator.py) is what decides whether and how to run a
    tool via TOOL_REGISTRY. The provider has no authority to execute anything.

    Rate limits as of Sept 2026: 20 req/min, 50/day unfunded (1,000/day after
    any $10+ credit purchase — never a hard requirement of this system,
    the $0 path through Gemini/Ollama must keep working regardless).
    """

    def __init__(self, api_key: str, model: str = "openrouter/free"):
        self.api_key = api_key
        self.model = model

    async def complete_json(self, system_prompt: str, user_message: str) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)


class GeminiProvider(AIProvider):
    """Google Gemini, classic generateContent REST endpoint. Free tier via
    Google AI Studio, no billing required. Same non-authority note as
    OpenRouter above applies — this only returns JSON, never executes."""

    def __init__(self, api_key: str, model: str = "gemini-3.7-flash"):
        self.api_key = api_key
        self.model = model

    async def complete_json(self, system_prompt: str, user_message: str) -> dict:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                url,
                headers={"x-goog-api-key": self.api_key},
                json={
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"role": "user", "parts": [{"text": user_message}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)


class ClaudeProvider(AIProvider):
    def __init__(self, api_key: str, model: str):
        # Imported lazily so `anthropic` isn't a hard dependency when unused.
        from anthropic import AsyncAnthropic

        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    async def complete_json(self, system_prompt: str, user_message: str) -> dict:
        resp = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system_prompt + "\n\nRespond with ONLY valid JSON. No prose, no markdown fences.",
            messages=[{"role": "user", "content": user_message}],
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        return json.loads(text)


class FallbackProvider(AIProvider):
    """
    Tries each provider in order, but only advances to the next on failures
    that are actually about THAT provider being temporarily unavailable —
    rate limited (429), down (5xx), a network/timeout hiccup, or it broke
    the JSON contract. Config/auth errors (400/401/403) are NOT treated as
    fallback triggers: silently routing around a bad API key would hide a
    real misconfiguration instead of surfacing it, and letting the next
    provider quietly cover for a bug is worse than a clear failure.
    """

    TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(self, providers: list[AIProvider]):
        if not providers:
            raise ValueError("FallbackProvider needs at least one provider")
        self.providers = providers

    @classmethod
    def _is_transient(cls, error: Exception) -> bool:
        if isinstance(error, httpx.HTTPStatusError):
            return error.response.status_code in cls.TRANSIENT_STATUS_CODES
        if isinstance(error, (httpx.TimeoutException, httpx.NetworkError)):
            return True
        if isinstance(error, json.JSONDecodeError):
            return True  # provider broke the "must return valid JSON" contract
        return False

    async def complete_json(self, system_prompt: str, user_message: str) -> dict:
        last_error: Exception | None = None
        for provider in self.providers:
            name = type(provider).__name__
            started = time.monotonic()
            try:
                result = await provider.complete_json(system_prompt, user_message)
                print(f"provider={name} latency={time.monotonic() - started:.2f}s status=success")
                return result
            except Exception as error:
                latency = time.monotonic() - started
                last_error = error
                if self._is_transient(error):
                    print(
                        f"provider={name} latency={latency:.2f}s status=transient_failure "
                        f"error={error!r} action=fallback_to_next"
                    )
                    continue
                print(
                    f"provider={name} latency={latency:.2f}s status=permanent_failure "
                    f"error={error!r} action=raise_immediately"
                )
                raise
        raise last_error


def get_provider(settings: Settings) -> AIProvider:
    """
    Builds the fallback chain from whichever credentials are actually
    configured: OpenRouter -> Gemini -> Claude -> Ollama. Ollama has no key
    requirement so it's always included as the guaranteed-available last
    resort — this is what keeps the system "architecturally functional when
    paid AI providers are disabled" per the spec's own design principle (§2).
    Leave a key blank in .env to skip that provider entirely.
    """
    chain: list[AIProvider] = []

    if settings.openrouter_api_key:
        chain.append(OpenRouterProvider(settings.openrouter_api_key, settings.openrouter_model))

    if settings.gemini_api_key:
        chain.append(GeminiProvider(settings.gemini_api_key, settings.gemini_model))

    if settings.anthropic_api_key:
        chain.append(ClaudeProvider(settings.anthropic_api_key, settings.anthropic_model))

    chain.append(OllamaProvider(settings.ollama_host, settings.ollama_model))

    # Always wrapped, even for a single provider — functionally identical
    # (nothing to fall back to if it fails), but keeps the latency/outcome
    # logging in FallbackProvider consistently present regardless of how
    # many providers happen to be configured.
    return FallbackProvider(chain)
