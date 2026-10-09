"""Document proposals are persisted, but only a human HTTP action commits them."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from arete.dataio.db import db_connection
from arete.services.documents import DocumentError, extraction_for, list_documents
from arete.services.documents import document_transaction as transaction
from arete.services.prescriptions import (
    ImportedSession,
    strength_prescription,
    strength_sets,
)

MAX_DRAFT_SESSIONS = 50
MAX_DRAFTS_PER_THREAD = 50
MAX_BATCH_SESSIONS = 5


def _sources_still_present(con, thread_id: str, items: list[dict]) -> None:
    """Deletion can race parsing; recheck after acquiring the lifecycle lock."""
    identifiers = {
        p["document_id"] for item in items for p in item["session"]["provenance"]
    }
    ready = {
        r[0]
        for r in con.execute(
            "SELECT id FROM app.coach_documents WHERE thread_id=? AND status='ready' LIMIT 20",
            [thread_id],
        ).fetchall()
    }
    if not identifiers <= ready:
        raise DocumentError(
            "Un document source a été supprimé ou n’est plus disponible."
        )


def _get(con, thread_id: str, draft_id: str) -> dict:
    row = con.execute(
        "SELECT id, version, status, sessions, confirmation_key, selected, session_ids FROM app.coach_imports WHERE id=? AND thread_id=?",
        [str(UUID(draft_id)), str(UUID(thread_id))],
    ).fetchone()
    if not row:
        raise DocumentError("Brouillon introuvable dans ce fil.")
    items = json.loads(row[3])
    for index, item in enumerate(items):
        session = item["session"]
        item["batch_duplicates"] = [
            i + 1
            for i, other in enumerate(items)
            if i != index
            and session["date"]
            and (other["session"]["date"], other["session"]["sport"])
            == (session["date"], session["sport"])
        ]
    return {
        "id": row[0],
        "version": row[1],
        "status": row[2],
        "sessions": items,
        "confirmation_key": row[4],
        "selected": json.loads(row[5]) if row[5] else None,
        "session_ids": json.loads(row[6]) if row[6] else [],
    }


def list_drafts(thread_id: str) -> list[dict]:
    with db_connection() as con:
        ids = con.execute(
            "SELECT id FROM app.coach_imports WHERE thread_id=? ORDER BY created_at DESC LIMIT ?",
            [str(UUID(thread_id)), MAX_DRAFTS_PER_THREAD],
        ).fetchall()
        return [_get(con, thread_id, row[0]) for row in ids]


def _validated(thread_id: str, session: ImportedSession) -> dict:
    problems = list(session.uncertainties)
    source_details = []
    names = {d["id"]: d["name"] for d in list_documents(thread_id)}
    ocr = False
    if session.date is None:
        problems.append("Date manquante ou ambiguë.")
    for source in session.provenance:
        extraction = extraction_for(thread_id, str(source.document_id))
        matches = [
            b
            for b in extraction.blocks
            if b.locator == source.locator and source.quote in b.text
        ]
        if not matches:
            raise DocumentError(
                f"La source {source.locator} ne contient pas l’extrait cité."
            )
        ocr |= any(b.method == "ocr" for b in matches)
        source_details.append(
            {
                **source.model_dump(mode="json"),
                "file_name": names.get(
                    str(source.document_id), str(source.document_id)
                ),
                "ocr": any(b.method == "ocr" for b in matches),
            }
        )
    if session.sport == "strength":
        if not session.strength_text:
            problems.append(
                "Le texte de musculation est requis pour le parsing par grammaire."
            )
        else:
            try:
                parsed = strength_prescription(session.strength_text, session.date)
                # Never silently replace steps: the preview must show any discrepancy.
                if strength_sets(session.prescription) != strength_sets(parsed):
                    problems.append(
                        "Les séries ne correspondent pas au texte reconnu par la grammaire. Relis le texte de musculation avant confirmation."
                    )
            except ValueError as exc:
                problems.append(str(exc))
    if session.sport == "swimming" and not session.prescription.pool_length_m:
        problems.append("Longueur du bassin manquante.")
    with db_connection() as con:
        duplicates = (
            con.execute(
                "SELECT id,description FROM app.planned_sessions WHERE date=? AND sport=? ORDER BY id LIMIT 51",
                [session.date, session.sport],
            ).fetchall()
            if session.date
            else []
        )
    if len(duplicates) > 50:
        raise DocumentError(
            "Trop de séances existantes ce jour-là pour vérifier les doublons."
        )
    return {
        "session": session.model_dump(mode="json"),
        "problems": problems,
        "ocr": ocr,
        "sources": source_details,
        "duplicates": [{"id": d[0], "description": d[1]} for d in duplicates],
    }


def propose(
    thread_id: str,
    sessions: list[ImportedSession],
    draft_id: str = "",
    expected_version: int = 0,
) -> dict:
    if not 1 <= len(sessions) <= MAX_BATCH_SESSIONS:
        raise DocumentError("Ajoute entre 1 et 5 séances par appel.")
    items = [_validated(thread_id, s) for s in sessions]
    with transaction() as con:
        _sources_still_present(con, thread_id, items)
        if draft_id:
            old = _get(con, thread_id, draft_id)
            if old["status"] != "draft" or old["version"] != expected_version:
                raise DocumentError("Le brouillon a changé. Recharge-le.")
            items = old["sessions"] + items
            if len(items) > MAX_DRAFT_SESSIONS:
                raise DocumentError(
                    "Maximum 50 séances par brouillon ; crée un autre lot explicitement."
                )
            con.execute(
                "UPDATE app.coach_imports SET sessions=?,version=version+1 WHERE id=?",
                [json.dumps(items, ensure_ascii=False), draft_id],
            )
        else:
            count_row = con.execute(
                "SELECT count(*) FROM app.coach_imports WHERE thread_id=?", [thread_id]
            ).fetchone()
            assert count_row is not None
            if count_row[0] >= MAX_DRAFTS_PER_THREAD:
                raise DocumentError("Maximum 50 imports par fil.")
            draft_id = str(uuid4())
            con.execute(
                "INSERT INTO app.coach_imports (id,thread_id,version,status,sessions) VALUES (?,?,1,'draft',?)",
                [draft_id, str(UUID(thread_id)), json.dumps(items, ensure_ascii=False)],
            )
        result = _get(con, thread_id, draft_id)
    return {
        "draft_id": result["id"],
        "version": result["version"],
        "count": len(items),
        "problems": [item["problems"] for item in items],
        "message": "Aperçu prêt. L’athlète doit le valider dans l’interface.",
    }


def update_draft(
    thread_id: str, draft_id: str, version: int, sessions: list[ImportedSession]
) -> dict:
    if not 1 <= len(sessions) <= MAX_DRAFT_SESSIONS:
        raise DocumentError("Un brouillon contient 1 à 50 séances.")
    items = [_validated(thread_id, s) for s in sessions]
    with transaction() as con:
        _sources_still_present(con, thread_id, items)
        old = _get(con, thread_id, draft_id)
        if old["version"] != version or old["status"] != "draft":
            raise DocumentError("Le brouillon a changé. Recharge-le.")
        con.execute(
            "UPDATE app.coach_imports SET sessions=?,version=version+1 WHERE id=?",
            [json.dumps(items, ensure_ascii=False), draft_id],
        )
        return _get(con, thread_id, draft_id)


def confirm(
    thread_id: str,
    draft_id: str,
    version: int,
    key: str,
    selected: list[int],
    reviewed: bool,
) -> list[int]:
    key = str(UUID(key))
    if (
        not reviewed
        or not selected
        or len(selected) > MAX_DRAFT_SESSIONS
        or len(set(selected)) != len(selected)
    ):
        raise DocumentError("Vérifie les sources et sélectionne les séances à ajouter.")
    # Revalidate before the transaction: document parsing never holds a write lock.
    with db_connection() as con:
        current = _get(con, thread_id, draft_id)
    if current["status"] == "confirmed":
        if current["confirmation_key"] == key and current["selected"] == selected:
            return [int(i) for i in current["session_ids"]]
        raise DocumentError("Ce brouillon a déjà été confirmé.")
    if current["version"] != version or any(
        i < 0 or i >= len(current["sessions"]) for i in selected
    ):
        raise DocumentError("Sélection ou version du brouillon invalide.")
    items = [
        _validated(
            thread_id, ImportedSession.model_validate(current["sessions"][i]["session"])
        )
        for i in selected
    ]
    if any(item["problems"] for item in items):
        raise DocumentError("Corrige les problèmes signalés avant confirmation.")
    with transaction() as con:
        _sources_still_present(con, thread_id, items)
        changed = con.execute(
            "UPDATE app.coach_imports SET status='confirmed',confirmation_key=?,selected=? WHERE id=? AND thread_id=? AND version=? AND status='draft' RETURNING id",
            [key, json.dumps(selected), draft_id, thread_id, version],
        ).fetchone()
        if not changed:
            raise DocumentError(
                "Le brouillon a changé. Recharge-le sans recréer les séances."
            )
        ids = []
        for item in items:
            s = item["session"]
            row = con.execute(
                "INSERT INTO app.planned_sessions (user_id,date,sport,session_type,description,source,status,prescription,provenance,revision) VALUES (1,?,?,?,?,'coach','pending',?,?,1) RETURNING id",
                [
                    s["date"],
                    s["sport"],
                    s["session_type"],
                    s["description"],
                    json.dumps(s["prescription"]),
                    json.dumps(item["sources"], ensure_ascii=False),
                ],
            ).fetchone()
            assert row
            ids.append(int(row[0]))
        con.execute(
            "UPDATE app.coach_imports SET session_ids=? WHERE id=?",
            [json.dumps(ids), draft_id],
        )
    return ids


def has_unvalidated_documents(thread_id: str) -> bool:
    documents = {d["id"] for d in list_documents(thread_id)}
    if not documents:
        return False
    drafts = list_drafts(thread_id)
    if any(d["status"] == "draft" for d in drafts):
        return True
    confirmed = {
        p["document_id"]
        for d in drafts
        if d["status"] in {"confirmed", "discarded"}
        for item in d["sessions"]
        for p in item["session"]["provenance"]
    }
    return bool(documents - confirmed)


def discard(thread_id: str, draft_id: str, version: int) -> None:
    with transaction() as con:
        changed = con.execute(
            "UPDATE app.coach_imports SET status='discarded',version=version+1 WHERE id=? AND thread_id=? AND version=? AND status='draft' RETURNING id",
            [str(UUID(draft_id)), str(UUID(thread_id)), version],
        ).fetchone()
        if not changed:
            raise DocumentError("Le brouillon a changé ou a déjà été confirmé.")
