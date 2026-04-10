from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"  # 👈 prevents crash from unused env vars
    )

    # Core
    host_url: str
    api_key: str
    app_env: str = "development"

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # App settings
    require_tls: bool = False
    fetch_rate_limit_per_minute: int = 120

    # S3 Config
    s3_bucket_name: str = "retail-search"
    s3_region: str = "ap-south-1"
    s3_endpoint_url: str = ""
    s3_allowed_clients: str = ""
    s3_allowed_datasets: str = ""
    s3_max_upload_mb: int = 100
    s3_list_max_keys: int = 500
    s3_presign_expiry_seconds: int = 900
    s3_api_key: str = ""

    # AWS Credentials
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_session_token: str = ""

    # Optional ES (if present in .env, won't crash now)
    es_host: str | None = None
    es_port: int | None = None
    es_scheme: str | None = None

    @property
    def meili_url(self):
        return self.host_url

    @property
    def parsed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def parsed_s3_allowed_clients(self) -> set[str]:
        return {item.strip().lower() for item in self.s3_allowed_clients.split(",") if item.strip()}

    @property
    def parsed_s3_allowed_datasets(self) -> set[str]:
        return {item.strip().lower() for item in self.s3_allowed_datasets.split(",") if item.strip()}


settings = Settings()