"""Document proposal adapters. Confirmation deliberately has no model tool."""

import json

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import TypeAdapter

from arete.services import imports
from arete.services.prescriptions import ImportedSession


@tool
def prepare_import(
    sessions_json: str,
    config: RunnableConfig,
    draft_id: str = "",
    expected_version: int = 0,
) -> str:
    """Prépare 1 à 5 séances documentées pour validation humaine, sans les planifier.

    sessions_json est un tableau JSON : date ISO ou null, sport, session_type,
    description, prescription {version:1, steps:[{kind:'effort',
    duration_kind:'seconds',value:1800}]}, provenance:[{document_id,locator,quote}].
    kind: warmup|effort|recovery|cooldown|rest|repeat. Une répétition utilise
    repeat (2..100), steps et aucune value. duration_kind: seconds|meters|reps|lap.
    target et secondary_target: {kind:pace_sec_km|heart_rate_bpm|power_w|cadence_rpm|hr_zone,low,high}.
    Musculation: strength_text exact, analysé par grammaire ; pas de chiffres inventés.
    Natation: prescription.pool_length_m, stroke free|back|breast|butterfly|mixed.
    uncertainties liste ce qui reste à résoudre. quote doit être un extrait exact
    du locator lu dans le fichier. Pour compléter un brouillon, fournir son id/version.
    """
    thread_id = config.get("configurable", {}).get("thread_id")
    if not thread_id:
        raise ValueError("Un fil de conversation est requis pour importer.")
    if len(sessions_json) > 32_000:
        raise ValueError("Lot trop volumineux ; utilise moins de séances.")
    try:
        sessions = TypeAdapter(list[ImportedSession]).validate_json(sessions_json)
        return json.dumps(
            imports.propose(thread_id, sessions, draft_id, expected_version),
            ensure_ascii=False,
        )
    except ValueError as exc:
        # Expected input errors are actionable tool results, never empty context.
        return json.dumps(
            {
                "error": str(exc),
                "message": "Relis les sources et corrige la proposition ; rien n’a été planifié.",
            },
            ensure_ascii=False,
        )


@tool
def inspect_import(config: RunnableConfig) -> str:
    """Liste les brouillons de ce fil, leur version et leurs problèmes de validation."""
    thread_id = config.get("configurable", {}).get("thread_id")
    if not thread_id:
        raise ValueError("Fil requis.")
    return json.dumps(
        [
            {
                "id": d["id"],
                "version": d["version"],
                "status": d["status"],
                "count": len(d["sessions"]),
                "problems": [i["problems"] for i in d["sessions"]],
            }
            for d in imports.list_drafts(thread_id)
        ],
        ensure_ascii=False,
    )
