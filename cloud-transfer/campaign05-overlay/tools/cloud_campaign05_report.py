"""Publish an aggregate, self-contained dashboard for the 100 oracle-student trials."""
from __future__ import annotations

import html
import json
from pathlib import Path

import numpy as np

from tools.cloud_campaign05 import MANIFEST, OUT, PLAN, PROPOSALS
from tools.mnq_oracle_prepare import sha256
from tools.mnq_oracle_research import save_json

ROOT = Path("/workspace")
SUMMARY = ROOT / "outputs/mnq_campaign05_summary.json"
PAGE = ROOT / "outputs/mnq_oracle_teaching_dashboard.html"
PRIVATE_PAGE = ROOT / "outputs/mnq_oracle_teaching_dashboard_PRIVATE.html"


def aggregate() -> dict:
    manifest = json.loads(MANIFEST.read_text())
    if sha256(PLAN) != manifest["plan_sha256"]:
        raise ValueError("Campaign plan changed")
    families, all_variants = [], []
    for index in range(1, 11):
        path = OUT / f"test_{index:02d}.json"
        audit = OUT / f"test_{index:02d}_audit.json"
        if not path.exists() or not audit.exists():
            raise ValueError(f"Tester {index:02d} result or audit missing")
        proposal_path = PROPOSALS / f"search_{index:02d}.json"
        if sha256(proposal_path) != manifest["proposals"][proposal_path.name]:
            raise ValueError("Frozen proposal changed")
        proposal = json.loads(proposal_path.read_text())
        result = json.loads(path.read_text())
        if (result["status"] != "complete_selection_only" or len(result["variants"]) != 10
                or result["proposal_sha256"] != sha256(proposal_path)
                or result["plan_sha256"] != manifest["plan_sha256"]
                or result["runner_sha256"] != manifest["runner_sha256"]
                or result["holdout_opened"] or result["sealed_2025_access"] or result["broker_orders"]):
            raise ValueError(f"Tester {index:02d} incomplete or lineage mismatch")
        if not isinstance(json.loads(audit.read_text()), dict):
            raise TypeError("Tester audit invalid")
        variants = []
        for j, row in enumerate(result["variants"]):
            if row["id"] != f"v{j:02d}" or len(row["fold_rank_scores"]) != 3:
                raise ValueError("Tester variant coverage differs from frozen proposal")
            scores = np.asarray(row["fold_rank_scores"], float)
            if not np.isfinite(scores).all() or not np.isclose(scores.mean(), row["mean_rank_score"]):
                raise ValueError("Invalid tester rank score")
            item = {"searcher": index, "variant": j, "model": proposal["variants"][j]["model"],
                    "features": proposal["variants"][j]["features"],
                    "fold_rank_scores": scores.tolist(), "mean_rank_score": float(scores.mean()),
                    "oracle_positive_fraction_by_fold": row["oracle_positive_fraction_by_fold"],
                    "oracle_imitation_fraction_by_fold": row["oracle_imitation_fraction_by_fold"],
                    "student_signal_fraction_by_fold": row["student_signal_fraction_by_fold"],
                    "current_paper_api_feature_parity": row["current_paper_api_feature_parity"],
                    "rank_gate_pass": bool(np.all(scores > 0) and scores.mean() > .05)}
            variants.append(item)
            all_variants.append(item)
        best = max(variants, key=lambda row: (row["mean_rank_score"], -row["variant"]))
        families.append({"id": index, "hypothesis": proposal["hypothesis"],
                         "best_variant": best, "gate_pass_count": sum(v["rank_gate_pass"] for v in variants),
                         "paper_api_parity_count": sum(v["current_paper_api_feature_parity"] for v in variants),
                         "fold_rows": result["fold_rows"]})
    if len(all_variants) != 100:
        raise ValueError("Expected exactly 100 tested variants")
    eligible = [v for v in all_variants if v["rank_gate_pass"]]
    selected = max(eligible, key=lambda v: (v["mean_rank_score"], -v["searcher"], -v["variant"])) if eligible else None
    holdout_path = OUT / "internal_holdout.json"
    holdout = None
    if holdout_path.exists():
        private = json.loads(holdout_path.read_text())
        holdout = {key: private[key] for key in (
            "status", "selected_searcher", "selected_variant", "selected_model", "training_rows",
            "holdout_ready_mature_opportunities", "holdout_rank_score", "oracle_positive_fraction",
            "student_signal_fraction", "oracle_action_imitation_fraction",
            "selected_opportunity_robust_net_mean_usd", "signals", "holdout_is_confirmation",
            "paper_api_feature_parity", "live_authorized", "broker_orders", "sealed_2025_access")}
        holdout["evaluations"] = [
            {"delay": row["delay"], "cost": row["cost"],
             "metrics": {key: row["metrics"][key] for key in (
                 "trades", "net", "expectancy", "win_rate", "max_drawdown_bar_close",
                 "gap_unresolved_trades")},
             "gap_exit_net_usd": row["gap_exit_net_usd"],
             "session_bootstrap": row.get("session_bootstrap")}
            for row in private["evaluations"]]
    return {"status": "selection_complete", "tested_variants": 100, "search_agents": 10, "test_agents": 10,
            "rank_gate_pass_count": len(eligible), "selected": selected,
            "internal_holdout": holdout,
            "method": "Eight hindsight robust action values (long/short x 3/5/10/20 bars), each scored at the worse of immediate and one-bar-delayed fill after $6 stress cost. Future bars are labels only. Three purged chronological selection folds; one global winner may be tested once on an internal opened holdout.",
            "limitations": ["Yahoo contract/roll/timestamp identity unverified", "All 2026 windows are development evidence",
                            "No paper feed or broker order is running", "No agreed finite maximum drawdown"],
            "families": families, "variants": all_variants}


