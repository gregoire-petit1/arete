"""Thin conversational Garmin adapters; services own validation and writes."""

import json
from datetime import date

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from arete.services import garmin_export, garmin_sync
from arete.services.prescriptions import conversation_prescription


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


@tool
def inspect_planned_session(session_id: int) -> str:
    """Read a session's steps, revision, derived structure and Garmin export state."""
    try:
        return _json(garmin_export.inspect_session(session_id))
    except ValueError as exc:
        return _json({"error": str(exc)})


@tool
def update_session_prescription(
    session_id: int,
    revision: int,
    date_str: str,
    description: str,
    prescription_json: str,
    strength_text: str = "",
) -> str:
    """Replace planned steps locally; requires the revision read by inspect_planned_session.

    prescription_json uses the create_planned_session prescription format.
    For strength, pass the exact strength_text to verify sets through the grammar.
    This never exports. Keep the same session id; never delete then recreate.
    """
    try:
        view = garmin_export.inspect_session(session_id)
        day = date.fromisoformat(date_str)
        prescription = conversation_prescription(
            prescription_json, view["session"]["sport"], day, strength_text
        )
        if not description or len(description) > 500:
            raise ValueError("Description requise, maximum 500 caractères.")
        garmin_export.update_session(
            session_id, revision, day, description, prescription
        )
        return _json(garmin_export.inspect_session(session_id, include_steps=False))
    except ValueError as exc:
        return _json({"error": str(exc)})


@tool
def list_garmin_devices(config: RunnableConfig) -> str:
    """List Garmin devices only when the athlete explicitly requests watch transfer."""
    try:
        return _json(
            garmin_export.devices(
                exchange=garmin_export.Exchange(
                    deadline=config.get("configurable", {}).get("workout_deadline")
                )
            )
        )
    except (ValueError, PermissionError) as exc:
        return _json({"error": str(exc)})


@tool
def export_garmin_sessions(
    session_ids: list[int], config: RunnableConfig, device_id: int | None = None
) -> str:
    """Send 1–5 distinct planned session ids TO Garmin on explicit request; default Garmin Connect.

    Only when the athlete asks to send, export or schedule named sessions:
    "synchroniser Garmin" is an import (sync_garmin_activities), never this.
    Stops at the first failure. Never replay an uncertain write or the entire batch.
    device_id is only for explicitly requested, verified watch transfer.
    """
    options = config.get("configurable", {})
    context = options.get("arete_context")
    today = getattr(context, "current_date", None) or date.today()
    try:
        # A model once read "synchronise Garmin" as an export of last week's plan.
        past = [
            session_id
            for session_id in session_ids
            if str(
                garmin_export.inspect_session(session_id, include_steps=False)[
                    "session"
                ]["date"]
            )[:10]
            < today.isoformat()
        ]
        if past:
            return _json(
                {"error": f"Séances passées, jamais exportées vers Garmin : {past}."}
            )
        return _json(
            garmin_export.export_batch(
                session_ids,
                device_id,
                deadline=options.get("workout_deadline"),
                on_progress=options.get("workout_progress"),
            )
        )
    except (ValueError, ConnectionError, TimeoutError, PermissionError) as exc:
        return _json({"error": str(exc)})


@tool
def reconcile_garmin_session(session_id: int, config: RunnableConfig) -> str:
    """Verify an uncertain Garmin outcome before considering another explicit export."""
    try:
        state = garmin_export.reconcile(
            session_id, deadline=config.get("configurable", {}).get("workout_deadline")
        )
        view = garmin_export.inspect_session(session_id, include_steps=False)
        if state["state"] in {"uncertain", "conflict", "failed"}:
            view["error"] = state["error"] or "Vérification Garmin incomplète."
        return _json(view)
    except ValueError as exc:
        return _json({"error": str(exc)})


@tool
def sync_garmin_activities(config: RunnableConfig) -> str:
    """Import the athlete's completed activities FROM Garmin Connect, like the sync button.

    This is what "synchronise Garmin" means; it never sends planned sessions.
    Once per turn, when asked to sync or when a recent session is missing.
    Returns the imported sessions; never call it again to retry.
    """
    try:
        return _json(
            garmin_sync.sync_recent(
                deadline=config.get("configurable", {}).get("workout_deadline")
            )
        )
    except (PermissionError, RuntimeError) as exc:
        return _json({"error": str(exc)})


GARMIN_TOOLS = [
    list_garmin_devices,
    export_garmin_sessions,
    reconcile_garmin_session,
    sync_garmin_activities,
]
