from typing import Optional

from backend.utils.http import cached_get_json

UNIPROT_SEARCH = "https://rest.uniprot.org/uniprotkb/search"


async def gene_to_protein(symbol: str) -> Optional[dict]:
    """Resolve a gene symbol to its reviewed human UniProt entry."""
    if not symbol:
        return None
    params = {
        "query": f"gene_exact:{symbol} AND organism_id:9606 AND reviewed:true",
        "fields": "accession,id,protein_name,gene_names,organism_name,reviewed",
        "format": "json",
        "size": 5,
    }
    data = await cached_get_json(
        UNIPROT_SEARCH,
        params=params,
        cache_key=f"uniprot:gene:{symbol.upper()}",
    )
    results = data.get("results") or []
    if not results:
        return None

    entry = results[0]
    protein_name = (
        ((entry.get("proteinDescription") or {}).get("recommendedName") or {})
        .get("fullName", {})
        .get("value")
    )
    organism = (entry.get("organism") or {}).get("scientificName")
    return {
        "uniprot_id": entry.get("primaryAccession"),
        "name": protein_name,
        "gene_symbol": symbol.upper(),
        "organism": organism,
        "reviewed": (entry.get("entryType", "")).lower().startswith("uniprotkb reviewed"),
    }
