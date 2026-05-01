import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

DEFAULT_DB = Path(__file__).parent.parent / "cache.db"
DEFAULT_TTL = 60 * 60 * 24 * 7  # one week


class Cache:
    def __init__(self, path: Path = DEFAULT_DB, ttl: int = DEFAULT_TTL):
        self.path = path
        self.ttl = ttl
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )

    def get(self, key: str) -> Optional[Any]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value, created_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
        if not row:
            return None
        if time.time() - row["created_at"] > self.ttl:
            return None
        return json.loads(row["value"])

    def set(self, key: str, value: Any) -> None:
        payload = json.dumps(value)
        now = int(time.time())
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, created_at) VALUES (?, ?, ?)",
                (key, payload, now),
            )


cache = Cache()
