import os
from pathlib import Path

# Safeguard for Linux snap sandboxing when reading distro information
try:
    import distro
    distro.distro._distro.os_release_file = '/usr/lib/os-release'
except Exception:
    pass

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    APP_NAME: str = "Transmute AI Intelligence Dissemination API"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@localhost:5432/transmute"
    )
    SQLITE_FALLBACK_URL: str = f"sqlite:///{BASE_DIR}/transmute.db"

    # File Storage
    STORAGE_DIR: Path = BASE_DIR / "storage"
    UPLOADS_DIR: Path = BASE_DIR / "storage" / "uploads"
    PREVIEWS_DIR: Path = BASE_DIR / "storage" / "previews"
    KEYS_DIR: Path = BASE_DIR / "storage" / "keys"

    # Deliverable Watermarking & Signing (T9)
    SIGNING_MASTER_KEY: str = os.getenv("SIGNING_MASTER_KEY", "")
    DEFAULT_SIGNING_ORG: str = os.getenv("DEFAULT_SIGNING_ORG", "Transmute Threat Intel CERT")
    DEFAULT_TLP_LEVEL: str = os.getenv("DEFAULT_TLP_LEVEL", "TLP:AMBER+STRICT")
    VERIFY_BASE_URL: str = os.getenv("VERIFY_BASE_URL", "http://localhost:5173/verify")

    # LLM Settings
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

    # Server Network
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", 8000))

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()

# Ensure directories exist
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
settings.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
settings.PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
settings.KEYS_DIR.mkdir(parents=True, exist_ok=True)
