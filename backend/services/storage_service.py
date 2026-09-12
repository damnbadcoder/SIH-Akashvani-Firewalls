import os
import uuid
import hashlib
from pathlib import Path
from typing import Tuple
from backend.config import settings

class StorageService:
    @staticmethod
    def calculate_sha256(content: bytes) -> str:
        sha = hashlib.sha256()
        sha.update(content)
        return sha.hexdigest()

    @staticmethod
    def save_upload(session_id: str, filename: str, data: bytes) -> Tuple[str, str, int]:
        session_upload_dir = settings.UPLOADS_DIR / session_id
        session_upload_dir.mkdir(parents=True, exist_ok=True)

        safe_name = Path(filename).name
        dest_path = session_upload_dir / safe_name
        dest_path.write_bytes(data)

        sha = StorageService.calculate_sha256(data)
        file_size = len(data)
        return str(dest_path), sha, file_size

    @staticmethod
    def save_original_preview(session_id: str, output_type: str, content: str) -> str:
        session_preview_dir = settings.PREVIEWS_DIR / session_id
        session_preview_dir.mkdir(parents=True, exist_ok=True)

        # Primary file Preview.md
        primary_file = session_preview_dir / "Preview.md"
        primary_file.write_text(content, encoding="utf-8")

        # Typed file
        typed_file = session_preview_dir / f"Preview_{output_type}_original.md"
        typed_file.write_text(content, encoding="utf-8")

        return str(primary_file)

    @staticmethod
    def save_edited_preview(session_id: str, output_type: str, content: str, version: int = 1) -> str:
        session_preview_dir = settings.PREVIEWS_DIR / session_id
        session_preview_dir.mkdir(parents=True, exist_ok=True)

        # Primary edited file Preview_edited.md
        primary_edited = session_preview_dir / "Preview_edited.md"
        primary_edited.write_text(content, encoding="utf-8")

        # Versioned edited file Preview_{output_type}_v{version}.md
        versioned_file = session_preview_dir / f"Preview_{output_type}_v{version}.md"
        versioned_file.write_text(content, encoding="utf-8")

        return str(primary_edited)

storage_service = StorageService()
