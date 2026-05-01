import httpx
import pytest
import respx

from backend.services import (
    civic_service,
    drug_service,
    gene_service,
    pdb_service,
    protein_service,
)


@pytest.mark.asyncio
@respx.mock
async def test_civic_cancer_to_genes_matches_and_pages():
    disease_payload = {
        "data": {
            "diseases": {
                "nodes": [
                    {"id": 11, "name": "Lung Non-small Cell Carcinoma", "doid": "DOID:3908"},
                    {"id": 12, "name": "Lung Adenocarcinoma", "doid": "DOID:3910"},
                ]
            }
        }
    }
    evidence_page1 = {
        "data": {
            "evidenceItems": {
                "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
                "nodes": [
                    {
                        "molecularProfile": {
                            "variants": [
                                {"feature": {"featureInstance": {"id": 1, "name": "EGFR", "entrezId": 1956}}}
                            ]
                        }
                    }
                ],
            }
        }
    }
    evidence_page2 = {
        "data": {
            "evidenceItems": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [
                    {
                        "molecularProfile": {
                            "variants": [
                                {"feature": {"featureInstance": {"id": 2, "name": "KRAS", "entrezId": 3845}}},
                                {"feature": {"featureInstance": {"id": 1, "name": "EGFR", "entrezId": 1956}}},
                            ]
                        }
                    }
                ],
            }
        }
    }

    call_count = {"n": 0}

    def graphql_side_effect(request):
        call_count["n"] += 1
        body = request.content.decode()
        if "diseases" in body and "name" in body:
            return httpx.Response(200, json=disease_payload)
        if "after" in body and "cursor1" in body:
            return httpx.Response(200, json=evidence_page2)
        return httpx.Response(200, json=evidence_page1)

    respx.post("https://civicdb.org/api/graphql").mock(side_effect=graphql_side_effect)

    result = await civic_service.cancer_to_genes("lung cancer")
    assert result["matched_disease"] in {
        "Lung Non-small Cell Carcinoma",
        "Lung Adenocarcinoma",
    }
    symbols = {g["symbol"] for g in result["genes"]}
    assert symbols == {"EGFR", "KRAS"}


@pytest.mark.asyncio
@respx.mock
async def test_gene_normalize_canonical_and_alias():
    respx.get("https://rest.genenames.org/fetch/symbol/EGFR").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": {
                    "docs": [
                        {
                            "symbol": "EGFR",
                            "name": "epidermal growth factor receptor",
                            "hgnc_id": "HGNC:3236",
                            "entrez_id": "1956",
                        }
                    ]
                }
            },
        )
    )
    respx.get("https://rest.genenames.org/fetch/symbol/HER1").mock(
        return_value=httpx.Response(200, json={"response": {"docs": []}})
    )
    respx.get("https://rest.genenames.org/search/HER1").mock(
        return_value=httpx.Response(
            200, json={"response": {"docs": [{"symbol": "EGFR"}]}}
        )
    )

    out = await gene_service.normalize_genes(
        [{"symbol": "EGFR"}, {"symbol": "HER1"}, {"symbol": "EGFR"}]
    )
    assert len(out) == 1
    assert out[0]["symbol"] == "EGFR"
    assert out[0]["hgnc_id"] == "HGNC:3236"


@pytest.mark.asyncio
@respx.mock
async def test_protein_service_returns_reviewed_human_entry():
    respx.get("https://rest.uniprot.org/uniprotkb/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "primaryAccession": "P00533",
                        "entryType": "UniProtKB reviewed (Swiss-Prot)",
                        "proteinDescription": {
                            "recommendedName": {"fullName": {"value": "Epidermal growth factor receptor"}}
                        },
                        "organism": {"scientificName": "Homo sapiens"},
                    }
                ]
            },
        )
    )
    out = await protein_service.gene_to_protein("EGFR")
    assert out["uniprot_id"] == "P00533"
    assert out["organism"] == "Homo sapiens"
    assert out["reviewed"] is True


