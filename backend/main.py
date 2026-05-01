import asyncio
import csv
import io
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.models.schemas import (
    Drug,
    Gene,
    Protein,
    SearchResponse,
    Structure,
    TargetResult,
)
from backend.services import (
    civic_service,
    drug_service,
    gene_service,
    pdb_service,
    protein_service,
)
from backend.utils.http import close_client

FRONTEND_DIR = Path(__file__).parent.parent / "public"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_client()


app = FastAPI(title="GeneX", lifespan=lifespan)


async def _resolve_target(
    gene_record: dict, structure_limit: int, drug_limit: int
) -> TargetResult:
    gene = Gene(**gene_record)
    protein_data = await protein_service.gene_to_protein(gene.symbol)
    if not protein_data:
        return TargetResult(gene=gene)
    protein = Protein(**protein_data)

    structures_raw, drugs_raw = await asyncio.gather(
        pdb_service.structures_for_protein(protein.uniprot_id, limit=structure_limit),
        drug_service.drugs_for_protein(protein.uniprot_id, limit=drug_limit),
    )
    structures = [Structure(**s) for s in structures_raw]
    drugs = [Drug(**d) for d in drugs_raw]
    return TargetResult(
        gene=gene,
        protein=protein,
        structures=structures,
        best_structure=structures[0] if structures else None,
        drugs=drugs,
        top_drug=drugs[0] if drugs else None,
    )


async def run_pipeline(
    cancer: str,
    gene_limit: int,
    structure_limit: int,
    drug_limit: int,
) -> SearchResponse:
    civic_result = await civic_service.cancer_to_genes(cancer)
    if not civic_result["matched_disease"]:
        return SearchResponse(
            cancer_query=cancer,
            matched_disease=None,
            candidate_diseases=[],
            results=[],
        )

    raw_genes = civic_result["genes"][:gene_limit] if gene_limit > 0 else civic_result["genes"]
    normalized = await gene_service.normalize_genes(raw_genes)

    targets = await asyncio.gather(
        *(_resolve_target(g, structure_limit, drug_limit) for g in normalized)
    )

    return SearchResponse(
        cancer_query=cancer,
        matched_disease=civic_result["matched_disease"],
        candidate_diseases=civic_result["candidate_diseases"],
        results=list(targets),
    )


@app.get("/api/search", response_model=SearchResponse)
async def search(
    cancer: str = Query(..., min_length=2, description="Cancer type"),
    gene_limit: int = Query(20, ge=0, le=200),
    structure_limit: int = Query(10, ge=1, le=50),
    drug_limit: int = Query(10, ge=0, le=50),
):
    try:
        return await run_pipeline(cancer, gene_limit, structure_limit, drug_limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Pipeline error: {exc}")


@app.get("/api/export")
async def export(
    cancer: str = Query(..., min_length=2),
    format: str = Query("json", pattern="^(json|csv)$"),
    gene_limit: int = Query(20, ge=0, le=200),
    structure_limit: int = Query(10, ge=1, le=50),
    drug_limit: int = Query(10, ge=0, le=50),
):
    response = await run_pipeline(cancer, gene_limit, structure_limit, drug_limit)
    if format == "json":
        return response

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "cancer_query",
            "matched_disease",
            "gene_symbol",
            "gene_name",
            "hgnc_id",
            "uniprot_id",
            "protein_name",
            "best_pdb_id",
            "best_method",
            "best_resolution",
            "top_drug",
            "top_drug_phase",
            "top_drug_action",
            "drug_count",
        ]
    )
    for target in response.results:
        best = target.best_structure
        top = target.top_drug
        writer.writerow(
            [
                response.cancer_query,
                response.matched_disease or "",
                target.gene.symbol,
                target.gene.name or "",
                target.gene.hgnc_id or "",
                target.protein.uniprot_id if target.protein else "",
                target.protein.name if target.protein else "",
                best.pdb_id if best else "",
                best.method if best else "",
                best.resolution if best and best.resolution is not None else "",
                top.name if top else "",
                top.phase_label if top else "",
                top.action_type if top else "",
                len(target.drugs),
            ]
        )
    buffer.seek(0)
    filename = f"targets_{response.matched_disease or response.cancer_query}.csv".replace(" ", "_")
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}


if FRONTEND_DIR.exists():
    @app.get("/")
    async def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
