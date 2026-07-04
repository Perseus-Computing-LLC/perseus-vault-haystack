# SPDX-FileCopyrightText: 2026 Perseus Computing LLC
#
# SPDX-License-Identifier: MIT

"""Haystack 2.x components wrapping the Perseus Vault memory store."""

from __future__ import annotations

from typing import Any

from haystack import component, default_from_dict, default_to_dict
from haystack.dataclasses import Document

from .memory_store import PerseusVaultMemoryStore


@component
class PerseusVaultMemoryWriter:
    """Haystack component that persists ``Document``s into a ``PerseusVaultMemoryStore``.

    Slots into a pipeline as a sink: it writes the incoming documents to Perseus
    Vault and passes them through unchanged (plus a count), so it can also sit
    mid-pipeline.

    Usage::

        from perseus_vault_haystack import PerseusVaultMemoryStore, PerseusVaultMemoryWriter

        store = PerseusVaultMemoryStore(db_path="~/.mimir/haystack.db")
        writer = PerseusVaultMemoryWriter(memory_store=store)
        writer.run(documents=[Document(content="Perseus Vault is local-first.")])
    """

    def __init__(self, *, memory_store: PerseusVaultMemoryStore) -> None:
        """Initialize the writer.

        :param memory_store: Backing :class:`PerseusVaultMemoryStore` to write into.
        """
        if not isinstance(memory_store, PerseusVaultMemoryStore):
            msg = "memory_store must be an instance of PerseusVaultMemoryStore"
            raise ValueError(msg)
        self._memory_store = memory_store

    @component.output_types(documents=list[Document], documents_written=int)
    def run(self, documents: list[Document]) -> dict[str, Any]:
        """Store ``documents`` in Perseus Vault and pass them through.

        :param documents: Documents to persist.
        :returns: ``{"documents": <same documents>, "documents_written": <count>}``.
        """
        written = self._memory_store.add_memories(documents)
        return {"documents": documents, "documents_written": written}

    def to_dict(self) -> dict[str, Any]:
        """Serialize this component to a dictionary."""
        return default_to_dict(self, memory_store=self._memory_store.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PerseusVaultMemoryWriter:
        """Deserialize a component from a dictionary."""
        data["init_parameters"]["memory_store"] = PerseusVaultMemoryStore.from_dict(
            data["init_parameters"]["memory_store"]
        )
        return default_from_dict(cls, data)


@component
class PerseusVaultMemoryRetriever:
    """Haystack component that retrieves ``Document``s from a ``PerseusVaultMemoryStore``.

    A thin pipeline adapter over :meth:`PerseusVaultMemoryStore.search_memories`.
    Takes a ``query`` and returns the most relevant stored documents — drop it in
    front of a prompt builder for retrieval-augmented generation over persistent
    memory.

    Usage::

        from perseus_vault_haystack import PerseusVaultMemoryStore, PerseusVaultMemoryRetriever

        store = PerseusVaultMemoryStore(db_path="~/.mimir/haystack.db")
        retriever = PerseusVaultMemoryRetriever(memory_store=store, top_k=5)
        result = retriever.run(query="What is Perseus Vault?")
        docs = result["documents"]
    """

    def __init__(self, *, memory_store: PerseusVaultMemoryStore, top_k: int | None = None) -> None:
        """Initialize the retriever.

        :param memory_store: Backing :class:`PerseusVaultMemoryStore` to query.
        :param top_k: Default max results; falls back to the store's ``top_k``
            when ``None``.
        """
        if not isinstance(memory_store, PerseusVaultMemoryStore):
            msg = "memory_store must be an instance of PerseusVaultMemoryStore"
            raise ValueError(msg)
        self._memory_store = memory_store
        self._top_k = top_k

    @component.output_types(documents=list[Document])
    def run(self, query: str, top_k: int | None = None) -> dict[str, list[Document]]:
        """Search the attached store and return matching documents.

        :param query: Natural-language / keyword query.
        :param top_k: Per-call override; falls back to init ``top_k``, then the
            store's default.
        :returns: ``{"documents": [Document, ...]}`` ordered by relevance.
        """
        effective_top_k = top_k if top_k is not None else self._top_k
        documents = self._memory_store.search_memories(query=query, top_k=effective_top_k)
        return {"documents": documents}

    def to_dict(self) -> dict[str, Any]:
        """Serialize this component to a dictionary."""
        return default_to_dict(self, memory_store=self._memory_store.to_dict(), top_k=self._top_k)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PerseusVaultMemoryRetriever:
        """Deserialize a component from a dictionary."""
        data["init_parameters"]["memory_store"] = PerseusVaultMemoryStore.from_dict(
            data["init_parameters"]["memory_store"]
        )
        return default_from_dict(cls, data)
