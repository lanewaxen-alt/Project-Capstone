from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4


class UserStore:
    def __init__(self, file_path: Path | None = None):
        self.file_path = file_path or Path(__file__).resolve().parents[2] / "data" / "users.json"
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self.file_path.write_text("[]", encoding="utf-8")

    # ── helpers ────────────────────────────────────────────────────────────

    def _read(self) -> list[dict]:
        try:
            return json.loads(self.file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def _write(self, users: list[dict]) -> None:
        self.file_path.write_text(json.dumps(users, indent=2), encoding="utf-8")

    @staticmethod
    def _hash(password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    # ── public API ─────────────────────────────────────────────────────────

    def username_exists(self, username: str) -> bool:
        return any(u["username"] == username for u in self._read())

    def register(self, username: str, password: str) -> dict:
        """Create a new user and return a session token."""
        users = self._read()
        token = str(uuid4())
        users.append({
            "username": username,
            "password_hash": self._hash(password),
            "token": token,
        })
        self._write(users)
        return {"username": username, "token": token}

    def login(self, username: str, password: str) -> dict | None:
        """Verify credentials and return a fresh session token, or None."""
        users = self._read()
        password_hash = self._hash(password)
        for user in users:
            if user["username"] == username and user["password_hash"] == password_hash:
                # rotate token on every login
                user["token"] = str(uuid4())
                self._write(users)
                return {"username": username, "token": user["token"]}
        return None