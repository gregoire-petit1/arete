"""Bounded skill selection before the first request; no model or embedding call."""

import re
import unicodedata

from deepagents.backends.protocol import FileDownloadResponse
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.messages import SystemMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.retrievers import BaseRetriever

from arete.services.system_skills import MAX_SKILL_BYTES, MAX_SYSTEM_SKILLS

MAX_PRELOADED_SKILLS = 3
MAX_SKILL_PRELOAD_TOKENS = 2_048
MAX_SKILL_QUERY_CHARS = 16_000


class SkillSelectionError(ValueError):
    """An explicit slash command cannot be honored; never silently ignore it."""


def requested_skill_paths(query: str, skills: list[dict]) -> tuple[str, ...]:
    """Resolve leading /name commands only against the trusted discovery list."""
    by_name = {skill["name"]: skill["path"] for skill in skills}
    paths = []
    remaining = query.lstrip()
    for _ in range(MAX_PRELOADED_SKILLS + 1):
        match = re.match(r"/([a-z0-9-]+)(?=\s|$)", remaining)
        if match is None:
            break
        name = match[1]
        if name not in by_name:
            raise SkillSelectionError(
                f"Skill inconnu : /{name}. Choisis un skill dans le menu /."
            )
        if by_name[name] not in paths:
            paths.append(by_name[name])
        remaining = remaining[match.end() :].lstrip()
    else:
        raise SkillSelectionError(
            f"Choisis au maximum {MAX_PRELOADED_SKILLS} skills par demande."
        )
    if remaining == "/":
        raise SkillSelectionError("Choisis un skill dans le menu / avant d’envoyer.")
    return tuple(paths)


def prioritize_requested(
    matches: list[Document], paths: tuple[str, ...]
) -> list[Document]:
    # Explicit selection bypasses relevance, never authorization or token limits.
    return [Document(page_content="", metadata={"path": path}) for path in paths] + [
        doc for doc in matches if doc.metadata["path"] not in paths
    ]


def _terms(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return re.findall(
        r"\w+", "".join(c for c in normalized if not unicodedata.combining(c))
    )


class SystemSkillRetriever(BaseRetriever):
    """Rank server-declared activation terms, avoiding generic prose matches.

    Skills without activation metadata stay available through native discovery.
    BM25Plus with delta=0 admits only positive matches, including a one-skill
    catalog; BM25Okapi can assign zero/negative scores in such a small corpus.
    """

    documents: list[Document]

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        from rank_bm25 import BM25Plus

        assert len(self.documents) <= MAX_SYSTEM_SKILLS
        if len(query) > MAX_SKILL_QUERY_CHARS:
            raise ValueError("Skill retrieval query exceeds its character limit")
        terms = list(dict.fromkeys(_terms(query)))
        if not self.documents or not terms:
            return []
        corpus = [_terms(doc.page_content) for doc in self.documents]
        assert all(corpus), "Skill activation terms must not be empty"
        scores = BM25Plus(corpus, k1=1.5, b=0.75, delta=0).get_scores(terms)
        ranked = sorted(
            (i for i, score in enumerate(scores) if score > 0),
            key=lambda i: (-scores[i], self.documents[i].metadata["path"]),
        )
        # Return all matches (at most 32) so selection can report budget omissions.
        return [self.documents[i] for i in ranked]


def skill_retriever(
    skills: list[dict], *, has_attachments: bool
) -> SystemSkillRetriever:
    documents = []
    for skill in skills:
        metadata = skill["metadata"]
        keywords = metadata.get("preload-keywords", "")
        requires = metadata.get("preload-requires", "")
        if requires not in ("", "attachments"):
            raise ValueError(f"Unknown skill preload requirement: {requires}")
        if not keywords or (requires == "attachments" and not has_attachments):
            continue
        documents.append(
            Document(page_content=keywords, metadata={"path": skill["path"]})
        )
    return SystemSkillRetriever(documents=documents)


def preload_section(bodies: dict[str, str]) -> str:
    if not bodies:
        return ""
    return (
        "Skills système préchargés pour cette demande : applique leur méthode "
        "sans relire leur SKILL.md. Ils n’accordent aucun outil ni permission.\n\n"
        + "\n\n".join(f"### {path}\n{body}" for path, body in sorted(bodies.items()))
    )


def preload_tokens(bodies: dict[str, str]) -> int:
    return int(count_tokens_approximately([SystemMessage(preload_section(bodies))]))


def select_preloads(
    matches: list[Document],
    responses: list[FileDownloadResponse],
    *,
    required: tuple[str, ...] = (),
) -> tuple[dict[str, str], bool]:
    """Keep whole bodies within the envelope; omissions stay discoverable."""
    paths = [doc.metadata["path"] for doc in matches[:MAX_PRELOADED_SKILLS]]
    if len(responses) != len(paths):
        raise RuntimeError("Incomplete system skill preload")
    bodies: dict[str, str] = {}
    for path, response in zip(paths, responses, strict=True):
        if response.path != path or response.error or response.content is None:
            raise RuntimeError(f"System skill preload failed: {path}")
        if len(response.content) > MAX_SKILL_BYTES:
            raise ValueError(f"System skill exceeds byte limit: {path}")
        body = response.content.decode("utf-8")
        candidate = {**bodies, path: body}
        if preload_tokens(candidate) <= MAX_SKILL_PRELOAD_TOKENS:
            bodies = candidate
        elif path in required:
            raise SkillSelectionError(
                "Les skills demandés dépassent le budget de préchargement. "
                "Choisis moins de skills ou demande au coach de lire le fichier du skill."
            )
    return bodies, len(bodies) < len(matches)
