"""Configuracion central de JobFlow AI."""
import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover
    pass


def _bool(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    data_dir: Path = Path(os.getenv("JOBFLOW_DATA_DIR", "data"))
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///data/jobflow.db")
    port: int = int(os.getenv("PORT", "8000"))
    llm_provider: str = os.getenv("LLM_PROVIDER", "none").lower()
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat")
    headless: bool = _bool(os.getenv("JOBFLOW_HEADLESS", "true"))
    confirm_before_submit: bool = _bool(os.getenv("JOBFLOW_CONFIRM", "true"))
    # SMTP opcional: si se configura, los correos se envian de verdad
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_pass: str = os.getenv("SMTP_PASS", "")


settings = Settings()
