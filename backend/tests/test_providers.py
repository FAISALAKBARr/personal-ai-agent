import json

import httpx
import pytest

from app.agents.providers import FallbackProvider


def _http_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(str(status_code), request=request, response=response)


class _WorkingProvider:
    async def complete_json(self, system_prompt, user_message):
        return {"ok": True}


class _TransientFailProvider:
    """Simulates a provider that's temporarily down (e.g. 503)."""

    async def complete_json(self, system_prompt, user_message):
        raise _http_error(503)


class _MalformedJsonProvider:
    """Simulates a provider that broke the 'must return valid JSON' contract."""

    async def complete_json(self, system_prompt, user_message):
        raise json.JSONDecodeError("bad json", "not json", 0)


class _AuthFailProvider:
    """Simulates a misconfigured provider (bad API key) — must NOT be papered over."""

    async def complete_json(self, system_prompt, user_message):
        raise _http_error(401)


class _BuggyProvider:
    """Simulates a genuine programming bug, unrelated to any provider's availability."""

    async def complete_json(self, system_prompt, user_message):
        raise RuntimeError("boom")


async def test_falls_back_on_transient_5xx():
    provider = FallbackProvider([_TransientFailProvider(), _WorkingProvider()])
    assert await provider.complete_json("sys", "user") == {"ok": True}


async def test_falls_back_on_malformed_json():
    provider = FallbackProvider([_MalformedJsonProvider(), _WorkingProvider()])
    assert await provider.complete_json("sys", "user") == {"ok": True}


async def test_does_not_mask_auth_errors():
    provider = FallbackProvider([_AuthFailProvider(), _WorkingProvider()])
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await provider.complete_json("sys", "user")
    assert exc_info.value.response.status_code == 401


async def test_does_not_mask_unexpected_bugs():
    provider = FallbackProvider([_BuggyProvider(), _WorkingProvider()])
    with pytest.raises(RuntimeError):
        await provider.complete_json("sys", "user")


async def test_uses_first_provider_when_it_succeeds():
    provider = FallbackProvider([_WorkingProvider(), _AuthFailProvider()])
    assert await provider.complete_json("sys", "user") == {"ok": True}


def test_requires_at_least_one_provider():
    with pytest.raises(ValueError):
        FallbackProvider([])
