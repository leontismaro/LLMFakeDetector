from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "LLM Fake Detector API")
    app_version: str = os.getenv("APP_VERSION", "0.1.0")
    default_timeout_seconds: int = int(os.getenv("DEFAULT_TIMEOUT_SECONDS", "30"))
    use_env_proxy: bool = os.getenv("USE_ENV_PROXY", "").lower() in {"1", "true", "yes", "on"}
    outbound_user_agent: str = os.getenv("OUTBOUND_USER_AGENT", "curl/8.7.1")


settings = Settings()
