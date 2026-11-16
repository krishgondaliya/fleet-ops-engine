"""Dock Balance Lab: offline prototype app. Run:  .venv/Scripts/streamlit run app.py

Views: station map (observed snapshot), forecast vs actual (predicted vs observed), policy simulation (simulated),
ask the agent (answers built only from read-only tool results). Every value carries an Observed / Predicted /
Simulated badge. Reads data/fleet.duckdb read-only (override with FLEET_DB).
"""
from __future__ import annotations

import html
import json
import os
import pathlib

import altair as alt
import duckdb
import pandas as pd
import pydeck as pdk
import streamlit as st

from fleetdata import agent as A
from fleetdata.forecast import REGIONS

APP_NAME = "Dock Balance Lab"
DB = pathlib.Path(os.environ.get("FLEET_DB", "data/fleet.duckdb"))
ENV_FILE = os.environ.get("FLEET_ENV_FILE", ".env")
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE = "#2a78d6", "#eb6834"          # validated categorical slots 1-2 (light surface)
BADGE = {"Observed": "gray", "Predicted": "blue", "Simulated": "orange"}
BANNER = ("**Independent analysis of public bike-share data.** Not affiliated with, endorsed by, or operated by the "
          "bike-share operator or its sponsors. Raw data is not redistributed.")


def badge(kind: str):
    st.badge(kind, color=BADGE[kind])


def tag(kind: str) -> str:
    """Badge text for places where a widget badge cannot go (metric labels, tooltips, table columns)."""
    return f"[{kind}]"


def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    return _q(str(DB), sql, params)


@st.cache_data(show_spinner=False)
def _q(db: str, sql: str, params: tuple) -> pd.DataFrame:
    with duckdb.connect(db, read_only=True) as con:
        return con.execute(sql, list(params)).df()


def has_table(name: str) -> bool:
    return bool(q("SELECT count(*) AS n FROM information_schema.tables WHERE table_name = ?", (name,)).n.iloc[0])


# ---------------- views ----------------
def view_map():
    st.subheader("Stations: bikes and docks at the snapshot")
    badge("Observed")
    df = q(f"""SELECT st.short_name, st.name, st.lat, st.lon, st.capacity, st.region_id,
                      sn.num_bikes_available AS bikes, sn.num_docks_available AS docks, sn.num_bikes_disabled AS bikes_disabled,
                      sn.is_installed, sn.is_renting, sn.is_returning, sn.is_stale, sn.fetched_at_utc
               FROM stations st JOIN snapshot sn USING (short_name)
               WHERE st.region_id IN {REGIONS} ORDER BY st.short_name""")
    if df.empty:
        st.warning("No Jersey City / Hoboken stations in the database.")
        return
    installed = df[df.is_installed]
    st.caption(f"One GBFS snapshot fetched {df.fetched_at_utc.iloc[0]:%Y-%m-%d %H:%M} UTC. A single instant, not history. "
               f"{len(df) - len(installed)} station(s) not installed are hidden.")
    c = st.columns(4)
    c[0].metric(f"Stations {tag('Observed')}", f"{len(installed):,}")
    c[1].metric(f"Bikes available {tag('Observed')}", f"{int(installed.bikes.sum()):,}")
    c[2].metric(f"Docks available {tag('Observed')}", f"{int(installed.docks.sum()):,}")
    c[3].metric(f"Empty stations {tag('Observed')}", f"{int((installed.bikes == 0).sum()):,}")
    m = installed.copy()
    m["fill"] = (m.bikes / m.capacity.where(m.capacity > 0)).clip(0, 1).fillna(0)
    # Sequential single hue (blue ramp): lighter = emptier, darker = fuller
    lo, hi = (205, 226, 251), (16, 66, 129)
    m["color"] = [[int(a + (b - a) * f) for a, b in zip(lo, hi)] + [220] for f in m.fill]
    m["radius"] = 25 + m.capacity * 2.5
    m["tip"] = [f"<b>{html.escape(str(r.short_name))}</b> {html.escape(str(r.name))}<br/>"
                f"{tag('Observed')} bikes {r.bikes} · docks {r.docks} · capacity {r.capacity}"
                + ("<br/>stale report" if r.is_stale else "") + ("" if r.is_renting else "<br/>not renting")
                for r in m.itertuples()]
    layer = pdk.Layer("ScatterplotLayer", m[["lon", "lat", "radius", "color", "tip"]], get_position=["lon", "lat"],
                      get_radius="radius", get_fill_color="color", get_line_color=[255, 255, 255], line_width_min_pixels=1,
                      stroked=True, pickable=True)
    st.pydeck_chart(pdk.Deck(layers=[layer], tooltip={"html": "{tip}"},
                             initial_view_state=pdk.ViewState(latitude=m.lat.mean(), longitude=m.lon.mean(), zoom=12.5)))
    st.caption("Circle size = capacity. Color = share of docks holding an available bike (light = empty, dark = full).")
    with st.expander("Table view"):
        t = m[["short_name", "name", "capacity", "bikes", "docks", "bikes_disabled", "is_renting", "is_stale"]]
        st.dataframe(t.rename(columns={"bikes": f"bikes {tag('Observed')}", "docks": f"docks {tag('Observed')}"}),
                     hide_index=True, width="stretch")


