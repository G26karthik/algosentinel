from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    gemini_api_key: str = ""
    github_token: str = ""
    github_webhook_secret: str = ""

    gemini_model: str = "gemini-2.5-flash"
    gemini_max_rpm: int = 14
    gemini_max_tokens: int = 8192
    gemini_thinking_budget: int = 0
    context_compress_every_n_calls: int = 6
    max_input_size_benchmark: int = 10000
    sandbox_timeout_seconds: int = 30
    sandbox_docker_image: str = "python:3.11-slim"

    min_regression_confidence: float = 0.85
    severity_critical_threshold: int = 2

    log_level: str = "INFO"
    log_format: str = "json"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
