from __future__ import annotations

import base64
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

APP_NAME = "ComfyUIWorkbench"

@dataclass
class Settings:
    server_address: str
    workflow_path: str
    gallery_dir: str
    checkpoint: str = ""

    @classmethod
    def defaults(cls, project_root: Path) -> "Settings":
        return cls("127.0.0.1:8188", str(project_root / "workflow_api.json"), str(project_root / "outputs"))

class SettingsStore:
    def __init__(self, project_root: Path, app_dir: Path | None = None):
        self.app_dir = app_dir or Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
        self.path = self.app_dir / "settings.json"
        self.project_root = project_root

    def load(self) -> Settings:
        defaults = Settings.defaults(self.project_root)
        if not self.path.exists(): return defaults
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
            return Settings(**{name: values.get(name, getattr(defaults, name)) for name in asdict(defaults)})
        except (json.JSONDecodeError, OSError, TypeError): return defaults

    def save(self, settings: Settings) -> None:
        self.app_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.path, json.dumps(asdict(settings), ensure_ascii=False, indent=2).encode("utf-8"))

class KeyProtectionError(RuntimeError): pass

class DPAPIKeyStore:
    """Stores a Fernet key protected for the current Windows user."""
    def __init__(self, app_dir: Path): self.path = app_dir / "gallery-key.dpapi"
    def get_or_create(self) -> bytes:
        try: import win32crypt
        except ImportError as exc: raise KeyProtectionError("缺少 pywin32，无法使用 Windows 凭据保护图库密钥。") from exc
        try:
            if self.path.exists():
                return win32crypt.CryptUnprotectData(base64.b64decode(self.path.read_bytes()), None, None, None, 0)[1]
            from cryptography.fernet import Fernet
            key = Fernet.generate_key()
            protected = win32crypt.CryptProtectData(key, APP_NAME, None, None, None, 0)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(self.path, base64.b64encode(protected))
            return key
        except Exception as exc: raise KeyProtectionError("无法读取或创建受 Windows 保护的图库密钥。") from exc

def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
