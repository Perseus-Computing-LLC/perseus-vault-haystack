---
layout: integration
name: Perseus Vault
description: Add local-first, encrypted, persistent memory to your Haystack agents and pipelines with Perseus Vault
authors:
    - name: Perseus Computing LLC
      socials:
        github: Perseus-Computing-LLC
pypi: https://pypi.org/project/perseus-vault-haystack/
repo: https://github.com/Perseus-Computing-LLC/mimir-haystack
type: Memory Store
report_issue: https://github.com/Perseus-Computing-LLC/mimir-haystack/issues
logo: /logos/perseus-vault.png
version: Haystack 2.0
toc: true
---

### **Table of Contents**

- [Overview](#overview)
- [Installation](#installation)
- [Usage](#usage)
  - [Available Classes](#available-classes)
  - [Use in a Pipeline](#use-in-a-pipeline)
- [License](#license)

## Overview

[Perseus Vault](https://github.com/Perseus-Computing-LLC/perseus-vault) is an open-source (MIT), local-first, encrypted persistent memory engine with 40+ tools exposed over the Model Context Protocol (MCP). It runs entirely on your machine and stores data in an encrypted SQLite database — no external vector database or API key required.

The `perseus-vault-haystack` package provides:

- `PerseusVaultMemoryStore`: A persistent memory store backed by a local Perseus Vault engine.
- `PerseusVaultMemoryWriter`: A component that persists `Document`s into the store.
- `PerseusVaultMemoryRetriever`: A component that retrieves the most relevant `Document`s for a query.

## Installation

```bash
pip install perseus-vault-haystack
```

You also need the `perseus-vault` binary on your `$PATH` (download from the [Perseus Vault releases page](https://github.com/Perseus-Computing-LLC/perseus-vault/releases)).

## Usage

### Available Classes

- `PerseusVaultMemoryStore` — owns the `perseus-vault` subprocess and configuration.
- `PerseusVaultMemoryWriter` — pipeline sink that writes documents to memory.
- `PerseusVaultMemoryRetriever` — pipeline source that recalls documents by query.

### Use in a Pipeline

```python
from haystack import Pipeline, Document
from perseus_vault_haystack import (
    PerseusVaultMemoryStore,
    PerseusVaultMemoryWriter,
    PerseusVaultMemoryRetriever,
)

store = PerseusVaultMemoryStore(db_path="~/.mimir/haystack.db", category="docs")

write_pipe = Pipeline()
write_pipe.add_component("writer", PerseusVaultMemoryWriter(memory_store=store))
write_pipe.run({"writer": {"documents": [Document(content="Perseus Vault is local-first.")]}})

read_pipe = Pipeline()
read_pipe.add_component("retriever", PerseusVaultMemoryRetriever(memory_store=store, top_k=3))
result = read_pipe.run({"retriever": {"query": "What is Perseus Vault?"}})
print(result["retriever"]["documents"])
```

## License

`perseus-vault-haystack` is distributed under the terms of the [MIT license](https://opensource.org/licenses/MIT).
