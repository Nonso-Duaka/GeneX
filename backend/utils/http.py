import asyncio
from typing import Any, Optional

import httpx

from backend.cache import cache

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
DEFAULT_HEADERS = {
    "User-Agent": "cancer-target-mapper/0.1 (research tool)",
    "Accept": "application/json",
}

_client: Optional[httpx.AsyncClient] = None
_lock = asyncio.Lock()


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        async with _lock:
            if _client is None:
                _client = httpx.AsyncClient(
                    timeout=DEFAULT_TIMEOUT,
                    headers=DEFAULT_HEADERS,
                    follow_redirects=True,
                )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def cached_get_json(
    url: str,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    cache_key: Optional[str] = None,
) -> Any:
    key = cache_key or f"GET {url} {params}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    client = await get_client()
    resp = await client.get(url, params=params, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    cache.set(key, data)
    return data


async def cached_post_json(
    url: str,
    json_body: dict,
    headers: Optional[dict] = None,
    cache_key: Optional[str] = None,
) -> Any:
    key = cache_key or f"POST {url} {json_body}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    client = await get_client()
    resp = await client.post(url, json=json_body, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    cache.set(key, data)
    return data
