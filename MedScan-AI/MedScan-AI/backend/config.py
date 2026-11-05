"""Application settings, read from environment variables (see .env.example)."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    # No default password on purpose: the URL must come from the environment.
    database_url: str = "sqlite:///./storage/medscan_dev.db"
    storage_dir: Path = ROOT_DIR / "storage"
    max_upload_mb: int = 15
    max_image_side_px: int = 8000
    min_image_side_px: int = 128
    allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000"
    # Where torchxrayvision caches downloaded weights
    model_cache_dir: Path = ROOT_DIR / "storage" / "model_cache"

    @property
    def upload_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def output_dir(self) -> Path:
        return self.storage_dir / "outputs"

    @property
    def report_dir(self) -> Path:
        return self.storage_dir / "reports"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def ensure_dirs(self) -> None:
        for d in (self.upload_dir, self.output_dir, self.report_dir, self.model_cache_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
