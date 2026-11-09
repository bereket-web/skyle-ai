from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    api_key: str | None = None
    max_document_bytes: int = 15 * 1024 * 1024
    max_csv_bytes: int = 10 * 1024 * 1024
    max_image_bytes: int = 10 * 1024 * 1024
    max_csv_rows: int = 100_000
    llm_enabled: bool = False
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = 25.0

    @property
    def database_path(self) -> Path:
        return self.data_dir / "skyle.sqlite3"

    @property
    def llm_ready(self) -> bool:
        return bool(self.llm_enabled and self.llm_base_url and self.llm_model)

    @classmethod
    def from_env(cls) -> Settings:
        data_dir = Path(os.environ.get("SKYLE_DATA_DIR", ".skyle-data")).expanduser()
        enabled = os.environ.get("SKYLE_LLM_ENABLED", "false").strip().lower() in {"1", "true", "yes"}
        return cls(
            data_dir=data_dir,
            api_key=os.environ.get("SKYLE_API_KEY") or None,
            max_document_bytes=int(os.environ.get("SKYLE_MAX_DOCUMENT_BYTES", 15 * 1024 * 1024)),
            max_csv_bytes=int(os.environ.get("SKYLE_MAX_CSV_BYTES", 10 * 1024 * 1024)),
            max_image_bytes=int(os.environ.get("SKYLE_MAX_IMAGE_BYTES", 10 * 1024 * 1024)),
            max_csv_rows=int(os.environ.get("SKYLE_MAX_CSV_ROWS", 100_000)),
            llm_enabled=enabled,
            llm_base_url=os.environ.get("SKYLE_LLM_BASE_URL") or None,
            llm_api_key=os.environ.get("SKYLE_LLM_API_KEY") or None,
            llm_model=os.environ.get("SKYLE_LLM_MODEL") or None,
            llm_timeout_seconds=float(os.environ.get("SKYLE_LLM_TIMEOUT_SECONDS", "25")),
        )
