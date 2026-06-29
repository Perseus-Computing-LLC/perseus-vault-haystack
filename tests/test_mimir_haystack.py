# SPDX-FileCopyrightText: 2026 Perseus Computing LLC
#
# SPDX-License-Identifier: MIT

"""Unit tests for mimir-haystack.

The Mimir subprocess is mocked at the ``MimirClient`` boundary so these tests
run without the ``mimir`` binary installed.
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

from mimir_haystack import (
    MimirMemoryRetriever,
    MimirMemoryStore,
    MimirMemoryWriter,
)


class FakeMimirClient:
    """In-memory stand-in for MimirClient.call_tool.

    Implements just enough of mimir_remember / mimir_recall / mimir_forget to
    exercise the store end-to-end without a subprocess.
    """

    def __init__(self, *args, **kwargs):
        self.store = {}  # key -> body_json
        self.calls = []

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "mimir_remember":
            self.store[arguments["key"]] = arguments["body_json"]
            return {"ok": True}
        if name == "mimir_recall":
            query = arguments.get("query", "").lower()
            limit = arguments.get("limit", 10)
            items = []
            for key, body_json in self.store.items():
                body = json.loads(body_json)
                if query in body.get("content", "").lower():
                    items.append({"key": key, "body_json": body_json, "score": 0.9})
            return {"items": items[:limit]}
        if name == "mimir_forget":
            self.store.clear()
            return {"ok": True}
        return {}


@pytest.fixture
def store(monkeypatch):
    """A MimirMemoryStore whose client is the in-memory fake."""
    fake = FakeMimirClient()
    s = MimirMemoryStore(db_path="/tmp/test.db", category="test")
    monkeypatch.setattr(s, "_client", fake)
    return s


# --------------------------------------------------------------------------- #
# MimirMemoryStore
# --------------------------------------------------------------------------- #
def test_add_and_search(store):
    written = store.add_memories(
        [
            Document(content="Mimir is a local-first memory engine."),
            Document(content="Haystack is an LLM framework."),
        ]
    )
    assert written == 2

    hits = store.search_memories("mimir")
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
    s = MimirMemoryStore(
        db_path="/x/y.db", mimir_binary="/opt/mimir", category="c", top_k=7, timeout_s=12.0
    )
    d = s.to_dict()
    assert d["init_parameters"]["category"] == "c"
    assert d["init_parameters"]["top_k"] == 7
    s2 = MimirMemoryStore.from_dict(d)
    assert s2.db_path == "/x/y.db"
    assert s2.mimir_binary == "/opt/mimir"
    assert s2.category == "c"
    assert s2.top_k == 7
    assert s2.timeout_s == 12.0


# --------------------------------------------------------------------------- #
# MimirMemoryWriter
# --------------------------------------------------------------------------- #
def test_writer_run(store):
    writer = MimirMemoryWriter(memory_store=store)
    docs = [Document(content="written via component")]
    out = writer.run(documents=docs)
    assert out["documents_written"] == 1
    assert out["documents"] == docs
    # confirm it actually landed in the store
    assert store.search_memories("written")[0].content == "written via component"


def test_writer_output_types(store):
    sockets = _output_sockets(MimirMemoryWriter(memory_store=store))
    assert sockets["documents"] == list[Document]
    assert sockets["documents_written"] is int


def test_writer_rejects_bad_store():
    with pytest.raises(ValueError):
        MimirMemoryWriter(memory_store=object())


def test_writer_to_dict_from_dict():
    s = MimirMemoryStore(category="w")
    writer = MimirMemoryWriter(memory_store=s)
    d = writer.to_dict()
    assert d["type"].endswith("MimirMemoryWriter")
    assert d["init_parameters"]["memory_store"]["init_parameters"]["category"] == "w"
    writer2 = MimirMemoryWriter.from_dict(d)
    assert isinstance(writer2._memory_store, MimirMemoryStore)
    assert writer2._memory_store.category == "w"


# --------------------------------------------------------------------------- #
# MimirMemoryRetriever
# --------------------------------------------------------------------------- #
def test_retriever_run(store):
    store.add_memories([Document(content="findable content here")])
    retriever = MimirMemoryRetriever(memory_store=store)
    out = retriever.run(query="findable")
    assert len(out["documents"]) == 1
    assert out["documents"][0].content == "findable content here"


def test_retriever_output_types(store):
    sockets = _output_sockets(MimirMemoryRetriever(memory_store=store))
    assert sockets["documents"] == list[Document]


def test_retriever_top_k_precedence(store):
    store.add_memories([Document(content=f"match {i}") for i in range(5)])
    # init top_k=2, call override=1 -> override wins
    retriever = MimirMemoryRetriever(memory_store=store, top_k=2)
    assert len(retriever.run(query="match", top_k=1)["documents"]) == 1
    # no override -> init top_k=2
    assert len(retriever.run(query="match")["documents"]) == 2


def test_retriever_rejects_bad_store():
    with pytest.raises(ValueError):
        MimirMemoryRetriever(memory_store=object())


def test_retriever_to_dict_from_dict():
    s = MimirMemoryStore(category="r")
    retriever = MimirMemoryRetriever(memory_store=s, top_k=3)
    d = retriever.to_dict()
    assert d["init_parameters"]["top_k"] == 3
    retriever2 = MimirMemoryRetriever.from_dict(d)
    assert isinstance(retriever2._memory_store, MimirMemoryStore)
    assert retriever2._top_k == 3


# --------------------------------------------------------------------------- #
# Pipeline integration (serialization round-trip through a real Pipeline)
# --------------------------------------------------------------------------- #
def test_components_in_pipeline_dumps_loads():
    from haystack import Pipeline

    s = MimirMemoryStore(category="pipe")
    pipe = Pipeline()
    pipe.add_component("writer", MimirMemoryWriter(memory_store=s))
    pipe.add_component("retriever", MimirMemoryRetriever(memory_store=s))
    yaml_str = pipe.dumps()
    assert "MimirMemoryWriter" in yaml_str
    assert "MimirMemoryRetriever" in yaml_str
    restored = Pipeline.loads(yaml_str)
    assert restored.get_component("writer") is not None
    assert restored.get_component("retriever") is not None


# --------------------------------------------------------------------------- #
# Client binary resolution (no subprocess spawned)
# --------------------------------------------------------------------------- #
def test_client_missing_binary_raises():
    from mimir_haystack._client import MimirClient

    c = MimirClient(mimir_binary="definitely-not-a-real-binary-xyz")
    with pytest.raises(RuntimeError, match="mimir binary not found"):
        c.start()


# --------------------------------------------------------------------------- #
# Real-binary smoke test (skipped automatically when no mimir binary is found)
# --------------------------------------------------------------------------- #
def _resolve_real_mimir():
    """Locate a real mimir binary, honoring MIMIR_BINARY override."""
    import os
    import shutil

    explicit = os.environ.get("MIMIR_BINARY")
    if explicit and os.path.exists(explicit):
        return explicit
    found = shutil.which("mimir") or shutil.which("mimir.exe")
    return found


@pytest.mark.skipif(_resolve_real_mimir() is None, reason="mimir binary not available")
def test_real_roundtrip(tmp_path):
    """End-to-end write+recall against a real mimir subprocess."""
    binary = _resolve_real_mimir()
    s = MimirMemoryStore(
        db_path=str(tmp_path / "real.db"),
        mimir_binary=binary,
        category="pytest-smoke",
        timeout_s=20,
    )
    written = s.add_memories(
        [Document(id="r1", content="Mimir provides persistent memory.", meta={"k": "v"})]
    )
    assert written == 1
    hits = s.search_memories("persistent memory", top_k=5)
    assert any(h.content == "Mimir provides persistent memory." for h in hits)
    s._client.close()
