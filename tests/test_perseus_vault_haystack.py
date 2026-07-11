# SPDX-FileCopyrightText: 2026 Perseus Computing LLC
#
# SPDX-License-Identifier: MIT

"""Unit tests for perseus-vault-haystack.

The Perseus Vault subprocess is mocked at the ``PerseusVaultClient`` boundary so
these tests run without the ``perseus-vault`` binary installed.
"""

import json
from unittest.mock import MagicMock

import pytest
from haystack import Document


def _output_sockets(comp):
    """Return {name: type} for a component instance's declared output types."""
    return {
        name: socket.type
        for name, socket in comp.__haystack_output__._sockets_dict.items()
    }

from perseus_vault_haystack import (
    PerseusVaultMemoryRetriever,
    PerseusVaultMemoryStore,
    PerseusVaultMemoryWriter,
)


class FakePerseusVaultClient:
    """In-memory stand-in for PerseusVaultClient.call_tool.

    Implements just enough of perseus_vault_remember / perseus_vault_recall /
    perseus_vault_forget to exercise the store end-to-end without a subprocess.
    """

    def __init__(self, *args, **kwargs):
        self.store = {}  # key -> body_json
        self.calls = []

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "perseus_vault_remember":
            self.store[arguments["key"]] = arguments["body_json"]
            return {"ok": True}
        if name == "perseus_vault_recall":
            query = arguments.get("query", "").lower()
            limit = arguments.get("limit", 10)
            # Mirror Perseus Vault FTS5 semantics: query words are OR'd against
            # the stored content (not a naive full-string substring match).
            terms = [t.strip("?.!,") for t in query.split() if len(t.strip("?.!,")) > 2]
            items = []
            for key, body_json in self.store.items():
                body = json.loads(body_json)
                content = body.get("content", "").lower()
                if any(term in content for term in terms):
                    items.append({"key": key, "body_json": body_json, "score": 0.9})
            return {"items": items[:limit]}
        if name == "perseus_vault_forget":
            self.store.clear()
            return {"ok": True}
        return {}


@pytest.fixture
def store(monkeypatch):
    """A PerseusVaultMemoryStore whose client is the in-memory fake."""
    fake = FakePerseusVaultClient()
    s = PerseusVaultMemoryStore(db_path="/tmp/test.db", category="test")
    monkeypatch.setattr(s, "_client", fake)
    return s


# --------------------------------------------------------------------------- #
# PerseusVaultMemoryStore
# --------------------------------------------------------------------------- #
def test_add_and_search(store):
    written = store.add_memories(
        [
            Document(content="Perseus Vault is a local-first memory engine."),
            Document(content="Haystack is an LLM framework."),
        ]
    )
    assert written == 2

    hits = store.search_memories("perseus vault")
    assert len(hits) == 1
    assert "local-first" in hits[0].content
    assert hits[0].score == pytest.approx(0.9)


def test_add_skips_empty_content(store):
    written = store.add_memories([Document(content=""), Document(content=None)])
    assert written == 0


def test_search_empty_query_returns_empty(store):
    assert store.search_memories("") == []


def test_search_preserves_meta_and_id(store):
    store.add_memories([Document(id="d1", content="alpha beta", meta={"k": "v"})])
    hits = store.search_memories("alpha")
    assert hits[0].id == "d1"
    assert hits[0].meta == {"k": "v"}


def test_top_k_override(store):
    store.add_memories([Document(content=f"item number {i}") for i in range(5)])
    hits = store.search_memories("item", top_k=2)
    assert len(hits) == 2


def test_delete_all(store):
    store.add_memories([Document(content="to be deleted")])
    store.delete_all_memories()
    assert store.search_memories("deleted") == []


def test_store_to_dict_from_dict_roundtrip():
    s = PerseusVaultMemoryStore(
        db_path="/x/y.db",
        perseus_vault_binary="/opt/perseus-vault",
        category="c",
        top_k=7,
        timeout_s=12.0,
    )
    d = s.to_dict()
    assert d["init_parameters"]["category"] == "c"
    assert d["init_parameters"]["top_k"] == 7
    s2 = PerseusVaultMemoryStore.from_dict(d)
    assert s2.db_path == "/x/y.db"
    assert s2.perseus_vault_binary == "/opt/perseus-vault"
    assert s2.category == "c"
    assert s2.top_k == 7
    assert s2.timeout_s == 12.0


# --------------------------------------------------------------------------- #
# PerseusVaultMemoryWriter
# --------------------------------------------------------------------------- #
def test_writer_run(store):
    writer = PerseusVaultMemoryWriter(memory_store=store)
    docs = [Document(content="written via component")]
    out = writer.run(documents=docs)
    assert out["documents_written"] == 1
    assert out["documents"] == docs
    # confirm it actually landed in the store
    assert store.search_memories("written")[0].content == "written via component"


