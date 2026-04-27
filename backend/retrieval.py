from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List


@dataclass
class KnowledgeDocument:
    id: str
    type: str
    scenario: str
    intent: str
    skill: str
    content: str
    source: str
    tags: List[str]


class FaissKnowledgeBase:
    """Loads a FAISS index and retrieves small coaching snippets for prompt support."""

    def __init__(
        self,
        index_path: str | None = None,
        metadata_path: str | None = None,
        embedding_model: str | None = None,
        top_k: int = 3,
    ) -> None:
        self.index_path = Path(
            index_path
            or os.getenv("FAISS_INDEX_PATH")
            or Path(__file__).resolve().parents[1] / "data" / "faiss" / "coaching.index"
        )
        self.metadata_path = Path(
            metadata_path
            or os.getenv("FAISS_METADATA_PATH")
            or Path(__file__).resolve().parents[1] / "data" / "faiss" / "coaching_metadata.json"
        )
        self.embedding_model_name = (
            embedding_model
            or os.getenv("EMBEDDING_MODEL_NAME")
            or "sentence-transformers/all-MiniLM-L6-v2"
        )
        self.top_k = int(os.getenv("RETRIEVAL_TOP_K", str(top_k)))
        self._loaded = False
        self._lock = Lock()
        self._documents: List[KnowledgeDocument] = []
        self._index: Any = None
        self._encoder: Any = None
        self._enabled = False
        self._checked = False
        self._disabled_reason = "Retrieval has not been checked yet."

    def is_available(self) -> bool:
        return self.index_path.exists() and self.metadata_path.exists()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def disabled_reason(self) -> str:
        return self._disabled_reason

    def startup_check(self) -> bool:
        """Check once at startup whether retrieval should be used for this server run."""
        if self._checked:
            return self._enabled

        with self._lock:
            if self._checked:
                return self._enabled

            if not self.index_path.exists() or not self.metadata_path.exists():
                self._enabled = False
                self._checked = True
                self._disabled_reason = (
                    "FAISS retrieval disabled because the index or metadata file is missing."
                )
                return self._enabled

            try:
                import faiss  # type: ignore
                from sentence_transformers import SentenceTransformer  # type: ignore
            except ImportError:
                self._enabled = False
                self._checked = True
                self._disabled_reason = (
                    "FAISS retrieval disabled because faiss-cpu or sentence-transformers is not installed."
                )
                return self._enabled

            try:
                with self.metadata_path.open("r", encoding="utf-8") as handle:
                    raw_documents = json.load(handle)
                self._documents = [KnowledgeDocument(**item) for item in raw_documents]
                self._index = faiss.read_index(str(self.index_path))
                self._encoder = SentenceTransformer(self.embedding_model_name)
                self._enabled = True
                self._disabled_reason = ""
            except Exception as exc:
                self._enabled = False
                self._disabled_reason = (
                    f"FAISS retrieval disabled because startup loading failed: {exc}"
                )
            finally:
                self._checked = True

            return self._enabled

    def retrieve(
        self,
        query: str,
        scenario: str,
        intent: str,
        limit: int | None = None,
    ) -> List[KnowledgeDocument]:
        if not self._checked:
            self.startup_check()

        if not self._enabled:
            return []

        query_vector = self._encoder.encode([query], normalize_embeddings=True)
        search_limit = max(self.top_k * 4, limit or self.top_k)
        _, indices = self._index.search(query_vector, search_limit)

        ranked: List[KnowledgeDocument] = []
        for idx in indices[0]:
            if idx < 0 or idx >= len(self._documents):
                continue
            doc = self._documents[idx]
            if _matches_filters(doc, scenario, intent):
                ranked.append(doc)

        if not ranked:
            ranked = [
                doc
                for doc in self._documents
                if doc.scenario == scenario or doc.intent == intent or doc.intent == "any"
            ]

        return ranked[: (limit or self.top_k)]


def _matches_filters(doc: KnowledgeDocument, scenario: str, intent: str) -> bool:
    scenario_match = doc.scenario in {scenario, "any"}
    intent_match = doc.intent in {intent, "any"}
    return scenario_match and intent_match


def format_retrieved_context(documents: List[KnowledgeDocument]) -> str:
    if not documents:
        return "No extra coaching snippets retrieved."

    lines = []
    for doc in documents:
        lines.append(
            f"- [{doc.type}] scenario={doc.scenario} skill={doc.skill}: {doc.content}"
        )
    return "\n".join(lines)
