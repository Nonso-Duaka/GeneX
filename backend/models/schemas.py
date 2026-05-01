from typing import Optional
from pydantic import BaseModel, Field


class Gene(BaseModel):
    symbol: str
    name: Optional[str] = None
    hgnc_id: Optional[str] = None
    entrez_id: Optional[int] = None


class Protein(BaseModel):
    uniprot_id: str
    name: Optional[str] = None
    gene_symbol: str
    organism: Optional[str] = None
    reviewed: bool = False


class Structure(BaseModel):
    pdb_id: str
    title: Optional[str] = None
    method: Optional[str] = None
    resolution: Optional[float] = None
    organism: Optional[str] = None


class Drug(BaseModel):
    chembl_id: str
    name: str
    max_phase: int
    phase_label: str
    action_type: Optional[str] = None
    mechanism: Optional[str] = None


class TargetResult(BaseModel):
    gene: Gene
    protein: Optional[Protein] = None
    structures: list[Structure] = Field(default_factory=list)
    best_structure: Optional[Structure] = None
    drugs: list[Drug] = Field(default_factory=list)
    top_drug: Optional[Drug] = None


class SearchResponse(BaseModel):
    cancer_query: str
    matched_disease: Optional[str] = None
    candidate_diseases: list[str] = Field(default_factory=list)
    results: list[TargetResult] = Field(default_factory=list)
