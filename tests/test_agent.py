"""Offline tests for the agent tools, the tool-use loop (with a SCRIPTED client, no API calls) and the eval grader.

Database: the REAL 10-station GBFS fixture (stations, snapshot) + SYNTHETIC trips, plus SYNTHETIC demand_grid,
forecast and metrics tables (fixture_db in conftest.py). The simulator is run on it to produce sim_* tables (SIMULATED).
"""
import pathlib

import duckdb
import pytest

from fleetdata import agent as A
from fleetdata import agent_eval as E
from fleetdata import agent_tools as T



@pytest.fixture
def db(fixture_db):
    return fixture_db


# ---------------- tools ----------------
def test_station_lookup_by_id_and_name(db):
    r = T.run_tool(db, "station_lookup", {"query": "jc115"})
    assert r["label"] == "observed" and r["rows"][0]["short_name"] == "JC115"
    assert "station_name_untrusted_text" in r["rows"][0]


def test_like_wildcards_are_literal(db):
    assert T.run_tool(db, "station_lookup", {"query": "%"})["row_count"] == 0
    assert T.run_tool(db, "station_lookup", {"query": "_"})["row_count"] == 0


@pytest.mark.parametrize("name,args,msg", [
    ("hourly_flow", {"short_name": "JC115'; DROP TABLE trips; --", "start_date": "2026-10-01", "end_date": "2026-10-02"}, "short_name"),
    ("hourly_flow", {"short_name": "JC115", "start_date": "2026-09-01", "end_date": "2026-10-15"}, "limited to 31 days"),
    ("hourly_flow", {"short_name": "JC115", "start_date": "2026-10-05", "end_date": "2026-10-01"}, "before"),
    ("hourly_flow", {"short_name": "JC115", "start_date": "05/10/2026", "end_date": "2026-10-06"}, "YYYY-MM-DD"),
    ("hourly_flow", {"short_name": "JC115", "start_date": "2026-10-01", "end_date": "2026-10-02", "sql": "x"}, "unknown argument"),
    ("hourly_flow", {"short_name": "JC999", "start_date": "2026-10-01", "end_date": "2026-10-02"}, "no trip data"),
    ("forecast_vs_actual", {"short_name": "JC115", "start_date": "2026-09-10", "end_date": "2026-09-11"}, "within"),
    ("model_metrics", {"view": "everything"}, "must be one of"),
    ("simulation_results", {"policy": "send_trucks"}, "must be one of"),
    ("station_lookup", {"query": "x" * 61}, "1-60"),
    ("station_lookup", {}, "missing required"),
    ("run_sql", {"q": "select 1"}, "unknown tool"),
])
def test_invalid_arguments_are_rejected(db, name, args, msg):
    with pytest.raises(T.ToolError, match=msg):
        T.run_tool(db, name, args)


def test_hourly_flow_totals_and_row_cap(db):
    r = T.run_tool(db, "hourly_flow", {"short_name": "JC115", "start_date": "2026-10-01", "end_date": "2026-10-31",
                                       "granularity": "hour"})
    assert r["row_count"] == T.MAX_ROWS and r["truncated"] is True
    assert r["totals"]["hours_covered"] == 31 * 24
    with duckdb.connect(str(db), read_only=True) as con:
        exp = con.execute("""SELECT sum(departures) FROM demand_grid WHERE short_name = 'JC115'
                             AND hour_local >= '2026-10-01'""").fetchone()[0]
    assert r["totals"]["departures"] == exp


def test_forecast_vs_actual_and_metrics_and_sim(db):
    r = T.run_tool(db, "forecast_vs_actual", {"short_name": "JC115", "start_date": "2026-10-01", "end_date": "2026-10-01"})
    assert r["totals"]["pred_lightgbm_total"] == 48.0 and r["totals"]["hours"] == 24
    m = T.run_tool(db, "model_metrics", {"view": "overall", "target": "arrivals"})
    assert {x["target"] for x in m["rows"]} == {"arrivals"}
    s = T.run_tool(db, "simulation_results", {"view": "summary"})
    assert s["label"] == "simulated" and {x["metric"] for x in s["rows"]} == {"lost_rentals", "failed_returns", "unserved_total"}
    assert "SIMULATED" in s["note"]


def test_tools_open_the_database_read_only(db, monkeypatch):
    seen = {}
    real = duckdb.connect
    monkeypatch.setattr(T.duckdb, "connect", lambda p, **kw: seen.update(kw) or real(p, **kw))
    T.run_tool(db, "station_lookup", {"query": "JC115"})
    assert seen == {"read_only": True}


# ---------------- loop (SCRIPTED client; no network) ----------------
def test_loop_runs_tools_and_appends_call_list(db):
    c = E.ScriptedClient([[("station_lookup", {"query": "JC115"})]],
                         answer=lambda r: f"Observed: {r[0]['rows'][0]['num_bikes_available']} bikes [#1].")
    r = A.ask("bikes at JC115?", c, db)
    assert r.stop == "end_turn" and len(r.tool_calls) == 1 and not r.unverified_numbers
    assert "Tool calls used:" in r.full_answer() and "[#1] station_lookup" in r.full_answer()


