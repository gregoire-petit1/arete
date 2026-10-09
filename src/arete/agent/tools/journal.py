"""The coach's one write on its journal: a dated entry, filed by the server."""

from __future__ import annotations

import json
from datetime import date
from typing import Literal

from langchain_core.tools import tool

from arete.services import athlete_facts
from arete.services.memory import append_entry

MAX_TITLE_CHARS = 120
MAX_BODY_CHARS = 2_000


@tool
def append_journal(
    file: Literal["sessions.md", "notes.md"], title: str, body: str, day: str = ""
) -> str:
    """Ajoute une entrée datée à ton journal. `sessions.md`: une séance dont
    vous avez parlé (faits marquants, ressenti, décision). `notes.md`: une
    observation de coach qui n'est pas un fait sur l'athlète. Le serveur écrit
    l'entête daté et ignore une entrée déjà présente. `day`: date ISO de la
    séance si ce n'est pas aujourd'hui, sinon vide."""
    if not title.strip() or not body.strip():
        return json.dumps({"error": "title et body sont obligatoires."})
    if len(title) > MAX_TITLE_CHARS or len(body) > MAX_BODY_CHARS:
        return json.dumps(
            {
                "error": f"Entrée trop longue (titre ≤ {MAX_TITLE_CHARS}, "
                f"corps ≤ {MAX_BODY_CHARS} caractères)."
            }
        )
    try:
        when = date.fromisoformat(day) if day else None
    except ValueError:
        return json.dumps({"error": f"day doit être une date ISO, reçu « {day} »."})
    written = append_entry(file, title, body, when=when)
    return json.dumps(
        {"written": written, "file": file}
        if written
        else {"written": False, "reason": "Cette entrée existe déjà."},
        ensure_ascii=False,
    )


@tool
def remember_fact(
    kind: Literal["injury", "constraint", "preference", "goal", "other"],
    text: str,
    fact_id: int = 0,
    status: Literal["active", "resolved"] = "active",
) -> str:
    """Enregistre un fait durable sur l'athlète (blessure, contrainte,
    préférence, objectif), ou corrige celui dont tu donnes `fact_id` (son
    numéro #N dans la liste jointe). `status="resolved"` quand le fait ne tient
    plus (blessure guérie, contrainte levée). Un fait par appel, une phrase."""
    try:
        if fact_id:
            fact = athlete_facts.update_fact(
                fact_id, kind=kind, text=text, status=status
            )
            if fact is None:
                return json.dumps({"error": f"Fait #{fact_id} introuvable."})
        else:
            if status != "active":
                return json.dumps(
                    {"error": "Un nouveau fait est actif ; pour clore, donne fact_id."}
                )
            fact = athlete_facts.add_fact(kind, text)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"saved": True, "fact": fact.to_dict()}, ensure_ascii=False)
