import pytest

from app.agents.providers import FallbackProvider


class _FailingProvider:
    async def complete_json(self, system_prompt, user_message):
        raise RuntimeError("simulated provider failure")


class _WorkingProvider:
    async def complete_json(self, system_prompt, user_message):
        return {"ok": True}


async def test_fallback_moves_to_next_provider_on_failure():
    provider = FallbackProvider([_FailingProvider(), _WorkingProvider()])
    result = await provider.complete_json("sys", "user")
    assert result == {"ok": True}


async def test_fallback_uses_first_provider_when_it_succeeds():
    provider = FallbackProvider([_WorkingProvider(), _FailingProvider()])
    result = await provider.complete_json("sys", "user")
    assert result == {"ok": True}


async def test_fallback_raises_last_error_if_all_fail():
    with pytest.raises(RuntimeError, match="simulated provider failure"):
        await FallbackProvider([_FailingProvider(), _FailingProvider()]).complete_json("sys", "user")


def test_fallback_requires_at_least_one_provider():
    with pytest.raises(ValueError):
        FallbackProvider([])