def test_tool_call_limit_is_enforced(db):
    steps = [[("station_lookup", {"query": "JC115"})]] * 12
    c = E.ScriptedClient(steps, answer="done")
    r = A.ask("q", c, db)
    assert len(r.tool_calls) == A.MAX_TOOL_CALLS == 8 and r.stop == "tool_limit"
    assert c.calls[-1]["tool_choice"] == {"type": "none"}


def test_parallel_calls_beyond_limit_get_error_results(db):
    c = E.ScriptedClient([[("station_lookup", {"query": "JC115"})] * 10], answer="done")
    r = A.ask("q", c, db)
    assert len(r.tool_calls) == 8
    results = c.calls[-1]["messages"][-1]["content"]
    assert len(results) == 10 and sum(x["is_error"] for x in results) == 2


def test_token_cap_stops_the_loop(db):
    c = E.ScriptedClient([[("station_lookup", {"query": "JC115"})]] * 5, answer="done", input_tokens=30_000)
    r = A.ask("q", c, db, token_cap=50_000)
    assert r.stop == "token_cap" and len(c.calls) == 2


def test_tool_errors_are_returned_to_the_model(db):
    c = E.ScriptedClient([[("hourly_flow", {"short_name": "bad"})]], answer="Not supported by the data: x")
    r = A.ask("q", c, db)
    assert r.tool_calls[0].error and c.calls[1]["messages"][-1]["content"][0]["is_error"] is True


def test_unverified_numbers_are_flagged(db):
    c = E.ScriptedClient([[("station_lookup", {"query": "JC115"})]], answer="There were 987654 bikes [#1] on 2026-10-01.")
    r = A.ask("q", c, db)
    assert r.unverified_numbers == ["987654"] and "Unverified numbers" in r.full_answer()


def test_number_check_rejects_laundered_args_errors_and_wrong_signs(db):
    """Audit cases: numbers the model put in its own arguments, or in a failed call, are not evidence;
    a signed number must match the sign of the tool value."""
    c = E.ScriptedClient([[("station_lookup", {"query": "4321"})]], answer="JC115 had 4321 departures [#1].")
    assert A.ask("q", c, db).unverified_numbers == ["4321"]
    c = E.ScriptedClient([[("hourly_flow", {"short_name": "JC115", "start_date": "2026-10-01", "end_date": "9999"})]],
                         answer="There were 9999 departures.")
    assert A.ask("q", c, db).unverified_numbers == ["9999"]
    calls = [A.ToolCall(1, "x", {}, {"rows": [{"departures": 178}], "totals": {"a": 120, "b": 58}})]
    assert A.check_numbers("-178 departures", calls) == ["-178"]
    assert A.check_numbers("178 departures", calls) == []


def test_number_check_accepts_rounding_percent_and_simple_sums():
    calls = [A.ToolCall(1, "x", {}, {"a": 0.62004, "b": 120, "c": 58, "s": "2026-10-07 17:00:00", "d": -26.8})]
    assert A.check_numbers("WAPE 0.62, or 62%; total 178; hour 17; JC115 [#1]", calls) == []
    assert A.check_numbers("WAPE 0.7", calls) == ["0.7"]
    assert A.check_numbers("a change of -26.8, i.e. 26.8 fewer", calls) == []
    assert A.check_numbers("year 2026", calls) == ["2026"]      # dates are not split into evidence


def test_refusal_is_reported_not_answered(db):
    class Refuser(E.ScriptedClient):
        def _create(self, **kw):
            return E._block(content=[], stop_reason="refusal", usage=self.usage)
    r = A.ask("q", Refuser([]), db)
    assert r.stop == "refusal" and r.tool_calls == []


def test_settings_report_key_presence_only(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=sk-test-not-real\n", encoding="utf-8")
    s = A.load_settings(env)
    assert s == {"model": "claude-sonnet-5-5", "has_key": True}


# ---------------- grader ----------------
@pytest.mark.parametrize("expected,tok,ok", [
    (178, "178", True), (178, "177", False), (0.838, "0.84", True), (0.838, "0.838", True), (0.838, "1", False),
    (0.4249, "42.5", True), (159.86, "159.9", True), (159.86, "160", True), (-39.97, "-40.0", True), (235.97, "236", True),
])
def test_grader_matching(expected, tok, ok):
    assert E.matches(expected, tok) is ok


def test_grader_signs_and_number_dumps():
    assert not E.matches(39.97, "-40.0") and E.matches(-39.97, "-40.0") and E.matches(-39.97, "40.0")
    q = {"id": "Q2"}
    assert not E.grade(q, " ".join(str(i) for i in range(300)), [178.0])[0]


def test_grader_unsupported_requires_prefix():
    q = {"unsupported": True}
    assert E.grade(q, f"{A.UNSUPPORTED_PREFIX} no status history.", None)[0]
    assert not E.grade(q, "About 12 rentals were lost.", None)[0]


def test_describe_api_error_is_short_and_plain():
    import anthropic
    from tests._api_errors import api_error
    assert A.describe_api_error(api_error(anthropic.BadRequestError, "Your credit balance is too low")).startswith(
        "The API account has no credit")
    assert A.describe_api_error(api_error(anthropic.AuthenticationError, "invalid x-api-key")).startswith(
        "The API key was rejected")
    assert A.describe_api_error(api_error(anthropic.APIConnectionError, "Connection error.")).startswith(
        "Could not reach the API")