def test_writer_output_types(store):
    sockets = _output_sockets(PerseusVaultMemoryWriter(memory_store=store))
    assert sockets["documents"] == list[Document]
    assert sockets["documents_written"] is int


def test_writer_rejects_bad_store():
    with pytest.raises(ValueError):
        PerseusVaultMemoryWriter(memory_store=object())


def test_writer_to_dict_from_dict():
    s = PerseusVaultMemoryStore(category="w")
    writer = PerseusVaultMemoryWriter(memory_store=s)
    d = writer.to_dict()
    assert d["type"].endswith("PerseusVaultMemoryWriter")
    assert d["init_parameters"]["memory_store"]["init_parameters"]["category"] == "w"
    writer2 = PerseusVaultMemoryWriter.from_dict(d)
    assert isinstance(writer2._memory_store, PerseusVaultMemoryStore)
    assert writer2._memory_store.category == "w"


# --------------------------------------------------------------------------- #
# PerseusVaultMemoryRetriever
# --------------------------------------------------------------------------- #
def test_retriever_run(store):
    store.add_memories([Document(content="findable content here")])
    retriever = PerseusVaultMemoryRetriever(memory_store=store)
    out = retriever.run(query="findable")
    assert len(out["documents"]) == 1
    assert out["documents"][0].content == "findable content here"


def test_retriever_output_types(store):
    sockets = _output_sockets(PerseusVaultMemoryRetriever(memory_store=store))
    assert sockets["documents"] == list[Document]


def test_retriever_top_k_precedence(store):
    store.add_memories([Document(content=f"match {i}") for i in range(5)])
    # init top_k=2, call override=1 -> override wins
    retriever = PerseusVaultMemoryRetriever(memory_store=store, top_k=2)
    assert len(retriever.run(query="match", top_k=1)["documents"]) == 1
    # no override -> init top_k=2
    assert len(retriever.run(query="match")["documents"]) == 2


def test_retriever_rejects_bad_store():
    with pytest.raises(ValueError):
        PerseusVaultMemoryRetriever(memory_store=object())


def test_retriever_to_dict_from_dict():
    s = PerseusVaultMemoryStore(category="r")
    retriever = PerseusVaultMemoryRetriever(memory_store=s, top_k=3)
    d = retriever.to_dict()
    assert d["init_parameters"]["top_k"] == 3
    retriever2 = PerseusVaultMemoryRetriever.from_dict(d)
    assert isinstance(retriever2._memory_store, PerseusVaultMemoryStore)
    assert retriever2._top_k == 3


# --------------------------------------------------------------------------- #
# Pipeline integration (serialization round-trip through a real Pipeline)
# --------------------------------------------------------------------------- #
def test_components_in_pipeline_dumps_loads():
    from haystack import Pipeline

    s = PerseusVaultMemoryStore(category="pipe")
    pipe = Pipeline()
    pipe.add_component("writer", PerseusVaultMemoryWriter(memory_store=s))
    pipe.add_component("retriever", PerseusVaultMemoryRetriever(memory_store=s))
    yaml_str = pipe.dumps()
    assert "PerseusVaultMemoryWriter" in yaml_str
    assert "PerseusVaultMemoryRetriever" in yaml_str
    restored = Pipeline.loads(yaml_str)
    assert restored.get_component("writer") is not None
    assert restored.get_component("retriever") is not None


# --------------------------------------------------------------------------- #
# Client binary resolution (no subprocess spawned)
# --------------------------------------------------------------------------- #
def test_client_missing_binary_raises():
    from perseus_vault_haystack._client import PerseusVaultClient

    c = PerseusVaultClient(perseus_vault_binary="definitely-not-a-real-binary-xyz")
    with pytest.raises(RuntimeError, match="perseus-vault binary not found"):
        c.start()


# --------------------------------------------------------------------------- #
# Real-binary smoke test (skipped automatically when no perseus-vault binary
# is found)
# --------------------------------------------------------------------------- #
def _resolve_real_perseus_vault():
    """Locate a real perseus-vault binary, honoring PERSEUS_VAULT_BINARY override.

    Prefers the canonical ``perseus-vault`` name; falls back to the legacy
    ``mimir`` compat symlink so the smoke test still runs on older installs.
    """
    import os
    import shutil

    explicit = os.environ.get("PERSEUS_VAULT_BINARY")
    if explicit and os.path.exists(explicit):
        return explicit
    found = (
        shutil.which("perseus-vault")
        or shutil.which("perseus-vault.exe")
        or shutil.which("mimir")
        or shutil.which("mimir.exe")
    )
    return found


