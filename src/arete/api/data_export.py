"""HTTP contract for the athlete's data export; the service owns the content."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Response

from arete.services import data_export

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/{fmt}")
def download_export(
    fmt: data_export.ExportFormat,
    start: date | None = None,
    end: date | None = None,
    tables: list[str] | None = Query(default=None),
) -> Response:
    """The athlete's data as a ZIP of CSV files or one JSON document."""
    try:
        file = data_export.build(fmt, start=start, end=end, names=tables)
    except data_export.ExportTooLarge as e:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Export trop volumineux ({e.size / 1e6:.1f} Mo, limite "
                f"{data_export.EXPORT_LIMIT_BYTES / 1e6:.0f} Mo) : choisis une "
                "période plus courte, moins de tables ou le format ZIP."
            ),
        ) from None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    return Response(
        content=file.content,
        media_type=file.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file.filename}"',
            "Cache-Control": "no-store",
        },
    )
