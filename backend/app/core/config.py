from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database — two URLs on purpose: the app uses the async driver,
    # APScheduler's SQLAlchemyJobStore needs a sync one.
    database_url: str = "postgresql+asyncpg://agent:agent@localhost:5432/agent"
    database_url_sync: str = "postgresql://agent:agent@localhost:5432/agent"

    redis_url: str = "redis://localhost:6379/0"

    # AI providers — tried in this order in agents/providers.py:get_provider():
    # OpenRouter -> Gemini -> Claude -> Ollama. Ollama needs no key and is
    # always last.
    openrouter_api_key: str | None = None
    openrouter_model: str = "openrouter/free"

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.7-flash"

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-6"

    # WhatsApp
    whatsapp_provider: str = "mock"  # "mock" | "baileys" | "cloud_api"
    whatsapp_allowed_numbers: str = ""  # comma-separated E.164 numbers
    whatsapp_webhook_secret: str = "changeme"
    baileys_bridge_url: str = "http://localhost:3000"

    # Misc
    app_secret_key: str = "changeme"
    debug: bool = True

    @property
    def allowed_numbers_list(self) -> list[str]:
        return [n.strip() for n in self.whatsapp_allowed_numbers.split(",") if n.strip()]


settings = Settings()
