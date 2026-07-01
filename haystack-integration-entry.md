---
layout: integration
name: Mimir
description: Add local-first, encrypted, persistent memory to your Haystack agents and pipelines with Mimir
authors:
    - name: Perseus Computing LLC
      socials:
        github: Perseus-Computing-LLC
pypi: https://pypi.org/project/mimir-haystack/
repo: https://github.com/Perseus-Computing-LLC/mimir-haystack
type: Memory Store
report_issue: https://github.com/Perseus-Computing-LLC/mimir-haystack/issues
logo: /logos/mimir.png
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

[Mneme](https://github.com/Perseus-Computing-LLC/mneme) is an open-source (MIT), local-first, encrypted persistent memory engine with 40+ tools exposed over the Model Context Protocol (MCP). It runs entirely on your machine and stores data in an encrypted SQLite database — no external vector database or API key required.

The `mimir-haystack` package provides:

- `MimirMemoryStore`: A persistent memory store backed by a local Mneme engine.
- `MimirMemoryWriter`: A component that persists `Document`s into the store.
- `MimirMemoryRetriever`: A component that retrieves the most relevant `Document`s for a query.

## Installation

```bash
pip install mimir-haystack
```

You also need the `mimir` binary on your `$PATH` (download from the [Mneme releases page](https://github.com/Perseus-Computing-LLC/mneme/releases)).

## Usage

### Available Classes

- `MimirMemoryStore` — owns the `mimir` subprocess and configuration.
- `MimirMemoryWriter` — pipeline sink that writes documents to memory.
- `MimirMemoryRetriever` — pipeline source that recalls documents by query.

### Use in a Pipeline

```python
from haystack import Pipeline, Document
from mimir_haystack import MimirMemoryStore, MimirMemoryWriter, MimirMemoryRetriever

store = MimirMemoryStore(db_path="~/.mimir/haystack.db", category="docs")

write_pipe = Pipeline()
write_pipe.add_component("writer", MimirMemoryWriter(memory_store=store))
write_pipe.run({"writer": {"documents": [Document(content="Mneme is local-first.")]}})

read_pipe = Pipeline()
read_pipe.add_component("retriever", MimirMemoryRetriever(memory_store=store, top_k=3))
result = read_pipe.run({"retriever": {"query": "What is Mneme?"}})
print(result["retriever"]["documents"])
```

## License

`mimir-haystack` is distributed under the terms of the [MIT license](https://opensource.org/licenses/MIT).
