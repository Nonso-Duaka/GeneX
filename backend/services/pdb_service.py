from typing import Optional

from backend.utils.http import cached_get_json, cached_post_json

RCSB_SEARCH = "https://search.rcsb.org/rcsbsearch/v2/query"
RCSB_ENTRY = "https://data.rcsb.org/rest/v1/core/entry/{pdb_id}"

METHOD_PRIORITY = {
    "X-RAY DIFFRACTION": 0,
    "ELECTRON MICROSCOPY": 1,
    "SOLUTION NMR": 2,
    "SOLID-STATE NMR": 3,
    "NEUTRON DIFFRACTION": 4,
}


def _method_rank(method: Optional[str]) -> int:
    if not method:
        return 99
    return METHOD_PRIORITY.get(method.upper(), 50)


async def search_by_uniprot(uniprot_id: str, limit: int = 25) -> list[str]:
    """Return PDB IDs whose polymer entities reference this UniProt accession,
    restricted to human (taxonomy 9606).
    """
    query = {
        "query": {
            "type": "group",
            "logical_operator": "and",
            "nodes": [
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_accession",
                        "operator": "exact_match",
                        "value": uniprot_id,
                    },
                },
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "rcsb_entity_source_organism.taxonomy_lineage.id",
                        "operator": "exact_match",
                        "value": "9606",
                    },
                },
            ],
        },
        "return_type": "entry",
        "request_options": {
            "paginate": {"start": 0, "rows": limit},
            "results_content_type": ["experimental"],
        },
    }
    data = await cached_post_json(
        RCSB_SEARCH, query, cache_key=f"rcsb:search:{uniprot_id}:{limit}"
    )
    results = data.get("result_set") or []
    return [r["identifier"] for r in results]


async def fetch_entry(pdb_id: str) -> Optional[dict]:
    url = RCSB_ENTRY.format(pdb_id=pdb_id.lower())
    try:
        data = await cached_get_json(url, cache_key=f"rcsb:entry:{pdb_id.upper()}")
    except Exception:
        return None
    title = (data.get("struct") or {}).get("title")
    methods = data.get("exptl") or []
    method = methods[0].get("method") if methods else None
    refine = data.get("refine") or []
    resolution = None
    if refine:
        resolution = refine[0].get("ls_d_res_high")
    if resolution is None:
        em = data.get("rcsb_entry_info") or {}
        resolution = em.get("resolution_combined", [None])[0] if em.get("resolution_combined") else None
    return {
        "pdb_id": pdb_id.upper(),
        "title": title,
        "method": method,
        "resolution": resolution,
    }


def rank_structures(entries: list[dict]) -> list[dict]:
    def key(s: dict):
        rank = _method_rank(s.get("method"))
        res = s.get("resolution")
        res_val = res if isinstance(res, (int, float)) else 999.0
        return (rank, res_val)

    return sorted(entries, key=key)


async def structures_for_protein(uniprot_id: str, limit: int = 25) -> list[dict]:
    pdb_ids = await search_by_uniprot(uniprot_id, limit=limit)
    entries: list[dict] = []
    for pid in pdb_ids:
        entry = await fetch_entry(pid)
        if entry:
            entries.append(entry)
    return rank_structures(entries)
