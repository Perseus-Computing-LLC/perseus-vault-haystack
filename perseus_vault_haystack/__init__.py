# SPDX-FileCopyrightText: 2026 Perseus Computing LLC
#
# SPDX-License-Identifier: MIT

"""perseus-vault-haystack — Perseus Vault persistent memory for Haystack 2.x.

Perseus Vault (https://github.com/Perseus-Computing-LLC/perseus-vault) is an
open-source (MIT) local-first, encrypted persistent memory engine with 40+ MCP
tools. This package exposes Perseus Vault to Haystack 2.x pipelines as a memory
store plus two ``@component`` adapters.

Requirements:
    A ``mimir`` binary must be on ``$PATH`` or passed explicitly via
    ``mimir_binary``. Download from:
    https://github.com/Perseus-Computing-LLC/perseus-vault/releases
"""

from .components import PerseusVaultMemoryRetriever, PerseusVaultMemoryWriter
from .memory_store import PerseusVaultMemoryStore

__all__ = [
    "PerseusVaultMemoryStore",
    "PerseusVaultMemoryWriter",
    "PerseusVaultMemoryRetriever",
]

__version__ = "0.1.0"
