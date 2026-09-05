from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Anthropic
    anthropic_api_key: str = ""

    # Adzuna
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "in"

    # Database
    database_url: str = "sqlite:///./apply_assist.db"

    # Email
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    digest_from_email: str = ""
    digest_to_email: str = ""

    # Scheduler
    job_fetch_cron_hour: int = 6
    digest_cron_day_of_week: str = "mon"
    digest_cron_hour: int = 9

    # CORS
    frontend_origin: str = "http://localhost:5173"

    # Browser extension import — the extension must send this key in the
    # X-Extension-Key header, so random callers can't write into your DB.
    extension_api_key: str = "change_me_to_a_long_random_string"


settings = Settings()