def view_forecast():
    st.subheader("Forecast vs actual, October 2026 test month")
    c = st.columns([1, 1])
    with c[0]:
        badge("Predicted")
    with c[1]:
        badge("Observed")
    stations = q("""SELECT DISTINCT p.short_name, coalesce(s.name, '') AS name FROM forecast_predictions p
                    LEFT JOIN stations s USING (short_name) ORDER BY p.short_name""")
    if stations.empty:
        st.warning("No forecasts in the database. Run `python -m fleetdata.forecast`.")
        return
    labels = {r.short_name: f"{r.short_name} · {r.name}" for r in stations.itertuples()}
    default = list(labels).index("JC115") if "JC115" in labels else 0
    a, b, d = st.columns([2, 1, 2])
    sn = a.selectbox("Station", list(labels), index=default, format_func=labels.get)
    target = b.radio("Target", ["departures", "arrivals"], horizontal=True)
    rng = d.date_input("Local dates (Oct 2026)", (pd.Timestamp("2026-10-05").date(), pd.Timestamp("2026-10-11").date()),
                       min_value=pd.Timestamp("2026-10-01").date(), max_value=pd.Timestamp("2026-10-31").date())
    if not isinstance(rng, tuple) or len(rng) != 2:
        st.info("Pick a start and an end date.")
        return
    df = q("""SELECT hour_local, actual, pred_lightgbm, pred_avg_4w, in_eval_set FROM forecast_predictions
              WHERE short_name = ? AND target = ? AND CAST(hour_local AS DATE) BETWEEN ? AND ? ORDER BY hour_local""",
           (sn, target, rng[0], rng[1]))
    show_base = st.checkbox("Also show the 4-week same-hour average baseline", value=False)
    long = df.melt("hour_local", ["actual", "pred_lightgbm"] + (["pred_avg_4w"] if show_base else []), "series", "trips")
    names = {"actual": "Actual (Observed)", "pred_lightgbm": "LightGBM forecast (Predicted)",
             "pred_avg_4w": "4-week average (Predicted baseline)"}
    long["series"] = long.series.map(names)
    domain = [names["actual"], names["pred_lightgbm"]] + ([names["pred_avg_4w"]] if show_base else [])
    colors = [INK2, BLUE] + ([ORANGE] if show_base else [])
    hover = alt.selection_point(fields=["hour_local"], nearest=True, on="pointerover", empty=False)
    base = alt.Chart(long).encode(x=alt.X("hour_local:T", title="Local time (America/New_York)"),
                                  y=alt.Y("trips:Q", title=f"{target.capitalize()} per hour"),
                                  color=alt.Color("series:N", scale=alt.Scale(domain=domain, range=colors),
                                                  legend=alt.Legend(orient="top", title=None)))
    lines = base.mark_line(strokeWidth=2, interpolate="monotone")
    pts = base.mark_point(size=60, filled=True).encode(opacity=alt.condition(hover, alt.value(1), alt.value(0)),
                                                       tooltip=[alt.Tooltip("hour_local:T", format="%a %d %b %H:%M"), "series:N",
                                                                alt.Tooltip("trips:Q", format=".2f")]).add_params(hover)
    rule = alt.Chart(long).mark_rule(color=GRID).encode(x="hour_local:T").transform_filter(hover)
    st.altair_chart((lines + rule + pts).properties(height=340).configure_axis(gridColor=GRID, labelColor=INK2,
                                                                               titleColor=INK2), width="stretch")
    e = df[df.in_eval_set]
    c = st.columns(4)
    c[0].metric(f"Actual total {tag('Observed')}", f"{int(df.actual.sum()):,}")
    c[1].metric(f"LightGBM total {tag('Predicted')}", f"{df.pred_lightgbm.sum():,.1f}")
    c[2].metric(f"LightGBM MAE, range {tag('Predicted')}", f"{(e.actual - e.pred_lightgbm).abs().mean():.3f}" if len(e) else "n/a")
    c[3].metric(f"4-week avg MAE, range {tag('Predicted')}", f"{(e.actual - e.pred_avg_4w).abs().mean():.3f}" if len(e) else "n/a")
    ms = q("SELECT * FROM forecast_metrics_by_station WHERE short_name = ? AND target = ?", (sn, target))
    if not ms.empty:
        r = ms.iloc[0]
        st.caption(f"Whole test month at {sn} {tag('Predicted')}: WAPE LightGBM {r.wape_lightgbm:.3f}, "
                   f"4-week average {r.wape_avg_4w:.3f}, same hour last week {r.wape_last_week:.3f} "
                   f"({int(r.actual_total):,} observed trips).")
    st.caption("Completed trips, not demand: empty or full stations suppress observed trips. Arrivals exclude trips that "
               "started in NYC. Forecasts are issued at local midnight from data through the previous day.")
    with st.expander("Table view"):
        st.dataframe(df.rename(columns={"actual": f"actual {tag('Observed')}", "pred_lightgbm": f"pred_lightgbm {tag('Predicted')}",
                                        "pred_avg_4w": f"pred_avg_4w {tag('Predicted')}"}), hide_index=True, width="stretch")


