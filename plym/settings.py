from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PLYM_", env_file=".env", extra="ignore")

    debug: bool = False

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "plym"
    db_user: str = "plym"
    db_password: str = "plym"

    superuser_email: str = "admin@plym.local"
    superuser_password: str = "changeme"

    jwt_secret: str = Field(min_length=16)
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 2_592_000

    upload_max_bytes: int = 10 * 1024 * 1024
    config_path: Path = Path("config.yaml")

    service_name: str = "plym"
    trace_exporter: str = "console"
    otlp_endpoint: str = "http://localhost:4317"
    trace_sample: float = 1.0
    trace_slow_ms: int = 200
    trace_args: bool = False
    trace_color: bool | None = None

    base_dir: Path = Path(__file__).resolve().parent.parent
    storage_dir: Path = Path("storage")
    uploads_dir: Path = Path("storage/_uploads")
    generated_dir: Path = Path("storage/.generated")
    backups_dir: Path = Path("storage/backups")
    fonts_dir: Path = Path("storage/webfonts")
    static_dir: Path = Path("storage/static")
    templates_dir: Path = Path("plym/templates")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
