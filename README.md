# perseus-vault-haystack

Local-first, encrypted **persistent memory for [Haystack](https://haystack.deepset.ai/) 2.x pipelines**, backed by [Perseus Vault](https://github.com/Perseus-Computing-LLC/perseus-vault) (formerly "Mimir"/"Mneme").

Perseus Vault is an open-source (MIT) memory engine that runs entirely on your machine, stores data in an encrypted SQLite database, and exposes 40+ tools over the Model Context Protocol (MCP). This package wraps Perseus Vault's `remember` / `recall` / `forget` tools as Haystack components so your pipelines can persist and retrieve documents across runs — no external vector database or API key required.

## Components

| Class | Type | Role |
| --- | --- | --- |
| `PerseusVaultMemoryStore` | Memory store | Owns the `perseus-vault` subprocess and config; holds `add_memories` / `search_memories` / `delete_all_memories`. |
| `PerseusVaultMemoryWriter` | `@component` | Pipeline sink that persists `Document`s into the store. |
| `PerseusVaultMemoryRetriever` | `@component` | Pipeline source that retrieves the most relevant `Document`s for a query. |

## Prerequisite: the `perseus-vault` binary

These components talk to a local `perseus-vault` executable over stdio. Install it first:

1. Download a pre-built binary from the [Perseus Vault releases page](https://github.com/Perseus-Computing-LLC/perseus-vault/releases) (or build from source).
2. Put it on your `$PATH` (so `perseus-vault` resolves), **or** pass its absolute path via `perseus_vault_binary=`.

You can verify it works with:

```bash
perseus-vault --version
```

## Install

```bash
pip install perseus-vault-haystack
```

This pulls in `haystack-ai`. The `perseus-vault` binary is a separate, language-agnostic dependency (see above).

## Quickstart — write then read in a pipeline

```python
from haystack import Pipeline, Document
from perseus_vault_haystack import (
    PerseusVaultMemoryStore,
    PerseusVaultMemoryWriter,
    PerseusVaultMemoryRetriever,
)

# One store, shared by both components (single perseus-vault subprocess).
store = PerseusVaultMemoryStore(db_path="~/.mimir/haystack.db", category="docs")

# --- Write documents into persistent memory ---
write_pipe = Pipeline()
write_pipe.add_component("writer", PerseusVaultMemoryWriter(memory_store=store))
write_pipe.run(
    {
        "writer": {
            "documents": [
                Document(content="Perseus Vault is a local-first, encrypted memory engine."),
                Document(content="Haystack is an open-source LLM framework by deepset."),
            ]
        }
    }
)

# --- Retrieve them later (even in a separate process / run) ---
read_pipe = Pipeline()
read_pipe.add_component("retriever", PerseusVaultMemoryRetriever(memory_store=store, top_k=3))
result = read_pipe.run({"retriever": {"query": "What is Perseus Vault?"}})

for doc in result["retriever"]["documents"]:
    print(doc.score, doc.content)
```

Because Perseus Vault persists to an encrypted SQLite file, documents written in one run are available in any future run pointed at the same `db_path`.

### Use directly (without a pipeline)

```python
from haystack import Document
from perseus_vault_haystack import PerseusVaultMemoryStore

store = PerseusVaultMemoryStore(db_path="~/.mimir/haystack.db")
store.add_memories([Document(content="Remember this fact.")])
hits = store.search_memories("fact", top_k=5)
```

## Configuration

`PerseusVaultMemoryStore` accepts:

- `db_path` — path to the Perseus Vault SQLite database (default `~/.mimir/haystack.db`).
- `perseus_vault_binary` — name on `$PATH` or absolute path to the executable (default `perseus-vault`).
- `category` — Perseus Vault category scoping all writes/recalls for this store (default `haystack-memory`). Use distinct categories to isolate corpora.
- `top_k` — default number of documents returned by retrieval (default `10`).
- `timeout_s` — per-RPC timeout for the subprocess (default `30`).

## Serialization

All three classes implement `to_dict()` / `from_dict()` and round-trip through `Pipeline.dumps()` / `Pipeline.loads()`.

## License

MIT © 2026 Perseus Computing LLC. Perseus Vault (formerly Mimir/Mneme) is also MIT-licensed.
