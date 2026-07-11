# SPDX-FileCopyrightText: 2026 Perseus Computing LLC
#
# SPDX-License-Identifier: MIT

"""Automatic memory wrapper for Haystack agents backed by Perseus Vault.

``PerseusVaultMemoryWrapper`` gives an agent long-term memory without relying on
the model to call tools: before each turn it recalls relevant memories and
injects them into the conversation as ``system`` messages (``auto_recall``), and
after the turn it stores the exchange (``auto_retain``). This mirrors the
ergonomics of ``HindsightMemoryWrapper`` while running entirely against a local,
encrypted Perseus Vault database — no API keys, no cloud.
"""

from __future__ import annotations

from typing import Any

from haystack.dataclasses import ChatMessage

from .memory_store import PerseusVaultMemoryStore


class PerseusVaultMemoryWrapper:
    """Wrap an agent with automatic recall-before / retain-after memory.

    :param memory_store: Backing :class:`PerseusVaultMemoryStore`.
    :param auto_recall: Inject relevant memories as ``system`` messages before
        each turn.
    :param auto_retain: Store the turn's user + assistant messages after each run.
    :param top_k: Maximum memories to inject when recalling.
    """

    def __init__(
        self,
        memory_store: PerseusVaultMemoryStore,
        *,
        auto_recall: bool = True,
        auto_retain: bool = True,
        top_k: int | None = None,
    ) -> None:
        if not isinstance(memory_store, PerseusVaultMemoryStore):
            msg = "memory_store must be an instance of PerseusVaultMemoryStore"
            raise ValueError(msg)
        self._memory_store = memory_store
        self.auto_recall = auto_recall
        self.auto_retain = auto_retain
        self.top_k = top_k

    # ------------------------------------------------------------------ #
    # Public helpers (also usable standalone, without an agent)
    # ------------------------------------------------------------------ #
    def recall(self, query: str, top_k: int | None = None) -> list[ChatMessage]:
        """Return relevant memories as ``system`` messages for ``query``."""
        return self._memory_store.recall_messages(
            query=query, top_k=top_k if top_k is not None else self.top_k
        )

    def retain(self, messages: list[ChatMessage]) -> int:
        """Persist ``messages`` to long-term memory. Returns the count written."""
        return self._memory_store.write_messages(messages)

    # ------------------------------------------------------------------ #
    # Agent driver
    # ------------------------------------------------------------------ #
    def run(self, agent: Any, messages: list[ChatMessage], **kwargs: Any) -> dict[str, Any]:
        """Drive ``agent`` with automatic recall + retain around the turn.

        The most recent user message is used as the recall query. Recalled
        memories are prepended as ``system`` messages, the agent runs, and (when
        ``auto_retain`` is on) the incoming user messages plus the agent's reply
        are written back to memory.

        :param agent: Any object with a ``run(messages=..., **kwargs)`` method
            returning a dict (e.g. a Haystack ``Agent``).
        :param messages: The conversation turn's messages.
        :returns: The agent's result dict, unchanged.
        """
        query = ""
        for msg in reversed(messages):
            role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
            if role == "user" and msg.text:
                query = msg.text
                break

        run_messages = list(messages)
        if self.auto_recall and query:
            memories = self.recall(query)
            run_messages = memories + run_messages

        result = agent.run(messages=run_messages, **kwargs)

        if self.auto_retain:
            to_store = [m for m in messages if (m.text or "").strip()]
            reply = self._extract_reply(result)
            if reply is not None:
                to_store.append(reply)
            if to_store:
                self.retain(to_store)

        return result

    @staticmethod
    def _extract_reply(result: dict[str, Any]) -> ChatMessage | None:
        """Best-effort pull of the assistant reply from an agent result dict."""
        if not isinstance(result, dict):
            return None
        last = result.get("last_message")
        if isinstance(last, ChatMessage):
            return last
        msgs = result.get("messages")
        if isinstance(msgs, list) and msgs and isinstance(msgs[-1], ChatMessage):
            return msgs[-1]
        return None
