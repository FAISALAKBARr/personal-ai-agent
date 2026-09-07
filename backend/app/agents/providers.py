import json
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
                    # latency-sensitive tool-call path. This is most of why the
                    # first end-to-end test took 61s.
                    "think": False,
                },
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"]
            return json.loads(content)


class OpenRouterProvider(AIProvider):
    """OpenAI-compatible. Default model 'openrouter/free' auto-picks a free
    model that supports structured outputs + tool calling — verified current
    as of Sept 2026, not just carried over from the other conversation's
    advice. Rate limits: 20 req/min, 50/day unfunded (1,000/day after any
    $10+ credit purchase, permanently)."""

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
    """Google Gemini, classic generateContent REST endpoint (still fully
    supported as of mid-2026 alongside the newer Interactions API — this one
    is simpler and enough for our needs). Free tier via Google AI Studio,
    no billing required. Default model verified current as of Sept 2026."""

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
    """Tries each provider in order, moving to the next on ANY failure
    (rate limit, network error, timeout, bad JSON, whatever). This is what
    actually makes a free-first setup reliable rather than just cheap —
    a 50-requests/day cap WILL get hit, and when it does, the agent should
    degrade to the next option instead of just failing."""

    def __init__(self, providers: list[AIProvider]):
        if not providers:
            raise ValueError("FallbackProvider needs at least one provider")
        self.providers = providers

    async def complete_json(self, system_prompt: str, user_message: str) -> dict:
        last_error: Exception | None = None
        for provider in self.providers:
            try:
                return await provider.complete_json(system_prompt, user_message)
            except Exception as e:  # noqa: BLE001 - deliberately broad, see docstring
                print(f"[FallbackProvider] {type(provider).__name__} failed ({e!r}), trying next...")
                last_error = e
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

    return chain[0] if len(chain) == 1 else FallbackProvider(chain)