def render(report: dict, trace: dict | None = None) -> str:
    esc = lambda value: html.escape(str(value))
    selected = report["selected"]
    holdout = report["internal_holdout"]
    card = (f'<strong>{selected["mean_rank_score"]:.3f}</strong><span>Best selection rank score</span>'
            if selected else '<strong>None</strong><span>Passed the selection gate</span>')
    holdout_text = ("Not run yet" if holdout is None else esc(holdout.get("status", "completed")))
    outcome_text = ("Profitability has not yet been replayed." if holdout is None else
                    "The one-time holdout lost money under stressed immediate and delayed fills.")
    holdout_cards = ""
    if holdout is not None:
        immediate = next(e for e in holdout["evaluations"] if e["delay"] == 0 and e["cost"] == "stress")
        delayed = next(e for e in holdout["evaluations"] if e["delay"] == 1 and e["cost"] == "stress")
        holdout_cards = (f'<div class="grid"><div class="card"><strong>${immediate["metrics"]["net"]:,.2f}</strong><span>Holdout stress net · immediate</span></div>'
                         f'<div class="card"><strong>${delayed["metrics"]["net"]:,.2f}</strong><span>Holdout stress net · one-bar delay</span></div>'
                         f'<div class="card"><strong>{immediate["metrics"]["trades"]}</strong><span>Filled holdout trades</span></div>'
                         f'<div class="card"><strong>{holdout["holdout_rank_score"]:+.3f}</strong><span>Holdout action-value rank</span></div>'
                         f'<div class="card"><strong>{holdout["oracle_positive_fraction"]:.1%}</strong><span>Hindsight oracle positive choice</span></div>'
                         f'<div class="card"><strong>{holdout["oracle_action_imitation_fraction"]:.1%}</strong><span>Student exactly matched oracle</span></div></div>')
    brain_html = ""
    if trace is not None:
        action_labels = ["long · 3 bars", "short · 3 bars", "long · 5 bars", "short · 5 bars",
                         "long · 10 bars", "short · 10 bars", "long · 20 bars", "short · 20 bars"]
        forecast_rows = ''.join(f'<tr><td>{label}</td><td>${pred:+.2f}</td><td>${actual:+.2f}</td></tr>'
                                for label, pred, actual in zip(action_labels, trace["predicted_stress_net_usd"],
                                                                trace["realized_oracle_stress_net_usd_after_maturity"]))
        contribution_rows = ''.join(f'<tr><td>{esc(row["feature"])}</td><td>{row["completed_bar_value"]:+.3f}</td>'
                                    f'<td>${row["contribution_to_chosen_forecast_usd"]:+.2f}</td></tr>'
                                    for row in trace["feature_contributions_usd"])
        chosen_index = action_labels.index(f'{trace["action"]} · {trace["horizon_bars"]} bars')
        realized_chosen = trace["realized_oracle_stress_net_usd_after_maturity"][chosen_index]
        brain_html = (f'<h2>One exact decision trace · private local view</h2>'
                      f'<p>This is the first selected signal in the fixed holdout, at {esc(trace["available_at"])}. '
                      f'The Ridge model chose {esc(trace["action"])} for {trace["horizon_bars"]} bars because its predicted '
                      f'worst-fill stressed net was ${trace["chosen_action_predicted_net_usd"]:+.2f}. '
                      f'The realized value was ${realized_chosen:+.2f}, visible only after the exit matured.</p>'
                      f'<div class="tablewrap"><table><thead><tr><th>Action</th><th>Student predicted net</th><th>Oracle realized net later</th></tr></thead><tbody>{forecast_rows}</tbody></table></div>'
                      f'<p>The chosen action prediction equals its training-mean baseline of ${trace["chosen_action_baseline_usd"]:+.2f} '
                      f'plus these feature contributions. They explain the arithmetic of this Ridge forecast, not causality or hidden thoughts.</p>'
                      f'<div class="tablewrap"><table><thead><tr><th>Completed-bar feature</th><th>Value</th><th>Contribution to chosen forecast</th></tr></thead><tbody>{contribution_rows}</tbody></table></div>')
    family_rows = []
    for family in report["families"]:
        best = family["best_variant"]
        fold_text = " / ".join(f"{x:+.3f}" for x in best["fold_rank_scores"])
        family_rows.append(f'<tr><td>{family["id"]:02d}</td><td>{esc(family["hypothesis"])}</td>'
                           f'<td>v{best["variant"]:02d} · {esc(best["model"])}</td>'
                           f'<td>{best["mean_rank_score"]:+.3f}</td><td>{fold_text}</td>'
                           f'<td>{family["gate_pass_count"]}/10</td><td>{family["paper_api_parity_count"]}/10</td></tr>')
    variant_rows = []
    for row in report["variants"]:
        folds = " / ".join(f"{x:+.3f}" for x in row["fold_rank_scores"])
        imitation = np.mean(row["oracle_imitation_fraction_by_fold"])
        variant_rows.append(f'<tr><td>{row["searcher"]:02d}/v{row["variant"]:02d}</td><td>{esc(row["model"])}</td>'
                            f'<td>{row["mean_rank_score"]:+.3f}</td><td>{folds}</td>'
                            f'<td>{"pass" if row["rank_gate_pass"] else "fail"}</td>'
                            f'<td>{imitation:.1%}</td><td>{"yes" if row["current_paper_api_feature_parity"] else "adapter needed"}</td>'
                            f'<td>{esc(", ".join(row["features"]))}</td></tr>')
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MNQ Oracle → Student | 100-trial dashboard</title>
<style>
:root{{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,sans-serif}}
body{{margin:0;background:#0b1220;color:#e9f0fc}}main{{max-width:1300px;margin:auto;padding:30px 22px 70px}}
h1{{font-size:clamp(2rem,4vw,3.4rem);margin:.2em 0}}h2{{margin:34px 0 12px}}p{{line-height:1.6;color:#b7c8e2;max-width:950px}}
.eyebrow{{color:#76c7ff;text-transform:uppercase;letter-spacing:.13em;font-weight:750;font-size:.78rem}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(205px,1fr));gap:12px;margin:24px 0}}
.card{{background:#142238;border:1px solid #29415f;border-radius:14px;padding:18px}}
.card strong{{display:block;font-size:1.7rem;color:#fff}}.card span{{color:#a8beda;font-size:.9rem}}
.banner{{border-left:4px solid #ffb454;background:#2a241f;padding:16px 19px;border-radius:8px;color:#ffddb0}}
.flow{{display:flex;flex-wrap:wrap;align-items:stretch;gap:10px;margin:18px 0}}.step{{flex:1;min-width:180px;border:1px solid #315070;border-radius:12px;background:#142238;padding:14px}}
.step b{{display:block;color:#76c7ff;margin-bottom:5px}}.step small{{color:#b7c8e2;line-height:1.5}}
.tablewrap{{overflow:auto;border:1px solid #29415f;border-radius:12px}}table{{width:100%;border-collapse:collapse;font-size:.86rem}}
th,td{{text-align:left;vertical-align:top;padding:10px 12px;border-bottom:1px solid #253953}}th{{position:sticky;top:0;background:#1a2d49;color:#cce2ff}}
tr:hover{{background:#142238}}td:nth-child(4),td:nth-child(5){{white-space:nowrap}}details{{margin-top:22px}}summary{{cursor:pointer;color:#76c7ff;font-weight:700}}
code{{color:#aee0ff}}.note{{font-size:.88rem;color:#97acca}}a{{color:#83d2ff}}
</style></head><body><main>
<div class="eyebrow">Research dashboard · November 3, 2026</div><h1>Can the student learn the oracle’s trades?</h1>
<p>Ten search agents proposed 100 fixed variants. Ten independent testers gave each variant hindsight labels for the best long/short action and 3, 5, 10, or 20-bar exit. The student saw only completed-bar features. Future prices were used to grade and teach, never to make a live decision.</p>
<div class="grid"><div class="card"><strong>100 / 100</strong><span>Variants tested</span></div>
<div class="card"><strong>{report["rank_gate_pass_count"]}</strong><span>Passed the three-fold rank gate</span></div>
<div class="card">{card}</div><div class="card"><strong>{holdout_text}</strong><span>One-time internal holdout</span></div></div>
{holdout_cards}
<div class="banner"><b>Live-trading status: blocked.</b> {outcome_text} Hindsight success is not a tradable forecast. The Yahoo contract and roll are unverified; no strategy has passed untouched confirmation or a finite risk gate. No broker orders were sent.</div>
<h2>What the agent “brain” can show</h2><div class="flow">
<div class="step"><b>1 · Completed chart</b><small>OHLCV history and causal market state, available after the minute closes.</small></div>
<div class="step"><b>2 · Student values</b><small>Predicted net dollars for eight entry/exit choices. Abstain if none clears stressed costs.</small></div>
<div class="step"><b>3 · Decision trace</b><small>Timestamp, feature values, eight predictions, selected action, horizon, and abstention reason. Local feature sensitivities can explain a selected model’s forecast; they are not literal thoughts.</small></div>
<div class="step"><b>4 · Oracle lesson later</b><small>Only after the future path matures, reveal all eight realized values and compare with the student. Missing bars invalidate the label.</small></div></div>
<p class="note">The hindsight oracle sees future entry and exit prices. Its high positive-action rate measures how often a perfect hindsight choice exists, not how often a student can predict it. Exact oracle imitation is shown below, but ranking and executable replay determine whether any candidate is useful.</p>
{brain_html}
<h2>Ten search families</h2><div class="tablewrap"><table><thead><tr><th>Agent</th><th>Hypothesis</th><th>Best variant</th><th>Mean rank</th><th>Three folds</th><th>Gate passes</th><th>Current API parity</th></tr></thead><tbody>{''.join(family_rows)}</tbody></table></div>
<details><summary>Inspect all 100 tested variants</summary><div class="tablewrap"><table><thead><tr><th>ID</th><th>Model</th><th>Mean rank</th><th>Three folds</th><th>Gate</th><th>Oracle imitation</th><th>API parity</th><th>Completed-bar features</th></tr></thead><tbody>{''.join(variant_rows)}</tbody></table></div></details>
<h2>How to read this result</h2><p>A rank score above zero means higher predicted action values tended to correspond to better realized action values in that fold. The fixed gate requires all three fold scores above zero and a mean above 0.05. Scores were chosen without replay profit. A winner gets exactly one internal holdout replay; that older holdout is still development evidence. Production requires a newly collected, source-audited cohort and a live feature adapter that reproduces the same inputs.</p>
<p>Historical future bars cannot tell us which future state will occur next. The teacher compares eight fixed actions on the one path that actually happened; it does not predict every possible path. A future student could model a distribution of scenarios, but its probabilities and payoffs would still need calibration and prospective validation before a live chart could use them.</p>
<p class="note">Source: frozen campaign05 plan and proposal hashes, ten independent tester ledgers. Full aggregate JSON: <code>mnq_campaign05_summary.json</code>. Local dashboard contains no private minute bars, models, or row-level outcomes.</p>
</main></body></html>'''


def run() -> dict:
    report = aggregate()
    save_json(SUMMARY, report)
    PAGE.write_text(render(report), encoding="utf-8")
    trace_path = OUT / "brain_trace_PRIVATE.json"
    if trace_path.exists():
        PRIVATE_PAGE.write_text(render(report, json.loads(trace_path.read_text())), encoding="utf-8")
    return report


if __name__ == "__main__":
    run()
