"""Application settings, read from the environment (or a local .env file).

Every tunable value lives here rather than inline at its use site — the stale-alert
thresholds in particular are each read from more than one place, so they must have a
single home (see docs/architecture.md, "Stale alerts").
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = (
        "postgresql+psycopg://expense:expense@localhost:5432/expense_reimbursement"
    )

    jwt_secret: str = "dev-only-secret-do-not-use-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24

    # Comma-separated in the environment; split into a list by cors_origin_list below.
    cors_origins: str = "http://localhost:5173"

    # Goal 10. N = how long Submitted may sit before it is stale;
    # M = how long a dismissal suppresses the alert before it returns.
    stale_after_days: int = 5
    stale_realert_after_days: int = 3

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
