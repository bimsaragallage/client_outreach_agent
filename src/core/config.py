from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import yaml
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ========== LLM Configuration ==========
    groq_api_key: Optional[str] = None

    # ========== Email Configuration ==========
    sendgrid_api_key: Optional[str] = None
    smtp_host: Optional[str] = "smtp.gmail.com"
    smtp_port: Optional[int] = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    from_email: Optional[str] = "outreach@company.com"
    imap_server: Optional[str] = None
    imap_port: Optional[int] = 993
    app_password: Optional[str] = None

    # ========== Storage ==========
    chroma_persist_dir: Optional[str] = "./data/memory"

    # ========== Feature Flags ==========
    enable_ab_testing: bool = False
    dry_run_mode: bool = False
    log_level: str = "INFO"


def load_yaml_config(config_path: str = "configs/settings.yaml") -> dict:
    """Load additional configuration from YAML file if present."""
    path = Path(config_path)
    if path.exists():
        with open(path, "r") as f:
            return yaml.safe_load(f)
    return {}


# Global settings instance
settings = Settings()
yaml_config = load_yaml_config()