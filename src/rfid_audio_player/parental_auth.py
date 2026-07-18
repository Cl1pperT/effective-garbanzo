"""Password verification for protected web settings."""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import tempfile

from werkzeug.security import check_password_hash, generate_password_hash


class ParentalAuth:
    """Store only a password hash and a random Flask session-signing secret."""

    def __init__(self, path: str | os.PathLike | None = None):
        project_root = Path(__file__).resolve().parents[2]
        self.path = Path(path) if path else project_root / "parental_auth.json"
        self.password_hash = ""
        self.session_secret = secrets.token_hex(32)
        self._load()

    @property
    def configured(self) -> bool:
        return bool(self.password_hash)

    def _load(self) -> None:
        try:
            with self.path.open("r", encoding="utf-8") as auth_file:
                saved = json.load(auth_file)
        except (FileNotFoundError, OSError, ValueError):
            return
        if not isinstance(saved, dict):
            return
        password_hash = saved.get("password_hash")
        session_secret = saved.get("session_secret")
        if isinstance(password_hash, str):
            self.password_hash = password_hash
        if isinstance(session_secret, str) and len(session_secret) >= 32:
            self.session_secret = session_secret

    def verify(self, password: object) -> bool:
        if not self.configured or not isinstance(password, str):
            return False
        try:
            return check_password_hash(self.password_hash, password)
        except (ValueError, TypeError):
            return False

    def set_password(self, password: str) -> None:
        if not isinstance(password, str) or len(password) < 8:
            raise ValueError("Parental password must be at least 8 characters.")
        if len(password) > 128:
            raise ValueError("Parental password must be 128 characters or fewer.")

        # Rotating the signing secret invalidates every previously authenticated
        # browser when the password changes.
        self.session_secret = secrets.token_hex(32)
        saved = {
            "password_hash": generate_password_hash(password),
            "session_secret": self.session_secret,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_path = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=self.path.parent
        )
        try:
            os.fchmod(file_descriptor, 0o600)
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as auth_file:
                file_descriptor = -1
                json.dump(saved, auth_file, indent=2)
                auth_file.write("\n")
            os.replace(temporary_path, self.path)
        finally:
            if file_descriptor >= 0:
                os.close(file_descriptor)
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
        self.password_hash = saved["password_hash"]
