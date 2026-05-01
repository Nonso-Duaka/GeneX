from difflib import SequenceMatcher
from typing import Optional

from backend.utils.http import cached_post_json

CIVIC_GRAPHQL = "https://civicdb.org/api/graphql"


SEARCH_DISEASES_QUERY = """
query SearchDiseases($name: String!) {
  diseases(name: $name, first: 25) {
    nodes {
      id
      name
      doid
    }
  }
}
"""


GENES_FOR_DISEASE_QUERY = """
query GenesForDisease($diseaseId: Int!, $after: String) {
  evidenceItems(diseaseId: $diseaseId, first: 100, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      molecularProfile {
        variants {
          feature {
            featureInstance {
              ... on Gene { id name entrezId }
            }
          }
        }
      }
    }
  }
}
"""


async def _gql(query: str, variables: dict, cache_key: str) -> dict:
    payload = {"query": query, "variables": variables}
    data = await cached_post_json(CIVIC_GRAPHQL, payload, cache_key=cache_key)
    if "errors" in data:
        raise RuntimeError(f"CIViC GraphQL error: {data['errors']}")
    return data["data"]


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


async def find_disease(query: str) -> tuple[Optional[dict], list[dict]]:
    """Return (best match, candidate list) for a free-text cancer query.

    Strategy: try the user's exact text first, then a stripped variant
    (drop the word "cancer"), then rank candidates by similarity.
    """
    queries = [query.strip()]
    stripped = query.lower().replace("cancer", "").strip()
    if stripped and stripped != query.strip().lower():
        queries.append(stripped)

    candidates: list[dict] = []
    seen: set[int] = set()
    for q in queries:
        data = await _gql(
            SEARCH_DISEASES_QUERY,
            {"name": q},
            cache_key=f"civic:disease:{q.lower()}",
        )
        for node in data.get("diseases", {}).get("nodes", []) or []:
            if node["id"] in seen:
                continue
            seen.add(node["id"])
            candidates.append(node)

    if not candidates:
        return None, []

    ranked = sorted(
        candidates,
        key=lambda d: _similarity(query, d["name"]),
        reverse=True,
    )
    return ranked[0], ranked


async def genes_for_disease(disease_id: int) -> list[dict]:
    """Walk evidence items for the disease and collect distinct genes."""
    genes: dict[int, dict] = {}
    cursor: Optional[str] = None
    page = 0
    while True:
        page += 1
        data = await _gql(
            GENES_FOR_DISEASE_QUERY,
            {"diseaseId": disease_id, "after": cursor},
            cache_key=f"civic:evidence:{disease_id}:p{page}:{cursor}",
        )
        ei = data.get("evidenceItems", {})
        for node in ei.get("nodes", []) or []:
            mp = node.get("molecularProfile") or {}
            for variant in mp.get("variants", []) or []:
                feature = (variant.get("feature") or {}).get("featureInstance") or {}
                gene_id = feature.get("id")
                name = feature.get("name")
                if gene_id and name and gene_id not in genes:
                    genes[gene_id] = {
                        "civic_id": gene_id,
                        "symbol": name,
                        "entrez_id": feature.get("entrezId"),
                    }
        info = ei.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            break
        cursor = info.get("endCursor")
        if not cursor:
            break
    return list(genes.values())


async def cancer_to_genes(cancer_query: str) -> dict:
    best, candidates = await find_disease(cancer_query)
    if best is None:
        return {
            "matched_disease": None,
            "candidate_diseases": [],
            "genes": [],
        }
    genes = await genes_for_disease(best["id"])
    return {
        "matched_disease": best["name"],
        "candidate_diseases": [c["name"] for c in candidates[:10]],
        "genes": genes,
    }
