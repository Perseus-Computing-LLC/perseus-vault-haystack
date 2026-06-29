# SPDX-FileCopyrightText: 2026 Perseus Computing LLC
#
# SPDX-License-Identifier: MIT

"""mimir-haystack — Mimir persistent memory for Haystack 2.x.

Mimir (https://github.com/Perseus-Computing-LLC/mimir) is an open-source (MIT)
local-first, encrypted persistent memory engine with 40+ MCP tools. This package
exposes Mimir to Haystack 2.x pipelines as a memory store plus two
``@component`` adapters.

Requirements:
    A ``mimir`` binary must be on ``$PATH`` or passed explicitly via
    ``mimir_binary``. Download from:
    https://github.com/Perseus-Computing-LLC/mimir/releases
"""

from .components import MimirMemoryRetriever, MimirMemoryWriter
from .memory_store import MimirMemoryStore

__all__ = [
    "MimirMemoryStore",
    "MimirMemoryWriter",
    "MimirMemoryRetriever",
]

__version__ = "0.1.0"