@pytest.mark.asyncio
@respx.mock
async def test_pdb_service_ranks_xray_above_em_and_by_resolution():
    respx.post("https://search.rcsb.org/rcsbsearch/v2/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "result_set": [
                    {"identifier": "1M14"},
                    {"identifier": "5UG9"},
                    {"identifier": "7SI5"},
                ]
            },
        )
    )
    entries = {
        "1m14": {
            "struct": {"title": "EGFR kinase"},
            "exptl": [{"method": "X-RAY DIFFRACTION"}],
            "refine": [{"ls_d_res_high": 2.6}],
        },
        "5ug9": {
            "struct": {"title": "EGFR cryo"},
            "exptl": [{"method": "ELECTRON MICROSCOPY"}],
            "rcsb_entry_info": {"resolution_combined": [3.4]},
        },
        "7si5": {
            "struct": {"title": "EGFR high-res"},
            "exptl": [{"method": "X-RAY DIFFRACTION"}],
            "refine": [{"ls_d_res_high": 1.85}],
        },
    }

    def entry_side_effect(request):
        pdb_id = request.url.path.rstrip("/").split("/")[-1]
        return httpx.Response(200, json=entries[pdb_id])

    respx.get(url__regex=r"https://data\.rcsb\.org/rest/v1/core/entry/.*").mock(
        side_effect=entry_side_effect
    )

    ranked = await pdb_service.structures_for_protein("P00533")
    assert [s["pdb_id"] for s in ranked] == ["7SI5", "1M14", "5UG9"]


@pytest.mark.asyncio
@respx.mock
async def test_drug_service_ranks_approved_above_clinical_and_drops_preclinical():
    respx.get("https://www.ebi.ac.uk/chembl/api/data/target.json").mock(
        return_value=httpx.Response(
            200, json={"targets": [{"target_chembl_id": "CHEMBL1824"}]}
        )
    )
    respx.get("https://www.ebi.ac.uk/chembl/api/data/mechanism.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "mechanisms": [
                    {
                        "molecule_chembl_id": "CHEMBL1336",
                        "parent_molecule_chembl_id": "CHEMBL1336",
                        "action_type": "INHIBITOR",
                        "mechanism_of_action": "BRAF inhibitor",
                    },
                    {
                        "molecule_chembl_id": "CHEMBL2103743",
                        "parent_molecule_chembl_id": "CHEMBL2103743",
                        "action_type": "INHIBITOR",
                        "mechanism_of_action": "BRAF V600 inhibitor",
                    },
                    {
                        "molecule_chembl_id": "CHEMBL999999",
                        "parent_molecule_chembl_id": "CHEMBL999999",
                        "action_type": "INHIBITOR",
                        "mechanism_of_action": "preclinical compound",
                    },
                ]
            },
        )
    )
    molecules = {
        "CHEMBL1336": {"molecule_chembl_id": "CHEMBL1336", "pref_name": "VEMURAFENIB", "max_phase": 4},
        "CHEMBL2103743": {"molecule_chembl_id": "CHEMBL2103743", "pref_name": "DABRAFENIB", "max_phase": 3},
        "CHEMBL999999": {"molecule_chembl_id": "CHEMBL999999", "pref_name": "EXAMPLE", "max_phase": 0},
    }

    def molecule_side_effect(request):
        chembl_id = request.url.path.rstrip("/").split("/")[-1].replace(".json", "")
        return httpx.Response(200, json=molecules[chembl_id])

    respx.get(
        url__regex=r"https://www\.ebi\.ac\.uk/chembl/api/data/molecule/.*"
    ).mock(side_effect=molecule_side_effect)

    drugs = await drug_service.drugs_for_protein("P15056")
    assert [d["chembl_id"] for d in drugs] == ["CHEMBL1336", "CHEMBL2103743"]
    assert drugs[0]["phase_label"] == "Approved"
    assert drugs[1]["phase_label"] == "Phase 3"
