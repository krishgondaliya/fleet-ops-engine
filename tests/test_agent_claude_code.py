"""Offline tests for the claude_code backend: the local MCP server (in-process and as a real stdio subprocess), the
command line and child environment, and stream-json parsing.

Recorded output: tests/fixtures/claude_code/*.jsonl are REAL Claude Code stream-json transcripts from the live eval
on 2026-11-16 (real data/fleet.duckdb), reduced by agent_claude_code.sanitize_stream to the fields the parser reads.
Streams built inline in this file are SYNTHETIC and say so. No test starts the Claude Code CLI (conftest points
CLAUDE_CLI at a path that does not exist).
"""
import io
import json
import pathlib
import subprocess
import sys

import pytest

from fleetdata import agent as A
from fleetdata import agent_claude_code as C
from fleetdata import agent_mcp as M
from fleetdata import agent_tools as T

REC = pathlib.Path(__file__).parent / "fixtures" / "claude_code"


# ---------------- MCP server ----------------
def _req(method, params=None, mid=1):
    return {"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}}


def test_mcp_lists_exactly_the_five_tools_with_same_schemas(fixture_db):
    s = M.Server(fixture_db, 8)
    init = s.handle(_req("initialize", {"protocolVersion": "2025-06-18"}))["result"]
    assert init["protocolVersion"] == "2025-06-18" and "tools" in init["capabilities"]
    assert s.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    tools = s.handle(_req("tools/list"))["result"]["tools"]
    assert [t["name"] for t in tools] == [t["name"] for t in T.TOOL_SCHEMAS]
    assert all(t["inputSchema"] == x["input_schema"] for t, x in zip(tools, T.TOOL_SCHEMAS))


def test_mcp_call_returns_the_same_result_as_run_tool(fixture_db):
    s = M.Server(fixture_db, 8)
    args = {"short_name": "JC115", "start_date": "2026-10-01", "end_date": "2026-10-02"}
    r = s.handle(_req("tools/call", {"name": "hourly_flow", "arguments": args}))["result"]
    assert r["isError"] is False
    got = json.loads(r["content"][0]["text"])
    assert got.pop("call") == "#1"
    assert got == json.loads(json.dumps(T.run_tool(fixture_db, "hourly_flow", args), default=str))


@pytest.mark.parametrize("name,args,msg", [
    ("hourly_flow", {"short_name": "JC115'; DROP TABLE trips; --", "start_date": "2026-10-01", "end_date": "2026-10-02"}, "short_name"),
    ("hourly_flow", {"short_name": "JC115", "start_date": "2026-10-01", "end_date": "2026-10-02", "sql": "x"}, "unknown argument"),
    ("run_sql", {"q": "select 1"}, "unknown tool"),
    ("station_lookup", "not-an-object", "must be an object"),
])
def test_mcp_reuses_validation(fixture_db, name, args, msg):
    r = M.Server(fixture_db, 8).handle(_req("tools/call", {"name": name, "arguments": args}))["result"]
    assert r["isError"] is True and msg in r["content"][0]["text"]


def test_mcp_enforces_the_call_limit_and_unknown_methods(fixture_db):
    s = M.Server(fixture_db, 2)
    call = _req("tools/call", {"name": "station_lookup", "arguments": {"query": "JC115"}})
    assert [s.handle(call)["result"]["isError"] for _ in range(3)] == [False, False, True]
    assert "Tool-call limit (2)" in s.handle(call)["result"]["content"][0]["text"]
    assert s.handle(_req("resources/list"))["error"]["code"] == -32601


def test_mcp_serve_loop_newline_json(fixture_db):
    inp = io.BytesIO(b"\n".join(json.dumps(m).encode() for m in [
        _req("initialize", {}, 1), {"jsonrpc": "2.0", "method": "notifications/initialized"},
        _req("tools/list", {}, 2)]) + b"\nnot json\n")
    out = io.BytesIO()
    M.serve(M.Server(fixture_db, 8), inp, out)
    resp = [json.loads(x) for x in out.getvalue().splitlines()]
    assert [r.get("id") for r in resp] == [1, 2, None] and resp[2]["error"]["code"] == -32700


def test_mcp_server_runs_as_a_stdio_subprocess(fixture_db):
    """The real transport: start the module the way Claude Code does and talk JSON-RPC over pipes (local only)."""
    cfg = C.mcp_config(fixture_db, 8)["mcpServers"]["fleet"]
    msgs = [_req("initialize", {"protocolVersion": "2025-06-18"}, 1), {"jsonrpc": "2.0", "method": "notifications/initialized"},
            _req("tools/call", {"name": "station_lookup", "arguments": {"query": "JC115"}}, 2)]
    p = subprocess.run([cfg["command"], *cfg["args"]], input="\n".join(map(json.dumps, msgs)) + "\n",
                       capture_output=True, text=True, timeout=60, env={**C.clean_env(), **cfg["env"]})
    resp = [json.loads(x) for x in p.stdout.splitlines()]
    assert p.returncode == 0 and [r["id"] for r in resp] == [1, 2]
    assert json.loads(resp[1]["result"]["content"][0]["text"])["rows"][0]["short_name"] == "JC115"


# ---------------- command line and environment ----------------
def test_command_locks_down_tools_and_uses_documented_flags(tmp_path):
    cmd = C.build_command("claude", "claude-sonnet-5-5", tmp_path / "m.json", tmp_path / "s.txt", 8)

    def val(flag):
        return cmd[cmd.index(flag) + 1]
    assert cmd[1] == "-p" and val("--output-format") == "stream-json" and "--verbose" in cmd
    assert val("--tools") == "" and "--strict-mcp-config" in cmd and val("--permission-mode") == "dontAsk"
    assert val("--allowedTools").split(",") == [f"mcp__fleet__{t['name']}" for t in T.TOOL_SCHEMAS]
    assert {"Bash", "PowerShell", "Read", "Write", "Edit", "WebFetch", "WebSearch"} <= set(val("--disallowedTools").split(","))
    assert val("--max-turns") == "9" and val("--setting-sources") == "" and "--no-session-persistence" in cmd
    assert all(isinstance(x, str) for x in cmd)


def test_child_environment_has_no_api_key():
    env = C.clean_env({"ANTHROPIC_API_KEY": "sk-test-not-real", "ANTHROPIC_AUTH_TOKEN": "t", "CLAUDECODE": "1",
                       "PATH": "/bin", "CLAUDE_CODE_OAUTH_TOKEN": "keep"})
    assert env == {"PATH": "/bin", "CLAUDE_CODE_OAUTH_TOKEN": "keep"}


def test_ask_runs_cli_in_temp_dir_without_key(monkeypatch, tmp_path):
    """subprocess.run is replaced: checks what would be launched and feeds back a RECORDED transcript."""
    seen = {}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("CLAUDE_CLI", "claude-test")

    def fake_run(cmd, **kw):
        seen.update(cmd=cmd, **kw)
        seen["mcp"] = json.loads(pathlib.Path(cmd[cmd.index("--mcp-config") + 1]).read_text(encoding="utf-8"))
        seen["system"] = pathlib.Path(cmd[cmd.index("--system-prompt-file") + 1]).read_text(encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, (REC / "Q2.jsonl").read_text(encoding="utf-8"), "")
    monkeypatch.setattr(C.subprocess, "run", fake_run)
    r = C.ask("How many trips started at JC115 on 2026-10-05?", tmp_path / "x.duckdb", "claude-sonnet-5-5")
    assert "ANTHROPIC_API_KEY" not in seen["env"] and seen["input"].startswith("How many trips")
    assert seen["cmd"][0] == "claude-test" and pathlib.Path(seen["cwd"]).name.startswith("fleet_cc_")
    assert seen["system"] == A.SYSTEM and list(seen["mcp"]["mcpServers"]) == ["fleet"]
    assert r.backend == "claude_code" and r.tool_calls


def test_missing_cli_is_a_clear_error():
    with pytest.raises(C.ClaudeCodeError, match="could not start"):
        C.ask("q")                                   # conftest points CLAUDE_CLI at a path that does not exist


# ---------------- parsing RECORDED output ----------------
def _rec(name):
    return (REC / name).read_text(encoding="utf-8").splitlines()


def test_parse_recorded_single_call():
    p = C.parse_stream(_rec("Q2.jsonl"))
    assert p["api_key_source"] == "none" and sorted(p["init_tools"]) == sorted(C.ALLOWED_TOOLS)
    assert [c.name for c in p["calls"]] == ["hourly_flow"] and p["calls"][0].n == 1
    assert p["calls"][0].result["totals"]["departures"] == 178 and "call" not in p["calls"][0].result
    r = C.to_result("q", p, "m")
    assert r.stop == "end_turn" and "178" in r.answer and not r.unverified_numbers
    assert "[#1] hourly_flow(" in r.full_answer()


def test_parse_recorded_forecast_call():
    p = C.parse_stream(_rec("Q6.jsonl"))
    r = C.to_result("q", p, "m")
    assert len(r.tool_calls) >= 1 and [c.n for c in r.tool_calls] == list(range(1, len(r.tool_calls) + 1))
    assert all(c.result is not None or c.error for c in r.tool_calls)
    assert r.stop == "end_turn" and r.unverified_numbers == A.check_numbers(r.answer, r.tool_calls)


def test_parse_recorded_unsupported_question():
    r = C.to_result("q", C.parse_stream(_rec("Q10.jsonl")), "m")
    assert r.answer.startswith(A.UNSUPPORTED_PREFIX)


# ---------------- SYNTHETIC streams for the edge cases ----------------
def _init(tools=None, key="none"):
    return {"type": "system", "subtype": "init", "tools": tools or C.ALLOWED_TOOLS, "apiKeySource": key, "model": "m"}


def _use(tid, name, args):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": tid, "name": "mcp__fleet__" + name, "input": args}]}}


def _res(tid, text, err=False):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "is_error": err,
                                                     "content": [{"type": "text", "text": text}]}]}}


