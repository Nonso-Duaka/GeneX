"""ChEMBL drug-target lookup.

Three-step pipeline per protein:
  1. UniProt accession → ChEMBL target ID  (target endpoint, filtered to single proteins)
  2. ChEMBL target ID → mechanism records  (one per known drug-target relationship)
  3. Each mechanism's molecule_chembl_id → molecule details (name, max_phase)

We only keep molecules with a clinical phase (max_phase >= 1) and rank by phase
descending so approved drugs (max_phase = 4) bubble to the top.
"""

import asyncio
from typing import Optional

from backend.utils.http import cached_get_json

CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"


async def find_target(uniprot_id: str) -> Optional[str]:
    url = f"{CHEMBL_BASE}/target.json"
    params = {
        "target_components__accession": uniprot_id,
        "target_type": "SINGLE PROTEIN",
        "limit": 1,
    }
    data = await cached_get_json(
        url, params=params, cache_key=f"chembl:target:{uniprot_id}"
    )
    targets = data.get("targets") or []
    if not targets:
        return None
    return targets[0].get("target_chembl_id")


async def get_mechanisms(target_chembl_id: str) -> list[dict]:
    url = f"{CHEMBL_BASE}/mechanism.json"
    params = {"target_chembl_id": target_chembl_id, "limit": 50}
    data = await cached_get_json(
        url, params=params, cache_key=f"chembl:mech:{target_chembl_id}"
    )
    return data.get("mechanisms") or []


async def get_molecule(chembl_id: str) -> Optional[dict]:
    url = f"{CHEMBL_BASE}/molecule/{chembl_id}.json"
    try:
        return await cached_get_json(url, cache_key=f"chembl:mol:{chembl_id}")
    except Exception:
        return None


def _phase_label(max_phase) -> str:
    try:
        p = int(float(max_phase)) if max_phase is not None else 0
    except (TypeError, ValueError):
        p = 0
    return {4: "Approved", 3: "Phase 3", 2: "Phase 2", 1: "Phase 1"}.get(p, "Preclinical")


async def drugs_for_protein(uniprot_id: str, limit: int = 10) -> list[dict]:
    target_id = await find_target(uniprot_id)
    if not target_id:
        return []
    mechanisms = await get_mechanisms(target_id)
    if not mechanisms:
        return []

    mech_by_mol: dict[str, dict] = {}
    for m in mechanisms:
        mol_id = m.get("parent_molecule_chembl_id") or m.get("molecule_chembl_id")
        if mol_id and mol_id not in mech_by_mol:
            mech_by_mol[mol_id] = m

    molecules = await asyncio.gather(
        *(get_molecule(mid) for mid in mech_by_mol.keys()),
        return_exceptions=True,
    )

    drugs: list[dict] = []
    for mol in molecules:
        if not mol or isinstance(mol, Exception):
            continue
        chembl_id = mol.get("molecule_chembl_id")
        if not chembl_id:
            continue
        mech = mech_by_mol.get(chembl_id, {})
        max_phase_raw = mol.get("max_phase")
        try:
            max_phase = int(float(max_phase_raw)) if max_phase_raw is not None else 0
        except (TypeError, ValueError):
            max_phase = 0
        if max_phase < 1:
            continue
        drugs.append(
            {
                "chembl_id": chembl_id,
                "name": (mol.get("pref_name") or chembl_id).title()
                if mol.get("pref_name")
                else chembl_id,
                "max_phase": max_phase,
                "phase_label": _phase_label(max_phase),
                "action_type": mech.get("action_type"),
                "mechanism": mech.get("mechanism_of_action"),
            }
        )

    drugs.sort(key=lambda d: d["max_phase"], reverse=True)
    return drugs[:limit]
