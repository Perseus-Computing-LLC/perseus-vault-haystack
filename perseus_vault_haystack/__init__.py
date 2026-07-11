# SPDX-FileCopyrightText: 2026 Perseus Computing LLC
#
# SPDX-License-Identifier: MIT

"""perseus-vault-haystack — Perseus Vault persistent memory for Haystack 2.x.

Perseus Vault (https://github.com/Perseus-Computing-LLC/perseus-vault) is an
open-source (MIT) local-first, encrypted persistent memory engine with 40+ MCP
tools. This package exposes Perseus Vault to Haystack 2.x as:

- a memory store (``PerseusVaultMemoryStore``) with both ``Document`` and
  ``ChatMessage`` read/write APIs,
- pipeline components (``PerseusVaultMemoryWriter`` / ``PerseusVaultMemoryRetriever``),
- ready-made Agent tools (``create_perseus_vault_tools`` → retain / recall / reflect),
- an automatic recall-and-retain wrapper (``PerseusVaultMemoryWrapper``).

Everything runs against a local, encrypted database with no API keys and no
external vector store.

Requirements:
    A ``perseus-vault`` binary must be on ``$PATH`` or passed explicitly via
    ``perseus_vault_binary``. Download from:
    https://github.com/Perseus-Computing-LLC/perseus-vault/releases
"""

from .components import PerseusVaultMemoryRetriever, PerseusVaultMemoryWriter
from .memory_store import PerseusVaultMemoryStore
from .tools import create_perseus_vault_tools
from .wrapper import PerseusVaultMemoryWrapper

__all__ = [
    "PerseusVaultMemoryStore",
    "PerseusVaultMemoryWriter",
    "PerseusVaultMemoryRetriever",
    "create_perseus_vault_tools",
    "PerseusVaultMemoryWrapper",
]

__version__ = "0.2.0"