def _done(text, sub="success"):
    return {"type": "result", "subtype": sub, "is_error": sub != "success", "result": text,
            "usage": {"input_tokens": 10, "cache_read_input_tokens": 5, "output_tokens": 3}}


def _lines(*events):
    return [json.dumps(e) for e in events] + ["not json"]


def test_synthetic_number_check_errors_and_refused_calls():
    ok = json.dumps({"call": "#1", "tool": "hourly_flow", "args": {"x": 4321}, "label": "observed", "totals": {"departures": 178}})
    lines = _lines(_init(), _use("a", "hourly_flow", {"x": 4321}), _res("a", ok),
                   _use("b", "hourly_flow", {"short_name": "bad"}), _res("b", "#2 error: short_name is invalid", True),
                   _use("c", "station_lookup", {}), _res("c", "Tool-call limit (8) reached. Answer now.", True),
                   _done("178 departures [#1], not 4321."))
    r = C.to_result("q", C.parse_stream(lines), "m")
    assert [(c.n, c.name, bool(c.error)) for c in r.tool_calls] == [(1, "hourly_flow", False), (2, "hourly_flow", True)]
    assert r.unverified_numbers == ["4321"] and r.input_tokens == 15 and r.output_tokens == 3
    assert "Unverified numbers" in r.full_answer() and "[#2] hourly_flow" in r.full_answer()


