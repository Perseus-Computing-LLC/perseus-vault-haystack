# SPDX-FileCopyrightText: 2026 Perseus Computing LLC
#
# SPDX-License-Identifier: MIT

"""Mimir-backed memory store for Haystack 2.x."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from haystack import default_from_dict, default_to_dict
from haystack.dataclasses import Document

from ._client import MimirClient

logger = logging.getLogger(__name__)

_DEFAULT_CATEGORY = "haystack-memory"


class MimirMemoryStore:
    """Persistent memory backend backed by the Mimir engine.

    Wraps the Mimir MCP tools ``mimir_remember`` (write), ``mimir_recall``
    (search) and ``mimir_forget`` (delete). Each Haystack ``Document`` is stored
    as one Mimir entity; the document's ``content`` becomes the entity body and
    its ``meta`` is preserved as JSON. On recall, entities are rehydrated back
    into ``Document`` objects with their original ``id``, ``content``, ``meta``
    and a relevance ``score`` from Mimir.

    The store owns the long-lived ``mimir`` subprocess; the thin
    :class:`~mimir_haystack.MimirMemoryWriter` and
    :class:`~mimir_haystack.MimirMemoryRetriever` components delegate to it so a
    single store can back several pipeline components.

    This class is safe to use across threads (the underlying client is
    thread-safe).
    """

    def __init__(
        self,
        db_path: str = "~/.mimir/haystack.db",
        mimir_binary: str = "mimir",
        category: str = _DEFAULT_CATEGORY,
        top_k: int = 10,
        timeout_s: float = 30.0,
    ) -> None:
        """Initialize the store.

        :param db_path: Path to the Mimir SQLite database file.
        :param mimir_binary: Name (on ``$PATH``) or absolute path of the
            ``mimir`` executable.
        :param category: Mimir category that scopes every write and recall for
            this store. Use distinct categories to isolate corpora.
        :param top_k: Default maximum number of documents returned by
            :meth:`search_memories`.
        :param timeout_s: Per-RPC timeout for the underlying Mimir subprocess.
        """
        self.db_path = db_path
        self.mimir_binary = mimir_binary
        self.category = category
        self.top_k = top_k
        self.timeout_s = timeout_s

        self._client = MimirClient(
            db_path=db_path,
            mimir_binary=mimir_binary,
            timeout_s=timeout_s,
        )

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #
    def add_memories(self, documents: list[Document]) -> int:
        """Persist ``documents`` into Mimir via ``mimir_remember``.

        Documents with empty ``content`` are skipped. The document ``id`` is used
        as the Mimir entity key so re-writing the same document updates it in
        place (idempotent upsert).

        :param documents: Documents to store.
        :returns: The number of documents actually written.
        """
        written = 0
        for doc in documents:
            if not doc.content:
                continue
            key = doc.id or f"doc:{int(time.time() * 1_000_000)}:{written}"
            self._client.call_tool(
                "mimir_remember",
                {
                    "category": self.category,
                    "key": key,
                    "body_json": json.dumps(
                        {
                            "doc_id": doc.id,
                            "content": doc.content,
                            "meta": doc.meta or {},
                        }
                    ),
                    "tags": ["haystack"],
                },
            )
            written += 1
        logger.info("Stored %d documents in Mimir category '%s'", written, self.category)
        return written

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #
    def search_memories(self, query: str, top_k: int | None = None) -> list[Document]:
        """Search Mimir via ``mimir_recall`` and return matching documents.

        :param query: Natural-language / keyword query. Empty queries return
            ``[]``.
        :param top_k: Per-call override of the store's default ``top_k``.
        :returns: A list of :class:`~haystack.dataclasses.Document`, ordered by
            Mimir relevance, each carrying a ``score`` when Mimir provides one.
        """
        if not query:
            return []
        limit = top_k if top_k is not None else self.top_k
        result = self._client.call_tool(
            "mimir_recall",
            {"query": query, "limit": limit, "category": self.category},
        )
        items = result.get("items", []) or result.get("results", [])
        documents: list[Document] = []
        for item in items:
            body = item.get("body_json", "{}")
            try:
                body_data = json.loads(body) if isinstance(body, str) else body
            except (json.JSONDecodeError, TypeError):
                body_data = {}
            if not isinstance(body_data, dict):
                continue
            content = body_data.get("content") or item.get("content")
            if not content:
                continue
            # Mimir's recall ranks by relevance but names the field differently
            # across versions: prefer an explicit ``score``, else fall back to
            # ``certainty`` (relevance/confidence in v2.x).
            score = item.get("score")
            if score is None:
                score = item.get("certainty")
            documents.append(
                Document(
                    id=body_data.get("doc_id") or item.get("key", ""),
                    content=content,
                    meta=body_data.get("meta", {}) or {},
                    score=float(score) if isinstance(score, (int, float)) else None,
                )
            )
        logger.info("Recalled %d documents for query '%s'", len(documents), query[:80])
        return documents

    # ------------------------------------------------------------------ #
    # Delete
    # ------------------------------------------------------------------ #
    def delete_all_memories(self) -> None:
        """Delete every entity in this store's category via ``mimir_forget``."""
        self._client.call_tool("mimir_forget", {"category": self.category})
        logger.info("Deleted all documents in Mimir category '%s'", self.category)

    # ------------------------------------------------------------------ #
    # Serialization
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, Any]:
        """Serialize this store for pipeline persistence."""
        return default_to_dict(
            self,
            db_path=self.db_path,
            mimir_binary=self.mimir_binary,
            category=self.category,
            top_k=self.top_k,
            timeout_s=self.timeout_s,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MimirMemoryStore:
        """Deserialize a store from a dict produced by :meth:`to_dict`."""
        return default_from_dict(cls, data)
