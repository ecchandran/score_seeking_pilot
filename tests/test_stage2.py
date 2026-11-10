import json

import numpy as np
import pytest

from src import analyze, freeze, run


def test_wilson_bounds():
    lo, hi = analyze.wilson(0, 10)
    assert lo == 0 and 0.25 < hi < 0.35
    lo, hi = analyze.wilson(10, 10)
    assert hi == pytest.approx(1) and 0.65 < lo < 0.75


def test_separation_detection():
    V = np.array([0, 0, 0.5, 0.5, 1, 1])
    assert analyze.separated(V, np.array([0, 0, 0, 1, 1, 1]))      # quasi-complete
    assert analyze.separated(V, np.zeros(6))                         # all one outcome
    assert not analyze.separated(V, np.array([0, 1, 0, 1, 0, 1]))


def test_mle_recovers_known_curve():
    rng = np.random.default_rng(0)
    V = np.repeat(analyze.GRID, 400)
    a, b = -2.0, 4.0                                                 # ED50 = 0.5
    y = (rng.random(V.size) < 1 / (1 + np.exp(-(a + b * V)))).astype(float)
    f = analyze.fit_model(V, y)
    assert not f["firth"] and f["converged"]
    assert abs(f["ed50"] - 0.5) < 0.05


def test_firth_finite_under_separation():
    V = np.array([0.0] * 10 + [0.1] * 10 + [1.0] * 10)
    y = np.array([0] * 10 + [1] * 10 + [1] * 10, float)
    f = analyze.fit_model(V, y)
    assert f["firth"] and np.isfinite(f["a"]) and np.isfinite(f["b"]) and f["b"] > 0
    assert 0 < f["ed50"] < 0.1


def test_bootstrap_ci_and_no_slope_share():
    rng = np.random.default_rng(1)
    V = np.repeat(analyze.GRID, 30)
    y = (rng.random(V.size) < 1 / (1 + np.exp(-(-3 + 6 * V)))).astype(float)
    b = analyze.bootstrap_ed50(V, y, n_boot=200)
    assert b["ci"][0] < 0.5 < b["ci"][1]
    # all comply: the Firth fit extrapolates ED50 far outside the grid (floor rule applies upstream)
    flat = analyze.bootstrap_ed50(V, np.zeros(V.size), n_boot=50)
    assert flat["ci"][0] > 1


def test_lr_test_detects_model_difference():
    V = np.repeat(analyze.GRID, 40)
    rng = np.random.default_rng(2)
    steep = (rng.random(V.size) < 1 / (1 + np.exp(-(-2 + 8 * V)))).astype(float)
    flat = (rng.random(V.size) < 0.05).astype(float)
    h = analyze.lr_test_h1({"a": (V, steep), "b": (V, flat)})
    assert h["df"] == 2 and h["p"] < 1e-6
    same = analyze.lr_test_h1({"a": (V, steep), "b": (V, steep.copy())})
    assert same["p"] > 0.5


def test_v_star_rounding_and_clip():
    assert analyze.v_star(0.33) == pytest.approx(0.35)
    assert analyze.v_star(0.01) == pytest.approx(0.05)
    assert analyze.v_star(float("inf")) == 1.0


def test_reps_by_model():
    cfg = {"seed": 1, "run_name": "x",
           "models": [{"name": "m1", "provider": "stub"}, {"name": "m2", "provider": "stub"}],
           "cells": [{"conditions": ["control"], "V": [0.0, 1.0], "reps": 6,
                      "reps_by_model": {"m2": 2}}]}
    rows = run.build_manifest(cfg)
    assert sum(r["model"] == "m1" for r in rows) == 12
    assert sum(r["model"] == "m2" for r in rows) == 4


def test_freeze_detects_change(tmp_path):
    rec = {"frozen_at_gate": 1, **freeze.current()}
    path = tmp_path / "FREEZE.json"
    path.write_text(json.dumps(rec))
    assert freeze.verify(path) == rec
    rec["prompt_tool_hashes"]["system_prompt"] = "0" * 64
    path.write_text(json.dumps(rec))
    with pytest.raises(SystemExit, match="system_prompt"):
        freeze.verify(path)


def _t(outcome, tokens=0, err=None):
    return {"outcome": outcome, "error": err,
            "usage_total": {"input": tokens, "cached_input": 0, "output": 0, "reasoning": 0}}


def test_provider_halt_after_zero_token_errors():
    h = run.ProviderHalt()
    for _ in range(run.PROVIDER_STOP_AFTER - 1):
        h.record("openai", _t("error", err="429 no credits"))
    h.record("openai", _t("comply", 500))          # a success resets the count
    for _ in range(run.PROVIDER_STOP_AFTER - 1):
        h.record("openai", _t("error", err="429 no credits"))
    assert "openai" not in h.halted
    h.record("openai", _t("error", err="429 no credits"))
    assert h.halted == {"openai"}
    h.record("openrouter", _t("error", tokens=100, err="attestation failed"))  # used tokens
    assert "openrouter" not in h.halted


def test_set_aside_failed(tmp_path):
    d = tmp_path / "transcripts" / "m" / "control"
    d.mkdir(parents=True)
    (d / "a.json").write_text(json.dumps(_t("error", err="429")))
    (d / "b.json").write_text(json.dumps(_t("error", tokens=10, err="late failure")))
    (d / "c.json").write_text(json.dumps(_t("violate", 900)))
    assert run.set_aside_failed(tmp_path) == 1
    assert (tmp_path / "aborted" / "m" / "control" / "a.json").exists()
    assert sorted(p.name for p in d.iterdir()) == ["b.json", "c.json"]


def test_cells_restricted_to_models():
    cfg = {"seed": 1, "run_name": "x",
           "models": [{"name": "m1", "provider": "stub"}, {"name": "m2", "provider": "stub"}],
           "cells": [{"models": ["m1"], "conditions": ["control", "block"], "V": [1.0], "reps": 3},
                     {"models": ["m2"], "conditions": ["control", "block"], "V": [0.05], "reps": 3}]}
    rows = run.build_manifest(cfg)
    assert {(r["model"], r["V"]) for r in rows} == {("m1", 1.0), ("m2", 0.05)}
    assert len(rows) == 12


def test_stage3_stats_helpers():
    d, lo, hi = analyze.newcombe_diff(15, 30, 5, 30)
    assert d == pytest.approx(1 / 3) and lo < d < hi and lo > 0
    d, lo, hi = analyze.newcombe_diff(0, 10, 10, 10)          # extremes stay in [-1, 1]
    assert d == -1 and lo >= -1 and hi < 0
    assert analyze.lr_2x2(10, 10, 0, 10) < 1e-4                 # separated cells: LR still works
    assert analyze.lr_2x2(5, 10, 5, 10) == pytest.approx(1.0)
    adj = analyze.holm({"a": 0.01, "b": 0.04, "c": 0.5, "d": None})
    assert adj["a"]["p_holm"] == pytest.approx(0.03) and adj["a"]["reject"]
    assert adj["b"]["p_holm"] == pytest.approx(0.08) and not adj["b"]["reject"]   # alpha 0.05
    assert analyze.holm({"b": 0.04, "x": 0.5}, alpha=0.10)["b"]["reject"]
    assert not adj["c"]["reject"] and "d" not in adj
