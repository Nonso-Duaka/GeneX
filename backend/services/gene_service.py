from typing import Optional

import httpx

from backend.utils.http import cached_get_json

HGNC_FETCH = "https://rest.genenames.org/fetch/symbol/{symbol}"
HGNC_SEARCH = "https://rest.genenames.org/search/{symbol}"
HGNC_HEADERS = {"Accept": "application/json"}


async def _fetch_canonical(symbol: str) -> Optional[dict]:
    url = HGNC_FETCH.format(symbol=symbol.upper())
    try:
        data = await cached_get_json(
            url, headers=HGNC_HEADERS, cache_key=f"hgnc:fetch:{symbol.upper()}"
        )
    except httpx.HTTPStatusError:
        return None
    docs = (data.get("response") or {}).get("docs") or []
    return docs[0] if docs else None


async def _search_alias(symbol: str) -> Optional[dict]:
    url = HGNC_SEARCH.format(symbol=symbol.upper())
    try:
        data = await cached_get_json(
            url, headers=HGNC_HEADERS, cache_key=f"hgnc:search:{symbol.upper()}"
        )
    except httpx.HTTPStatusError:
        return None
    docs = (data.get("response") or {}).get("docs") or []
    if not docs:
        return None
    top = docs[0]
    canonical_symbol = top.get("symbol")
    if not canonical_symbol:
        return None
    return await _fetch_canonical(canonical_symbol)


async def normalize_one(symbol: str) -> Optional[dict]:
    if not symbol:
        return None
    record = await _fetch_canonical(symbol)
    if record is None:
        record = await _search_alias(symbol)
    if record is None:
        return None
    return {
        "symbol": record.get("symbol"),
        "name": record.get("name"),
        "hgnc_id": record.get("hgnc_id"),
        "entrez_id": int(record["entrez_id"]) if record.get("entrez_id") else None,
    }


async def normalize_genes(raw_genes: list[dict]) -> list[dict]:
    """Normalize and deduplicate gene symbols using HGNC."""
    out: dict[str, dict] = {}
    for raw in raw_genes:
        symbol = raw.get("symbol")
        if not symbol:
            continue
        record = await normalize_one(symbol)
        if record is None:
            # fall back to the raw symbol so we don't drop unmatched entries
            record = {
                "symbol": symbol.upper(),
                "name": None,
                "hgnc_id": None,
                "entrez_id": raw.get("entrez_id"),
            }
        out.setdefault(record["symbol"], record)
    return list(out.values())