def view_sim():
    st.subheader("Policy simulation: no action vs greedy truck")
    badge("Simulated")
    if not has_table("sim_summary"):
        st.warning("No simulation results. Run `python -m fleetdata.sim`.")
        return
    meta = json.loads(q("SELECT meta_json FROM sim_meta").meta_json.iloc[0])
    sc, tr = meta["scope"], meta["config"]["truck"]
    st.warning("**Every number on this page is SIMULATED.** One synthetic weekday per seed, demand drawn from the "
               "October forecasts, 30 seeds with identical demand for both policies. These are not observed outcomes "
               "and not evidence about real operations.")
    s = q("SELECT * FROM sim_summary ORDER BY metric").set_index("metric")
    names = {"lost_rentals": "Lost rentals", "failed_returns": "Failed returns", "unserved_total": "Lost + failed"}
    cols = st.columns(3)
    for col, (k, label) in zip(cols, names.items()):
        r = s.loc[k]
        col.metric(f"{label} per day, greedy {tag('Simulated')}", f"{r.mean_greedy:,.1f}",
                   delta=f"{r.mean_diff:+.1f} vs no action (95% CI {r.ci95_lo:+.1f} to {r.ci95_hi:+.1f})", delta_color="inverse")
        col.caption(f"No action: {r.mean_no_action:,.1f} {tag('Simulated')} · greedy better in "
                    f"{int(r.seeds_greedy_better)}/{int(r.n_seeds)} seeds")
    h = q("SELECT policy, hour_local, lost_rentals + failed_returns AS unserved FROM sim_hourly ORDER BY policy, hour_local")
    h["policy"] = h.policy.map({"no_action": "No action", "greedy": "Greedy truck"})
    chart = alt.Chart(h).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X("hour_local:O", title="Local hour"), xOffset="policy:N",
        y=alt.Y("unserved:Q", title="Lost rentals + failed returns (mean per day, SIMULATED)"),
        color=alt.Color("policy:N", scale=alt.Scale(domain=["No action", "Greedy truck"], range=[ORANGE, BLUE]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["policy:N", "hour_local:O", alt.Tooltip("unserved:Q", format=".1f", title="unserved (Simulated)")])
    st.altair_chart(chart.properties(height=300).configure_axis(gridColor=GRID, labelColor=INK2, titleColor=INK2),
                    width="stretch")
    runs = q("""SELECT policy, avg(truck_moves) AS moves, avg(bikes_moved) AS bikes, avg(truck_km) AS km
                FROM sim_runs WHERE policy = 'greedy' GROUP BY policy""")
    if not runs.empty:
        st.caption(f"Greedy truck activity {tag('Simulated')}: {runs.moves.iloc[0]:.1f} moves, {runs.bikes.iloc[0]:.0f} bikes, "
                   f"{runs.km.iloc[0]:.0f} road-km per day (means over seeds).")
    with st.expander("Assumptions (config/sim.json) and start state"):
        st.markdown(f"- Start state {tag('Observed')}: {sc['stations']} installed stations, {sc['start_bikes_clipped']:,} bikes "
                    f"(snapshot {sc['snapshot_fetched_at_utc']} UTC, clipped to capacity), {sc['docks']:,} docks.\n"
                    f"- Demand {tag('Predicted')} → draws {tag('Simulated')}: expected {sc['expected_departures']:.0f} departures and "
                    f"{sc['expected_arrivals']:.0f} arrivals per day.\n"
                    f"- Truck: {tr['count']} truck, {tr['capacity_bikes']} bikes, {tr['moves_per_hour']} move per hour from "
                    f"{tr['operating_hours_local'][0]}:00 to {tr['operating_hours_local'][1]}:00, "
                    f"{tr['travel_budget_km_per_hour']} road-km per hour, target fill {tr['target_fill']}.\n"
                    "- Riders do not carry bikes between stations in this model; a lost rental or failed return is only counted.")
    with st.expander("Table view: per-station means"):
        st.dataframe(q("SELECT * FROM sim_station ORDER BY lost_rentals + failed_returns DESC"), hide_index=True,
                     width="stretch")


def _label_kind(label: str) -> str:
    return "Simulated" if "simulated" in label else ("Predicted" if "predicted" in label else "Observed")


def view_agent():
    st.subheader("Ask the agent")
    st.caption(f"Answers come only from {len(A.TOOL_SCHEMAS)} read-only tools (no free-form SQL), at most "
               f"{A.MAX_TOOL_CALLS} tool calls and {A.TOKEN_CAP:,} tokens per question. Numbers not found in any tool "
               "result are flagged. Calls the Anthropic API (paid).")
    settings = A.load_settings(ENV_FILE)
    with st.form("ask"):
        question = st.text_input("Question", placeholder="e.g. How many departures did JC115 have on 2026-10-05?", max_chars=500)
        go = st.form_submit_button("Ask")
    if go and question.strip():
        if not settings["has_key"]:
            st.error("ANTHROPIC_API_KEY is not set in .env, so the agent cannot run.")
        else:
            import anthropic
            with st.spinner(f"Asking {settings['model']}…"):
                try:
                    st.session_state.setdefault("history", []).insert(
                        0, A.ask(question.strip(), A.make_client(), DB, settings["model"]))
                except anthropic.APIError as e:
                    st.error(f"API call failed ({type(e).__name__}): {getattr(e, 'message', e)}")
    for res in st.session_state.get("history", []):
        with st.container(border=True):
            st.markdown(f"**Q:** {res.question}")
            st.text(res.answer)
            if res.unverified_numbers:
                st.warning("Unverified numbers (not found in any tool result): " + ", ".join(res.unverified_numbers))
            st.caption(f"model {res.model} · stop {res.stop} · {len(res.tool_calls)} tool call(s) · "
                       f"tokens in {res.input_tokens:,} / out {res.output_tokens:,}")
            for c in res.tool_calls:
                kind = _label_kind(c.result["label"]) if c.result else None
                with st.expander(f"[#{c.n}] {c.name}({json.dumps(c.args, sort_keys=True)})"
                                 + (f" {tag(kind)}" if kind else " error")):
                    if c.error:
                        st.error(c.error)
                    else:
                        badge(kind)
                        st.json(c.result, expanded=False)


def main():
    st.set_page_config(page_title=APP_NAME, layout="wide")
    st.title(APP_NAME)
    st.info(BANNER)
    st.caption("Badges: " + " · ".join(f"**{k}** = {v}" for k, v in {
        "Observed": "measured in public data (one snapshot, completed trips)",
        "Predicted": "day-ahead model output",
        "Simulated": "output of the one-day simulator under stated assumptions"}.items()))
    if not DB.exists():
        st.error(f"Database not found at {DB}. Run `python -m fleetdata.build` (and steps 2–3) first.")
        return
    tabs = st.tabs(["Station map", "Forecast vs actual", "Policy simulation", "Ask the agent"])
    for tab, view in zip(tabs, (view_map, view_forecast, view_sim, view_agent)):
        with tab:
            view()


main()
