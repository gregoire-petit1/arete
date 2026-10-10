"""Publish immutable Git bundles to the database; no agent-facing write API."""

import hashlib
import json
from itertools import islice
from pathlib import Path

from arete.dataio.db import transaction

MAX_SYSTEM_SKILLS = 32
MAX_SKILL_BYTES = 32_768


def publish_bundle(root: Path) -> dict[str, str]:
    """Return the DB snapshot for this release, without replacing other releases.

    Called by composition once per cached chat graph, never at import time.
    The digest isolates rolling deployments and makes publication idempotent.
    """
    files = {}
    paths = sorted(islice(root.glob("*/SKILL.md"), MAX_SYSTEM_SKILLS + 1))
    if len(paths) > MAX_SYSTEM_SKILLS:
        raise ValueError("Too many system skills")
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("System skills must belong to the versioned bundle")
        with path.open("rb") as source:
            content = source.read(MAX_SKILL_BYTES + 1)
        if len(content) > MAX_SKILL_BYTES:
            raise ValueError(f"System skill exceeds byte limit: {path.name}")
        files["/" + path.relative_to(root).as_posix()] = content.decode("utf-8")
    if not files:
        raise ValueError("System skill bundle is empty")
    digest = hashlib.sha256(
        json.dumps(files, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    with transaction() as con:
        con.executemany(
            "INSERT INTO app.system_skills (bundle, path, content) VALUES (?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            [(digest, path, content) for path, content in files.items()],
        )
        rows = con.execute(
            "SELECT path, content FROM app.system_skills WHERE bundle=? LIMIT ?",
            [digest, MAX_SYSTEM_SKILLS + 1],
        ).fetchall()
        snapshot = dict(rows)
        if snapshot != files:
            raise RuntimeError("Stored system skill bundle differs from Git content")
    return snapshot
