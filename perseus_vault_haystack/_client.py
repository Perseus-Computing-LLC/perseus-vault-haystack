# SPDX-FileCopyrightText: 2026 Perseus Computing LLC
#
# SPDX-License-Identifier: MIT

"""Low-level JSON-RPC (MCP stdio) client for the Perseus Vault memory engine.

Perseus Vault (https://github.com/Perseus-Computing-LLC/perseus-vault) is an
open-source (MIT) local-first, encrypted persistent memory engine exposing 40+
MCP tools. It runs as ``mimir serve --db <path>`` and speaks JSON-RPC 2.0 over
stdin/stdout (the MCP stdio transport).

This client spawns the ``mimir`` binary and provides a thin, thread-safe
``call_tool`` method. It is adapted from the proven client core in
``Perseus-Computing-LLC/adk-mimir-memory``.
"""

from __future__ import annotations

import atexit
import json
import os
import queue
import shutil
import subprocess
import threading
import time


class PerseusVaultClient:
    """Thread-safe JSON-RPC client over a ``mimir`` stdio subprocess.

    The client lazily spawns the subprocess on first use (``start``), performs
    the MCP ``initialize`` handshake, and exposes ``call_tool`` to invoke any
    Perseus Vault MCP tool. The subprocess is terminated at interpreter exit.
    """

    def __init__(
        self,
        db_path: str = "~/.mimir/haystack.db",
        mimir_binary: str = "mimir",
        timeout_s: float = 30.0,
    ) -> None:
        """Initialize the client (does not start the subprocess yet).

        :param db_path: Path to the Perseus Vault SQLite database file.
        :param mimir_binary: Name (resolved on ``$PATH``) or absolute path of the
            ``mimir`` executable.
        :param timeout_s: Per-RPC timeout guarding against a hung subprocess.
        """
        self.db_path = os.path.expanduser(db_path)
        self.mimir_binary = mimir_binary
        self.timeout_s = timeout_s

        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._request_id = 0
        self._recv: queue.Queue = queue.Queue()
        self._reader: threading.Thread | None = None
        self._started = False

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def _resolve_binary(self) -> str:
        if os.path.isabs(self.mimir_binary):
            if not os.path.exists(self.mimir_binary):
                msg = f"mimir binary not found at '{self.mimir_binary}'."
                raise RuntimeError(msg)
            return self.mimir_binary
        resolved = shutil.which(self.mimir_binary)
        if resolved is None and os.name == "nt" and not self.mimir_binary.lower().endswith(".exe"):
            # On Windows the binary may be installed without the .exe suffix
            # (shutil.which only matches PATHEXT extensions by default).
            resolved = shutil.which(self.mimir_binary + ".exe")
        if resolved is None:
            msg = (
                f"mimir binary not found on $PATH (looked for '{self.mimir_binary}'). "
                "Install Perseus Vault from "
                "https://github.com/Perseus-Computing-LLC/perseus-vault/releases "
                "or pass an absolute path via mimir_binary=."
            )
            raise RuntimeError(msg)
        return resolved

    def start(self) -> None:
        """Spawn the subprocess and perform the MCP handshake (idempotent)."""
        with self._lock:
            if self._started:
                return
            binary = self._resolve_binary()

            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

            # stderr is discarded: nothing drains it, so a chatty server filling
            # the OS pipe buffer would block on its stderr write while we wait on
            # stdout (a classic two-pipe deadlock).
            self._proc = subprocess.Popen(
                [binary, "serve", "--db", self.db_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )

            proc_stdout = self._proc.stdout

            def _pump() -> None:
                try:
                    for line in proc_stdout:  # type: ignore[union-attr]
                        self._recv.put(line)
                except Exception:  # noqa: BLE001
                    pass
                finally:
                    self._recv.put(None)  # EOF sentinel

            self._reader = threading.Thread(target=_pump, daemon=True)
            self._reader.start()
            self._started = True
            atexit.register(self.close)

        # Handshake (outside the lock; _rpc takes the lock itself).
        self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "perseus-vault-haystack", "version": "0.1.0"},
            },
        )
        self._notify("notifications/initialized", {})

    def close(self) -> None:
        """Terminate the Perseus Vault subprocess."""
        proc = self._proc
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ #
    # JSON-RPC plumbing
    # ------------------------------------------------------------------ #
    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _rpc(self, method: str, params: object) -> dict:
        """Send a JSON-RPC request and return its ``result`` dict."""
        with self._lock:
            if self._proc is None or self._proc.stdin is None:
                msg = "Perseus Vault subprocess is not running. Call start() first."
                raise RuntimeError(msg)
            req_id = self._next_id()
            req = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
            payload = json.dumps(req, default=str)
            try:
                self._proc.stdin.write(payload + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError) as e:
                msg = (
                    f"Perseus Vault subprocess communication failed: {e}. "
                    "The mimir process may have crashed."
                )
                raise RuntimeError(msg) from e

            deadline = time.monotonic() + self.timeout_s
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    msg = f"Perseus Vault RPC '{method}' timed out after {self.timeout_s}s."
                    raise RuntimeError(msg)
                try:
                    raw = self._recv.get(timeout=remaining)
                except queue.Empty:
                    msg = f"Perseus Vault RPC '{method}' timed out after {self.timeout_s}s."
                    raise RuntimeError(msg) from None
                if raw is None:
                    msg = "Perseus Vault subprocess closed its output (it may have crashed)."
                    raise RuntimeError(msg)
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    resp = json.loads(raw)
                except json.JSONDecodeError:
                    continue  # non-JSON noise on stdout
                if resp.get("id") != req_id:
                    continue  # notification or a stale/other reply
                if "error" in resp:
                    err = resp["error"]
                    msg = f"Perseus Vault RPC error [{err.get('code')}]: {err.get('message')}"
                    raise RuntimeError(msg)
                return resp.get("result", {})

    def _notify(self, method: str, params: object) -> None:
        """Send a JSON-RPC notification (no id, no response expected)."""
        with self._lock:
            if self._proc is None or self._proc.stdin is None:
                return
            payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params})
            try:
                self._proc.stdin.write(payload + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Call a Perseus Vault MCP tool and return its ``structuredContent``.

        Falls back to parsing the first text content block if no structured
        content is present.
        """
        if not self._started:
            self.start()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        sc = result.get("structuredContent")
        if sc is not None:
            return sc
        content = result.get("content", [])
        if content:
            try:
                return json.loads(content[0].get("text", "{}"))
            except (json.JSONDecodeError, IndexError, KeyError, AttributeError):
                pass
        return {}