def test_synthetic_turn_limit_and_failures():
    r = C.to_result("q", C.parse_stream(_lines(_init(), {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "partial"}]}}, _done(None, "error_max_turns"))), "m")
    assert r.stop == "turn_limit" and r.answer == "partial"
    with pytest.raises(C.ClaudeCodeError, match="tools other than"):
        C.to_result("q", C.parse_stream(_lines(_init(C.ALLOWED_TOOLS + ["Bash"]), _done("x"))), "m")
    with pytest.raises(C.ClaudeCodeError, match="API key"):
        C.to_result("q", C.parse_stream(_lines(_init(key="ANTHROPIC_API_KEY"), _done("x"))), "m")
    with pytest.raises(C.ClaudeCodeError, match="error_during_execution"):
        C.to_result("q", C.parse_stream(_lines(_init(), _done("boom", "error_during_execution"))), "m")
    with pytest.raises(C.ClaudeCodeError, match="no result"):
        C.to_result("q", C.parse_stream(_lines(_init())), "m")
    # EndConversation cannot be removed while MCP tools exist (CLI reference); it is tolerated
    assert C.to_result("q", C.parse_stream(_lines(_init(C.ALLOWED_TOOLS + ["EndConversation"]), _done("ok"))), "m").answer == "ok"


def test_sanitize_keeps_only_parser_fields():
    raw = "\n".join(json.dumps(e) for e in [
        {**_init(), "cwd": "C:/Users/someone/tmp", "session_id": "abc", "slash_commands": ["x"]},
        {"type": "system", "subtype": "hook_started", "x": 1}, {"type": "rate_limit_event"},
        {**_use("a", "hourly_flow", {}), "session_id": "abc", "uuid": "u"}, _done("ok")])
    out = C.sanitize_stream(raw)
    assert "someone" not in out and "session_id" not in out and "uuid" not in out and "rate_limit" not in out
    assert C.to_result("q", C.parse_stream(out.splitlines()), "m").answer == "ok"


# ---------------- backend selection ----------------
def test_backend_setting_and_dispatch(tmp_path, monkeypatch):
    for k in ("AGENT_BACKEND", "AGENT_MODEL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    s = A.load_settings(tmp_path / "missing.env")
    assert s["backend"] == "claude_code" and A.DEFAULT_BACKEND == "claude_code"
    monkeypatch.setenv("AGENT_BACKEND", "gpt")
    with pytest.raises(ValueError, match="AGENT_BACKEND"):
        A.load_settings(tmp_path / "missing.env")
    seen = {}
    monkeypatch.setattr(C, "ask", lambda q, db, model: seen.update(q=q, model=model) or "cc-result")
    assert A.answer("q?", {"backend": "claude_code", "model": "m", "has_key": False}) == "cc-result" and seen["model"] == "m"
    with pytest.raises(A.MissingKeyError):
        A.answer("q?", {"backend": "api", "model": "m", "has_key": False})


def test_describe_claude_code_errors():
    assert C.describe_error(C.ClaudeCodeError("exit 1: Not logged in · Please run /login")).startswith("Claude Code is not logged in")
    assert C.describe_error(C.ClaudeCodeError("could not start the claude CLI: x")).startswith("The Claude Code CLI was not found")
    assert C.describe_error(C.ClaudeCodeError("weird")) == "The Claude Code run failed."
