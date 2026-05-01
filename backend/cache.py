"""In-memory TTL cache.

Used in two contexts:
  * Local dev: persists for the life of the uvicorn process.
  * Vercel: persists for the life of a warm function instance, resets on cold start.

Persistent caching can be added later by swapping this module with one
backed by Upstash Redis or Vercel KV.
"""

import time
from typing import Any, Optional

DEFAULT_TTL = 60 * 60 * 24 * 7  # one week


class Cache:
    def __init__(self, ttl: int = DEFAULT_TTL):
        self.ttl = ttl
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if not entry:
            return None
        created_at, value = entry
        if time.time() - created_at > self.ttl:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.time(), value)


cache = Cache()
