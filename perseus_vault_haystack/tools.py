# SPDX-FileCopyrightText: 2026 Perseus Computing LLC
#
# SPDX-License-Identifier: MIT

"""Ready-made Haystack ``Tool`` instances backed by Perseus Vault.

These let a Haystack ``Agent`` decide on its own when to store and retrieve
durable memory, the same way the ``mem0`` and ``hindsight`` integrations expose
their memory as agent tools. Three tools are provided:

- ``retain_memory``  — store a durable fact, preference, or piece of context.
- ``recall_memory``  — search memory and return the raw matching entries.
- ``reflect_memory`` — assemble a synthesis-ready context block over the most
  relevant memories, so the agent's own chat generator can reason a focused
  answer from them.

Unlike the cloud-backed alternatives, every tool here runs against a local,
encrypted Perseus Vault database with no API keys and no external services —
``reflect_memory`` deliberately does the synthesis in the caller's existing LLM
rather than requiring a separate provider, preserving the zero-dependency,
local-first guarantee.
"""

from __future__ import annotations

from typing import Any

from haystack.tools import Tool

from .memory_store import PerseusVaultMemoryStore

_RETAIN_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": (
                "The durable fact, user preference, or project context to store "
                "in long-term memory. Write it as a standalone statement."
            ),
        },
    },
    "required": ["text"],
}

_RECALL_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "What to search long-term memory for.",
        },
        "top_k": {
            "type": "integer",
            "description": "Maximum number of memories to return (optional).",
        },
    },
    "required": ["query"],
}

_REFLECT_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "The question to reflect on. Relevant memories are gathered into "
                "a context block for you to reason over and answer."
            ),
        },
        "top_k": {
            "type": "integer",
            "description": "Maximum number of memories to reflect over (optional).",
        },
    },
    "required": ["query"],
}


def create_perseus_vault_tools(
    memory_store: PerseusVaultMemoryStore,
    *,
    include_retain: bool = True,
    include_recall: bool = True,
    include_reflect: bool = True,
) -> list[Tool]:
    """Build Haystack ``Tool`` instances backed by ``memory_store``.

    :param memory_store: The :class:`PerseusVaultMemoryStore` the tools read and
        write. All tools share this store (and its single ``perseus-vault``
        subprocess), scoped to the store's ``category``.
    :param include_retain: Include the ``retain_memory`` (write) tool.
    :param include_recall: Include the ``recall_memory`` (raw search) tool.
    :param include_reflect: Include the ``reflect_memory`` (synthesis-context) tool.
    :returns: A list of :class:`~haystack.tools.Tool` ready to pass to an
        ``Agent(tools=...)``.
    """
    if not isinstance(memory_store, PerseusVaultMemoryStore):
        msg = "memory_store must be an instance of PerseusVaultMemoryStore"
        raise ValueError(msg)

    def _retain(text: str) -> str:
        from haystack.dataclasses import ChatMessage

        written = memory_store.write_messages([ChatMessage.from_user(text)])
        return "Stored 1 memory." if written else "Nothing stored (empty text)."

    def _recall(query: str, top_k: int | None = None) -> str:
        docs = memory_store.search_memories(query=query, top_k=top_k)
        if not docs:
            return "No relevant memories found."
        return "\n".join(f"- {doc.content}" for doc in docs)

    def _reflect(query: str, top_k: int | None = None) -> str:
        docs = memory_store.search_memories(query=query, top_k=top_k)
        if not docs:
            return f"No memories relevant to '{query}' were found."
        lines = "\n".join(f"- {doc.content}" for doc in docs)
        return (
            f"Relevant memories for '{query}':\n{lines}\n\n"
            "Synthesize a concise, direct answer grounded only in the memories above."
        )

    tools: list[Tool] = []
    if include_retain:
        tools.append(
            Tool(
                name="retain_memory",
                description=(
                    "Store a durable user-specific fact, preference, or piece of "
                    "project context in long-term memory for future sessions."
                ),
                parameters=_RETAIN_PARAMETERS,
                function=_retain,
            )
        )
    if include_recall:
        tools.append(
            Tool(
                name="recall_memory",
                description=(
                    "Search long-term memory and return the raw matching entries. "
                    "Call this before answering to ground responses in what you know."
                ),
                parameters=_RECALL_PARAMETERS,
                function=_recall,
            )
        )
    if include_reflect:
        tools.append(
            Tool(
                name="reflect_memory",
                description=(
                    "Gather the most relevant memories for a question into a "
                    "synthesis-ready context block to reason a focused answer over."
                ),
                parameters=_REFLECT_PARAMETERS,
                function=_reflect,
            )
        )
    return tools
