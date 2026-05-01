import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Use a throwaway SQLite cache for every test."""
    from backend import cache as cache_module

    fresh = cache_module.Cache(path=tmp_path / "test_cache.db", ttl=60)
    monkeypatch.setattr(cache_module, "cache", fresh)

    from backend.utils import http as http_module
    monkeypatch.setattr(http_module, "cache", fresh)

    yield fresh
