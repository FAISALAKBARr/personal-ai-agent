from app.agents.providers import (
    ClaudeProvider,
    FallbackProvider,
    GeminiProvider,
    OllamaProvider,
    OpenRouterProvider,
    get_provider,
)
from app.core.config import Settings


def _chain_types(provider):
    if isinstance(provider, FallbackProvider):
        return [type(p).__name__ for p in provider.providers]
    return [type(provider).__name__]


def test_no_cloud_keys_returns_bare_ollama_provider():
    settings = Settings(openrouter_api_key=None, gemini_api_key=None, anthropic_api_key=None)
    provider = get_provider(settings)
    assert isinstance(provider, OllamaProvider)


def test_single_cloud_key_wraps_with_ollama_fallback():
    settings = Settings(openrouter_api_key="sk-or-fake", gemini_api_key=None, anthropic_api_key=None)
    assert _chain_types(get_provider(settings)) == ["OpenRouterProvider", "OllamaProvider"]


def test_chain_order_is_openrouter_gemini_claude_ollama():
    settings = Settings(openrouter_api_key="sk-or-fake", gemini_api_key="g-fake", anthropic_api_key="sk-ant-fake")
    assert _chain_types(get_provider(settings)) == [
        "OpenRouterProvider",
        "GeminiProvider",
        "ClaudeProvider",
        "OllamaProvider",
    ]


def test_gemini_only_skips_openrouter_and_claude():
    settings = Settings(openrouter_api_key=None, gemini_api_key="g-fake", anthropic_api_key=None)
    assert _chain_types(get_provider(settings)) == ["GeminiProvider", "OllamaProvider"]
