"""
Manual smoke test for every configured AI provider. Exercises the actual
GeminiProvider / OpenRouterProvider / OllamaProvider classes from the app —
not just a raw HTTP ping — so a pass here means the real code path works,
not just "the API happens to be reachable".

Run inside the backend container:
    docker compose exec backend python scripts/test_providers.py

No inline shell quoting needed — that's the whole point of this file.
"""

import asyncio
import sys
from pathlib import Path

# Running this as `python scripts/test_providers.py` only puts scripts/ on
# sys.path, not the backend root — so `import app...` fails even though the
# app package is right there one level up. Fix it explicitly so this script
# works the same way no matter how it's invoked.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.providers import GeminiProvider, OllamaProvider, OpenRouterProvider  # noqa: E402
from app.core.config import settings  # noqa: E402

TEST_SYSTEM = 'Respond with ONLY a JSON object shaped like {"answer": "..."}. No other text.'
TEST_USER = "What is the capital of Indonesia?"


async def _try(name: str, provider) -> None:
    print(f"--- {name} ---")
    try:
        result = await provider.complete_json(TEST_SYSTEM, TEST_USER)
        print(f"OK: {result}")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
    print()


async def main() -> None:
    if settings.gemini_api_key:
        await _try("Gemini", GeminiProvider(settings.gemini_api_key, settings.gemini_model))
    else:
        print("--- Gemini --- SKIPPED (GEMINI_API_KEY not set)\n")

    if settings.openrouter_api_key:
        await _try("OpenRouter", OpenRouterProvider(settings.openrouter_api_key, settings.openrouter_model))
    else:
        print("--- OpenRouter --- SKIPPED (OPENROUTER_API_KEY not set)\n")

    # Ollama needs no key, always tested
    await _try("Ollama", OllamaProvider(settings.ollama_host, settings.ollama_model))


if __name__ == "__main__":
    asyncio.run(main())
