from __future__ import annotations

import base64
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .config import _atomic_write


class GalleryError(RuntimeError): pass

@dataclass(frozen=True)
class GalleryItem:
    id: str
    created_at: float
    file_name: str
    metadata: dict[str, Any]


class EncryptedGallery:
    """Image bytes and the complete index remain Fernet encrypted at rest."""
    def __init__(self, directory: str | Path, key: bytes):
        self.directory = Path(directory)
        self.index_path = self.directory / "index.enc"
        self.cipher = Fernet(key)
        self._lock = threading.RLock()
        self.directory.mkdir(parents=True, exist_ok=True)

    def list_items(self) -> list[GalleryItem]:
        with self._lock:
            return sorted(self._read_index(), key=lambda item: item.created_at, reverse=True)

    def save_image(self, data: bytes, metadata: dict[str, Any]) -> GalleryItem:
        with self._lock:
            item = GalleryItem(uuid.uuid4().hex, time.time(), f"{uuid.uuid4().hex}.enc", metadata)
            _atomic_write(self.directory / item.file_name, self.cipher.encrypt(data))
            items = self._read_index(); items.append(item); self._write_index(items)
            return item

    def image_bytes(self, item_id: str) -> bytes:
        item = self.get(item_id)
        try: return self.cipher.decrypt((self.directory / item.file_name).read_bytes())
        except (OSError, InvalidToken) as exc: raise GalleryError("图片无法解密，文件或当前 Windows 凭据可能不匹配。") from exc

    def get(self, item_id: str) -> GalleryItem:
        for item in self.list_items():
            if item.id == item_id: return item
        raise GalleryError("找不到该图库作品。")

    def export(self, item_id: str, destination: str | Path) -> None:
        Path(destination).write_bytes(self.image_bytes(item_id))

    def _read_index(self) -> list[GalleryItem]:
        if not self.index_path.exists(): return []
        try:
            payload = self.cipher.decrypt(self.index_path.read_bytes())
            return [GalleryItem(**value) for value in json.loads(payload)]
        except (OSError, InvalidToken, json.JSONDecodeError, TypeError) as exc:
            raise GalleryError("图库索引无法解密，已停止写入以保护现有作品。") from exc

    def _write_index(self, items: list[GalleryItem]) -> None:
        payload = json.dumps([asdict(item) for item in items], ensure_ascii=False).encode("utf-8")
        _atomic_write(self.index_path, self.cipher.encrypt(payload))