@pytest.mark.skipif(
    _resolve_real_perseus_vault() is None, reason="perseus-vault binary not available"
)
def test_real_roundtrip(tmp_path):
    """End-to-end write+recall against a real perseus-vault subprocess."""
    binary = _resolve_real_perseus_vault()
    s = PerseusVaultMemoryStore(
        db_path=str(tmp_path / "real.db"),
        perseus_vault_binary=binary,
        category="pytest-smoke",
        timeout_s=20,
    )
    written = s.add_memories(
        [Document(id="r1", content="Perseus Vault provides persistent memory.", meta={"k": "v"})]
    )
    assert written == 1
    hits = s.search_memories("persistent memory", top_k=5)
    assert any(h.content == "Perseus Vault provides persistent memory." for h in hits)
    s._client.close()


# --------------------------------------------------------------------------- #
# ChatMessage API
# --------------------------------------------------------------------------- #
def test_write_and_recall_messages(store):
    from haystack.dataclasses import ChatMessage

    written = store.write_messages(
        [
            ChatMessage.from_user("Alice prefers concise answers."),
            ChatMessage.from_assistant("Understood."),
        ]
    )
    assert written == 2
    msgs = store.recall_messages("concise", top_k=5)
    assert msgs and all(m.role.value == "system" for m in msgs)
    assert any("concise" in m.text for m in msgs)


def test_write_messages_skips_empty(store):
    from haystack.dataclasses import ChatMessage

    assert store.write_messages([ChatMessage.from_user("   ")]) == 0


# --------------------------------------------------------------------------- #
# Agent tools
# --------------------------------------------------------------------------- #
def test_create_tools_default_set(store):
    from perseus_vault_haystack import create_perseus_vault_tools

    tools = create_perseus_vault_tools(store)
    assert [t.name for t in tools] == ["retain_memory", "recall_memory", "reflect_memory"]


def test_tools_selective_inclusion(store):
    from perseus_vault_haystack import create_perseus_vault_tools

    tools = create_perseus_vault_tools(store, include_reflect=False, include_recall=False)
    assert [t.name for t in tools] == ["retain_memory"]


def test_retain_and_recall_tools_roundtrip(store):
    from perseus_vault_haystack import create_perseus_vault_tools

    retain, recall, reflect = create_perseus_vault_tools(store)
    assert retain.invoke(text="The vault is encrypted with AES-256-GCM.") == "Stored 1 memory."
    assert "AES-256-GCM" in recall.invoke(query="encrypted")
    assert "encrypted" in reflect.invoke(query="encrypted")


def test_recall_tool_no_hits(store):
    from perseus_vault_haystack import create_perseus_vault_tools

    _, recall, _ = create_perseus_vault_tools(store)
    assert recall.invoke(query="nonexistent-topic") == "No relevant memories found."


def test_tools_reject_bad_store():
    from perseus_vault_haystack import create_perseus_vault_tools

    with pytest.raises(ValueError):
        create_perseus_vault_tools(object())  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Auto-memory wrapper
# --------------------------------------------------------------------------- #
def test_wrapper_recall_injects_and_retain_stores(store):
    from haystack.dataclasses import ChatMessage

    from perseus_vault_haystack import PerseusVaultMemoryWrapper

    store.write_messages([ChatMessage.from_user("Bob works in US/Central timezone.")])

    seen = {}

    class FakeAgent:
        def run(self, messages, **kw):
            seen["system_count"] = sum(1 for m in messages if m.role.value == "system")
            return {"last_message": ChatMessage.from_assistant("Bob is in Central time.")}

    wrapper = PerseusVaultMemoryWrapper(store, auto_recall=True, auto_retain=True)
    res = wrapper.run(FakeAgent(), messages=[ChatMessage.from_user("What timezone is Bob in?")])

    assert seen["system_count"] >= 1  # a memory was injected
    assert res["last_message"].text == "Bob is in Central time."
    # assistant reply was retained
    assert any("Central time" in m.text for m in store.recall_messages("Central time", top_k=10))


def test_wrapper_recall_disabled(store):
    from haystack.dataclasses import ChatMessage

    from perseus_vault_haystack import PerseusVaultMemoryWrapper

    store.write_messages([ChatMessage.from_user("Some stored fact about widgets.")])

    class FakeAgent:
        def run(self, messages, **kw):
            return {
                "system_count": sum(1 for m in messages if m.role.value == "system"),
                "last_message": ChatMessage.from_assistant("ok"),
            }

    wrapper = PerseusVaultMemoryWrapper(store, auto_recall=False, auto_retain=False)
    res = wrapper.run(FakeAgent(), messages=[ChatMessage.from_user("widgets?")])
    assert res["system_count"] == 0


def test_wrapper_rejects_bad_store():
    from perseus_vault_haystack import PerseusVaultMemoryWrapper

    with pytest.raises(ValueError):
        PerseusVaultMemoryWrapper(object())  # type: ignore[arg-type]
