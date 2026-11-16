"""claude_code backend for the investigation agent: runs the Claude Code CLI non-interactively, once per question,
under the user's logged-in Claude subscription instead of an API key. LOCAL USE ONLY (see README).

Per question it starts `claude -p` (flags checked against `claude --help` and the CLI reference for v2.1.325):
  --output-format stream-json --verbose     machine-readable event stream (stream-json in -p mode needs --verbose)
  --mcp-config <file> --strict-mcp-config   only the local fleet MCP server (fleetdata.agent_mcp), no other MCP servers
  --tools ""                                no built-in tools at all (file, shell, web, ...)
  --disallowedTools <built-ins>             belt and braces: deny the built-in tools by name too
  --allowedTools mcp__fleet__<tool> ...     the five read-only tools run without a permission prompt
  --permission-mode dontAsk                 anything not pre-allowed is denied, never prompted
  --max-turns MAX_TOOL_CALLS + 1            8 tool-call turns plus the answer; the MCP server also refuses call 9+
  --system-prompt-file                      the same SYSTEM prompt as the API path
  --setting-sources ""                      no user/project/local settings files (no hooks, no permission rules)
  --no-session-persistence, --model, --effort medium
The question goes in on stdin and the run happens in an empty temporary directory, so no project CLAUDE.md or
.claude/ settings are picked up. The child gets a copy of the environment WITHOUT ANTHROPIC_API_KEY (and without
ANTHROPIC_AUTH_TOKEN and this session's CLAUDE_CODE_* linkage), so it authenticates with the subscription login. The
init event's apiKeySource is recorded and anything other than "none" is treated as an error.

The answer gets the same number check and code-built tool-call list as the API path (agent.check_numbers,
AgentResult.full_answer).
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from fleetdata import agent as A
from fleetdata.agent_mcp import SERVER_NAME
from fleetdata.agent_tools import TOOL_SCHEMAS

PREFIX = f"mcp__{SERVER_NAME}__"
ALLOWED_TOOLS = [PREFIX + t["name"] for t in TOOL_SCHEMAS]
BUILTIN_TOOLS = ["Bash", "PowerShell", "Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "Glob", "Grep", "LS",
                 "WebFetch", "WebSearch", "Agent", "Task", "TodoWrite", "Skill", "SlashCommand", "ToolSearch", "Monitor"]
ALWAYS_PRESENT = {"EndConversation"}          # per the CLI reference, --tools "" cannot remove it while MCP tools remain
# Variables removed from the child environment: the API key (so the subscription login is used) and the variables
# that link a process to a parent Claude Code session.
STRIP_ENV = {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT",
             "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_MESSAGING_SOCKET",
             "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_ENTRYPOINT",
             "CLAUDE_CODE_EXECPATH"}
TIMEOUT_S = 300


class ClaudeCodeError(RuntimeError):
    """The Claude Code run failed before producing an answer (CLI missing, not logged in, crash, timeout)."""


# ---------------- command and environment ----------------
def find_cli() -> str:
    """CLAUDE_CLI overrides. On Windows the npm shim is a .cmd; prefer the native claude.exe it wraps so arguments
    are not re-parsed by cmd.exe."""
    if os.environ.get("CLAUDE_CLI"):
        return os.environ["CLAUDE_CLI"]
    path = shutil.which("claude")
    if not path:
        raise ClaudeCodeError("the claude CLI was not found on PATH (install Claude Code or set CLAUDE_CLI)")
    p = pathlib.Path(path)
    if p.suffix.lower() in (".cmd", ".bat", ".ps1"):
        exe = p.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        if exe.exists():
            return str(exe)
    return path


def clean_env(env: dict | None = None) -> dict:
    env = dict(os.environ if env is None else env)
    for k in STRIP_ENV:
        env.pop(k, None)
    return env


def mcp_config(db_path: pathlib.Path, max_calls: int) -> dict:
    repo = pathlib.Path(__file__).resolve().parents[1]
    return {"mcpServers": {SERVER_NAME: {
        "type": "stdio", "command": sys.executable,
        "args": ["-m", "fleetdata.agent_mcp", "--db", str(pathlib.Path(db_path).resolve()), "--max-calls", str(max_calls)],
        "env": {"PYTHONPATH": str(repo)}}}}


def build_command(cli: str, model: str, mcp_file: pathlib.Path, prompt_file: pathlib.Path, max_tool_calls: int) -> list[str]:
    return [cli, "-p", "--output-format", "stream-json", "--verbose",
            "--model", model, "--effort", "medium",
            "--mcp-config", str(mcp_file), "--strict-mcp-config",
            "--tools", "",
            "--disallowedTools", ",".join(BUILTIN_TOOLS),
            "--allowedTools", ",".join(ALLOWED_TOOLS),
            "--permission-mode", "dontAsk",
            "--max-turns", str(max_tool_calls + 1),
            "--system-prompt-file", str(prompt_file),
            "--setting-sources", "",
            "--no-session-persistence"]


# ---------------- output parsing ----------------
def _result_text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(c.get("text", "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text")


def parse_stream(lines, max_tool_calls: int = A.MAX_TOOL_CALLS) -> dict:
    """Parse stream-json lines into tool calls, final answer and run metadata. Pure: no process, no network."""
    events = []
    for ln in lines:
        ln = ln.strip()
        if ln:
            try:
                events.append(json.loads(ln))
            except json.JSONDecodeError:
                continue                                  # tolerate stray non-JSON lines
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), {})
    uses: dict[str, A.ToolCall] = {}
    order: list[str] = []
    texts: list[str] = []
    for e in events:
        msg = e.get("message") or {}
        if e.get("type") == "assistant":
            for b in msg.get("content") or []:
                if b.get("type") == "tool_use":
                    uses[b["id"]] = A.ToolCall(0, b.get("name", ""), b.get("input") if isinstance(b.get("input"), dict)
                                               else {"_raw": str(b.get("input"))})
                    order.append(b["id"])
                elif b.get("type") == "text" and b.get("text", "").strip():
                    texts.append(b["text"].strip())
        elif e.get("type") == "user" and isinstance(msg.get("content"), list):
            for b in msg["content"]:
                if b.get("type") != "tool_result" or b.get("tool_use_id") not in uses:
                    continue
                c, text = uses[b["tool_use_id"]], _result_text(b.get("content"))
                if b.get("is_error"):
                    c.error = text or "tool error"
                    continue
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    c.error = f"unparseable tool result: {text[:200]}"
                    continue
                data.pop("call", None)
                c.result = data
    calls: list[A.ToolCall] = []
    for tid in order:                                     # number like the API loop; drop calls the server refused
        c = uses[tid]
        if c.error and "Tool-call limit" in c.error:
            continue
        c.n = len(calls) + 1
        c.name = c.name[len(PREFIX):] if c.name.startswith(PREFIX) else c.name
        calls.append(c)
    res = next((e for e in reversed(events) if e.get("type") == "result"), None)
    usage = (res or {}).get("usage") or {}
    return {
        "init_tools": init.get("tools", []), "api_key_source": init.get("apiKeySource"), "model": init.get("model"),
        "mcp_servers": init.get("mcp_servers", []), "calls": calls, "last_text": texts[-1] if texts else "",
        "result": res,
        "input_tokens": sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                             "cache_read_input_tokens")),
        "output_tokens": int(usage.get("output_tokens") or 0),
    }


_KEEP = {"system": ("type", "subtype", "tools", "apiKeySource", "model", "mcp_servers", "permissionMode"),
         "assistant": ("type", "message"), "user": ("type", "message"),
         "result": ("type", "subtype", "is_error", "num_turns", "result", "usage", "errors")}


def sanitize_stream(text: str) -> str:
    """Reduce a stream-json transcript to the fields parse_stream reads, for recording test fixtures: drops session
    ids, uuids, working directory and machine details."""
    out = []
    for ln in text.splitlines():
        try:
            e = json.loads(ln)
        except json.JSONDecodeError:
            continue
        keep = _KEEP.get(e.get("type"))
        if not keep or (e["type"] == "system" and e.get("subtype") != "init"):
            continue
        e = {k: e[k] for k in keep if k in e}
        if "message" in e:
            e["message"] = {"role": e["message"].get("role"), "content": e["message"].get("content")}
        if "usage" in e:
            e["usage"] = {k: e["usage"].get(k) for k in ("input_tokens", "cache_creation_input_tokens",
                                                          "cache_read_input_tokens", "output_tokens")}
        out.append(json.dumps(e))
    return "\n".join(out) + "\n"


def to_result(question: str, parsed: dict, model: str) -> A.AgentResult:
    res = parsed["result"]
    if res is None:
        raise ClaudeCodeError("Claude Code produced no result event")
    unexpected = [t for t in parsed["init_tools"] if t not in ALLOWED_TOOLS and t not in ALWAYS_PRESENT]
    if unexpected:
        raise ClaudeCodeError(f"refusing the run: tools other than the fleet MCP tools were available: {unexpected}")
    if parsed["api_key_source"] not in (None, "none"):
        raise ClaudeCodeError(f"refusing the run: Claude Code used an API key ({parsed['api_key_source']}), not the subscription")
    sub = res.get("subtype")
    if sub == "success" and not res.get("is_error"):
        stop, answer = ("tool_limit" if len(parsed["calls"]) >= A.MAX_TOOL_CALLS else "end_turn"), (res.get("result") or "").strip()
    elif sub == "error_max_turns":
        stop, answer = "turn_limit", parsed["last_text"] or "Stopped: the turn limit was reached before an answer."
    else:
        raise ClaudeCodeError(f"Claude Code run failed ({sub}): {str(res.get('result') or res.get('errors') or '')[:300]}")
    r = A.AgentResult(question, answer or "(no answer text)", parsed["calls"], parsed.get("model") or model, stop,
                      parsed["input_tokens"], parsed["output_tokens"], backend="claude_code")
    r.unverified_numbers = A.check_numbers(r.answer, r.tool_calls)
    return r


# ---------------- run ----------------
def ask(question: str, db_path: pathlib.Path = pathlib.Path("data/fleet.duckdb"), model: str = A.DEFAULT_MODEL,
        max_tool_calls: int = A.MAX_TOOL_CALLS, timeout: int = TIMEOUT_S, record_to: pathlib.Path | None = None) -> A.AgentResult:
    cli = find_cli()
    with tempfile.TemporaryDirectory(prefix="fleet_cc_") as tmp:
        tmp = pathlib.Path(tmp)
        (tmp / "mcp.json").write_text(json.dumps(mcp_config(db_path, max_tool_calls)), encoding="utf-8")
        (tmp / "system.txt").write_text(A.SYSTEM, encoding="utf-8")
        cmd = build_command(cli, model, tmp / "mcp.json", tmp / "system.txt", max_tool_calls)
        try:
            p = subprocess.run(cmd, input=question, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               cwd=tmp, env=clean_env(), timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ClaudeCodeError(f"Claude Code did not finish within {timeout} s")
        except OSError as e:
            raise ClaudeCodeError(f"could not start the claude CLI: {e}")
    lines = p.stdout.splitlines()
    if record_to:
        record_to.write_text(sanitize_stream(p.stdout), encoding="utf-8")
    parsed = parse_stream(lines, max_tool_calls)
    if parsed["result"] is None:
        raise ClaudeCodeError(f"Claude Code exited with code {p.returncode}: {(p.stderr or p.stdout).strip()[-400:]}")
    return to_result(question, parsed, model)


def describe_error(e: Exception) -> str:
    """Short plain-language message for a failed Claude Code run."""
    msg = str(e).lower()
    if "not found on path" in msg or "could not start" in msg:
        return "The Claude Code CLI was not found. Install it or set CLAUDE_CLI."
    if "login" in msg or "logged in" in msg or "authenticat" in msg:
        return "Claude Code is not logged in. Run `claude` once and log in with your subscription."
    if "usage limit" in msg or "rate limit" in msg:
        return "The Claude subscription usage limit was reached. Try again later."
    if "did not finish" in msg:
        return "Claude Code took too long to answer."
    if "refusing the run" in msg:
        return "The Claude Code run was stopped because its setup was not the locked-down one this app expects."
    return "The Claude Code run failed."
