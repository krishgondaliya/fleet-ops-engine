"""Offline smoke tests for the Streamlit app (app.py) using streamlit's AppTest, against the fixture DB
(REAL 10-station GBFS subset + SYNTHETIC trips/forecasts + SIMULATED sim_* tables). No API calls."""
import pathlib

import pytest
from streamlit.testing.v1 import AppTest

APP = str(pathlib.Path(__file__).parents[1] / "app.py")


@pytest.fixture
def app(fixture_db, tmp_path, monkeypatch):
    monkeypatch.setenv("FLEET_DB", str(fixture_db))
    monkeypatch.setenv("FLEET_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("AGENT_BACKEND", "api")
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    return at


def texts(at) -> str:
    parts = [e.value for kind in ("markdown", "caption", "info", "warning", "error", "subheader", "title") for e in getattr(at, kind)]
    parts += [m.label for m in at.metric]
    return "\n".join(map(str, parts))


def test_renders_four_views_without_errors(app):
    assert not app.exception
    assert [t.label for t in app.tabs] == ["Station map", "Forecast vs actual", "Policy simulation", "Ask the agent"]
    assert app.title[0].value == "Dock Balance Lab"


def test_banner_and_no_operator_brand(app):
    assert "not affiliated" in app.info[0].value.lower()
    allt = texts(app).lower()
    assert "citi" not in allt and "lyft" not in allt


def test_every_metric_is_badged(app):
    assert app.metric, "expected metrics"
    for m in app.metric:
        assert any(k in m.label for k in ("[Observed]", "[Predicted]", "[Simulated]")), m.label


def test_simulation_view_is_labeled_simulated(app):
    assert "Every number on this page is SIMULATED" in texts(app)
    assert any("[Simulated]" in m.label for m in app.metric)


def test_agent_without_key_explains_instead_of_calling(app):
    app.text_input[0].input("How many departures did JC115 have on 2026-10-01?")
    app.button[0].click()
    app.run()
    assert not app.exception
    assert any("ANTHROPIC_API_KEY is not set" in e.value for e in app.error)


def test_map_counts_empty_and_full_stations(app):
    labels = [m.label for m in app.metric]
    assert any(l.startswith("Empty stations") for l in labels) and any(l.startswith("Full stations") for l in labels)


def test_map_scale_and_view_fit():
    import pandas as pd
    # The helpers are pure; load them without running the Streamlit script body.
    src = (pathlib.Path(APP).read_text(encoding="utf-8")).rsplit("\nmain()", 1)[0]
    ns: dict = {}
    exec(compile(src, APP, "exec"), ns)
    assert ns["fill_rgb"](0) == list(ns["EMPTY_RGB"]) and ns["fill_rgb"](1) == list(ns["FULL_RGB"])
    assert ns["fill_rgb"](0.5) == list(ns["MID_RGB"])
    v = ns["fit_view"](pd.Series([40.70, 40.76]), pd.Series([-74.09, -74.02]))
    assert 11.5 < v.zoom < 13.5 and abs(v.longitude + 74.055) < 1e-9


def test_agent_api_failure_shows_plain_message_and_collapsed_details(fixture_db, tmp_path, monkeypatch):
    import anthropic
    from fleetdata import agent as A
    from tests._api_errors import api_error

    def fail(*a, **k):
        raise api_error(anthropic.BadRequestError, "Your credit balance is too low to access the Anthropic API.")

    monkeypatch.setenv("FLEET_DB", str(fixture_db))
    monkeypatch.setenv("FLEET_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("AGENT_BACKEND", "api")
    monkeypatch.setattr(A, "make_client", lambda: object())
    monkeypatch.setattr(A, "ask", fail)
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.text_input[0].input("How many departures did JC115 have on 2026-10-01?")
    at.button[0].click()
    at.run()
    assert not at.exception
    assert [e.value for e in at.error] == ["The API account has no credit. Add credit, then ask again."]
    details = [x for x in at.expander if x.label == "Error details"]
    assert details and "credit balance is too low" in details[0].code[0].value


def _cc_app(fixture_db, tmp_path, monkeypatch, fake_ask):
    from fleetdata import agent_claude_code as CC
    monkeypatch.setenv("FLEET_DB", str(fixture_db))
    monkeypatch.setenv("FLEET_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("AGENT_BACKEND", "claude_code")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(CC, "ask", fake_ask)
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.text_input[0].input("How many departures did JC115 have on 2026-10-01?")
    at.button[0].click()
    at.run()
    return at


def test_agent_claude_code_backend_needs_no_key_and_shows_backend(fixture_db, tmp_path, monkeypatch):
    from fleetdata import agent as A
    fake = lambda q, db, model: A.AgentResult(q, "Observed: 5 departures [#1].", [], model, "end_turn", backend="claude_code")
    at = _cc_app(fixture_db, tmp_path, monkeypatch, fake)
    assert not at.exception and not at.error
    assert any("Backend: **claude_code**" in c.value for c in at.caption)
    assert any("answered by backend **claude_code**" in c.value for c in at.caption)


def test_agent_claude_code_failure_shows_plain_message(fixture_db, tmp_path, monkeypatch):
    from fleetdata import agent_claude_code as CC

    def fail(q, db, model):
        raise CC.ClaudeCodeError("Claude Code exited with code 1: Not logged in · Please run /login")
    at = _cc_app(fixture_db, tmp_path, monkeypatch, fail)
    assert not at.exception
    assert [e.value for e in at.error] == ["Claude Code is not logged in. Run `claude` once and log in with your subscription."]
    assert "Not logged in" in [x for x in at.expander if x.label == "Error details"][0].code[0].value
