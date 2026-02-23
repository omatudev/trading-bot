from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Alpaca
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"

    # LLM
    gemini_api_key: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://neondb_owner:npg_tm6h1dowkXDg@ep-cool-river-aijc9n18-pooler.c-4.us-east-1.aws.neon.tech/neondb?ssl=require"

    # CORS
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    # Logging
    log_level: str = "WARNING"

    # Auth
    google_client_id: str = "879038766799-lihogd5k6ed49n9gbv29min1mftfp78h.apps.googleusercontent.com"
    allowed_email: str = "omatu.personal@gmail.com"
    jwt_secret: str = "change-me-in-production"
    jwt_expiration_days: int = 7

    # Trading Rules
    take_profit_pct: float = 10.0
    max_position_days_red: int = 15
    min_profit_to_exit_red: float = 0.5
    extraordinary_gap_sell_pct: float = 60.0
    ticker_profile_recalc_days: int = 30
    ticker_profile_months: int = 4
    threshold_change_alert_pct: float = 30.0

    # Schedule (hours/minutes ET)
    schedule_pre_open: str = "9:20"
    schedule_open: str = "9:30"
    schedule_mid: str = "10:00"
    schedule_pre_close: str = "3:30"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
