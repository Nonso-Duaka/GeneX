# GeneX

**GeneX** maps a cancer type to its known gene targets and the best available
protein structures, in one query.

```
cancer name
   │ CIViC GraphQL  (https://civicdb.org/api/graphql)
   ▼
disease → genes
   │ HGNC REST      (rest.genenames.org)
   ▼
normalized gene symbols
   │ UniProt REST   (rest.uniprot.org) — reviewed, organism_id 9606
   ▼
human protein accessions
   │ RCSB Search v2 + Data API (search.rcsb.org, data.rcsb.org)
   ▼
PDB structures, ranked by method (X-ray > cryo-EM > NMR) then resolution
```

## Stack

- **Backend:** FastAPI + httpx (async, fan-out per gene)
- **Frontend:** single `index.html`, vanilla JS (served by FastAPI)
- **Cache:** SQLite TTL cache for every outbound HTTP call (1-week default)
- **Tests:** pytest + respx (no real network)

## Run it

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Open <http://127.0.0.1:8000>.

Try queries like:
- `Lung Non-small Cell Carcinoma`
- `Melanoma`
- `Breast Carcinoma`

The first request for a disease takes 30–60s (the pipeline fans out across
4 public APIs). Repeat queries are instant — they hit the SQLite cache
(`cache.db` in the project root). Delete that file to force a refresh.

## API

| Endpoint | Description |
|---|---|
| `GET /api/search?cancer=...&gene_limit=15&structure_limit=5` | Run the pipeline, return JSON |
| `GET /api/export?cancer=...&format=json\|csv` | Same pipeline, downloadable |
| `GET /api/health` | Liveness check |

### Example

```bash
curl 'http://127.0.0.1:8000/api/search?cancer=Lung%20Non-small%20Cell%20Carcinoma&gene_limit=5&structure_limit=3' | jq
```

## Tests

```bash
python -m pytest
```

All HTTP calls are mocked with `respx`, so tests run offline.

## Layout

```
backend/
  main.py                 # FastAPI app, /api/search, /api/export
  cache.py                # SQLite TTL cache
  models/schemas.py       # Pydantic models
  services/
    civic_service.py      # cancer → genes  (CIViC GraphQL)
    gene_service.py       # HGNC normalize + dedupe
    protein_service.py    # gene → reviewed human UniProt entry
    pdb_service.py        # UniProt → PDB structures + ranking
  utils/http.py           # shared async client + cached_get/post helpers
frontend/
  index.html              # input + results table + export buttons
tests/
  test_services.py        # one test per service, fully mocked
```

## Notes on data choices

- **Why CIViC GraphQL, not REST.** The CIViC REST API is deprecated; GraphQL
  is the supported interface.
- **Why HGNC fetch + search fallback.** `fetch/symbol/{X}` only matches
  current canonical symbols. For aliases (e.g. `HER1` → `EGFR`) we fall
  back to `search/{X}` and re-fetch the canonical record.
- **Why `reviewed:true` and `organism_id:9606` in UniProt.** The plan
  requires human, and reviewed (Swiss-Prot) entries are the curated set —
  this avoids picking a TrEMBL or non-human ortholog.
- **Why method-then-resolution ranking.** Plan §6 step 6: prefer X-ray /
  cryo-EM, prefer better resolution. Method bucket dominates resolution
  so a 3.0 Å X-ray ranks above a 2.5 Å NMR.
