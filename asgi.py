"""Vercel entrypoint.

The bundle ships ``src/`` without installing the package, hence the path.
Vercel hands the service the public path (``/api/health``) while the app
routes ``/health``, as it does behind nginx locally, hence the prefix strip.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from starlette.types import Receive, Scope, Send  # noqa: E402

from arete.api.main import app as arete_app  # noqa: E402

PREFIX = "/api"


async def app(scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] in ("http", "websocket"):
        path = scope["path"]
        if path == PREFIX or path.startswith(PREFIX + "/"):
            scope = {**scope, "path": path[len(PREFIX) :] or "/", "raw_path": None}
    await arete_app(scope, receive, send)
