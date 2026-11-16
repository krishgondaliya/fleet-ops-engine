"""Local MCP server (stdio) exposing the five read-only agent tools from fleetdata.agent_tools. No new capabilities:
every call goes through agent_tools.run_tool, so argument validation, the fixed parameterized queries, the read-only
connection and the MAX_ROWS cap are the same as on the API path.

One server process serves one question (Claude Code starts it per run). It numbers calls #1, #2, ... exactly like
the API loop and refuses calls beyond --max-calls (default agent.MAX_TOOL_CALLS = 8) with an error result.

Protocol: newline-delimited JSON-RPC 2.0 on stdin/stdout (MCP stdio transport). Implemented by hand to avoid a new
dependency; it supports initialize, ping, tools/list and tools/call. Nothing except protocol messages is written
to stdout.

Usage (normally started by Claude Code via --mcp-config):
  python -m fleetdata.agent_mcp --db data/fleet.duckdb [--max-calls 8]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from fleetdata.agent_tools import TOOL_SCHEMAS, ToolError, run_tool

SERVER_NAME = "fleet"
PROTOCOL_VERSION = "2025-06-18"          # answered when the client does not ask for one


class Server:
    def __init__(self, db_path: pathlib.Path, max_calls: int):
        self.db_path, self.max_calls, self.calls = db_path, max_calls, 0

    def tools(self) -> list[dict]:
        return [{"name": t["name"], "description": t["description"], "inputSchema": t["input_schema"]} for t in TOOL_SCHEMAS]

    def call(self, name: str, args) -> dict:
        if self.calls >= self.max_calls:
            return _text(f"Tool-call limit ({self.max_calls}) reached. Answer now from the results you have.", True)
        self.calls += 1
        n = self.calls
        try:
            if not isinstance(args, dict):
                raise ToolError("arguments must be an object")
            result = run_tool(self.db_path, name, args)
            return _text(json.dumps({"call": f"#{n}", **result}, default=str), False)
        except ToolError as e:
            return _text(f"#{n} error: {e}", True)

    def handle(self, msg: dict) -> dict | None:
        """Return the JSON-RPC response for one message, or None for notifications."""
        method, mid = msg.get("method"), msg.get("id")
        if mid is None:                                  # notification (e.g. notifications/initialized)
            return None
        p = msg.get("params") or {}
        if method == "initialize":
            res = {"protocolVersion": p.get("protocolVersion") or PROTOCOL_VERSION,
                   "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": SERVER_NAME, "version": "1.0"}}
        elif method == "ping":
            res = {}
        elif method == "tools/list":
            res = {"tools": self.tools()}
        elif method == "tools/call":
            res = self.call(p.get("name", ""), p.get("arguments") or {})
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": res}


def _text(text: str, is_error: bool) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def serve(server: Server, inp=None, out=None) -> None:
    inp = inp or sys.stdin.buffer
    out = out or sys.stdout.buffer
    for raw in inp:
        if not raw.strip():
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            resp = server.handle(msg) if isinstance(msg, dict) else None
        if resp is not None:
            out.write(json.dumps(resp).encode("utf-8") + b"\n")
            out.flush()


def main() -> None:
    from fleetdata.agent import MAX_TOOL_CALLS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True, type=pathlib.Path)
    ap.add_argument("--max-calls", type=int, default=MAX_TOOL_CALLS)
    a = ap.parse_args()
    serve(Server(a.db, a.max_calls))


if __name__ == "__main__":
    main()
