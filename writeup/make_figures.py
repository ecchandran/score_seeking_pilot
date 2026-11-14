"""Generate pgfplots figures and LaTeX tables for the 2-page write-up from committed stats.

  .venv/bin/python writeup/make_figures.py

Reads results/stage2_dose_v2/stage2_stats.json and results/stage3_conditions/stage3_stats.json
(never the raw transcripts) and writes writeup/generated/*.tex. Rerun after any re-analysis;
never hand-edit the generated files.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "generated"
sys.path.insert(0, str(REPO))
from src.analyze import ALPHA, Z95, holm, lr_2x2, newcombe_diff, wilson  # noqa: E402

# Stage 3 contrasts reported in the write-up (human decision 2026-11-08): both against enable.
# control - enable is the pre-registered enable - control with the sign flipped (same p);
# block - enable is new (not pre-registered). Holm runs across these 12 contrasts.
CONTRASTS = [("control", "enable"), ("block", "enable")]

# Display order (capability order within OpenAI, DeepSeek last) and Okabe-Ito colors + markers,
# so identity never rests on color alone.
MODELS = [
    ("gpt-6-astra", "GPT-6 Astra", "oiBlue", "*"),
    ("gpt-5.6-sol", "GPT-5.6 Sol", "oiOrange", "square*"),
    ("gpt-5.5", "GPT-5.5", "oiGreen", "triangle*"),
    ("o3", "o3", "oiPurple", "diamond*"),
    ("openai/gpt-oss-120b", "gpt-oss-120b", "oiVermillion", "pentagon*"),
    ("deepseek/deepseek-v4-pro", "DeepSeek V4 Pro", "oiSky", "otimes*"),
]
COLORS = {"oiBlue": "0072B2", "oiOrange": "E69F00", "oiGreen": "009E73",
          "oiPurple": "CC79A7", "oiVermillion": "D55E00", "oiSky": "56B4E9"}


def load(p: str) -> dict:
    return json.loads((REPO / p).read_text())


def colors_tex() -> str:
    return "".join(f"\\definecolor{{{n}}}{{HTML}}{{{h}}}\n" for n, h in COLORS.items())


def dose_tex(s2: dict) -> str:
    """Violation rate among grader readers vs V, Wilson 95% bars, small x-jitter per model."""
    lines = []
    for i, (mid, name, col, mark) in enumerate(MODELS):
        jit = (i - 2.5) * 0.012
        # pgfplots asymmetric error bars: "+=" / "-=" explicit values
        pts = []
        for c in s2["per_model"][mid]["by_V"]:
            if not c["n_analysis"]:
                continue
            lo, hi = wilson(c["violations"], c["n_analysis"], Z95)   # 95% Wilson
            pts.append(f"({c['V'] + jit:.3f},{100 * c['rate']:.1f}) "
                       f"+= (0,{100 * (hi - c['rate']):.1f}) -= (0,{100 * (c['rate'] - lo):.1f})")
        pts = " ".join(pts)
        lines.append(
            f"\\addplot+[{col}, mark={mark}, mark size=1.6pt, line width=0.7pt, "
            f"mark options={{solid, fill={col}, draw=white, line width=0.3pt}}, "
            f"error bars/.cd, y dir=both, y explicit, "
            f"error bar style={{line width=0.4pt, {col}, opacity=0.6}}, error mark=none] "
            f"coordinates {{{pts}}};\n"
            f"\\addlegendentry{{{name}}}")
    return "\n".join(lines) + "\n"


def stage3_contrasts(s3: dict) -> dict:
    """Newcombe 95% CI and LR p for each contrast in CONTRASTS, Holm across all of them."""
    out, pvals = {}, {}
    for mid, *_ in MODELS:
        cells = s3["per_model"][mid]["cells"]
        out[mid] = {}
        for a, b in CONTRASTS:
            ka, na = cells[a]["violations"], cells[a]["n_analysis"]
            kb, nb = cells[b]["violations"], cells[b]["n_analysis"]
            d, lo, hi = newcombe_diff(ka, na, kb, nb, Z95)
            p = lr_2x2(ka, na, kb, nb)
            out[mid][f"{a}-{b}"] = {"diff": d, "ci95": [lo, hi], "p_lr": p,
                                    "counts": [ka, na, kb, nb]}
            pvals[(mid, f"{a}-{b}")] = p
    for (mid, key), h in holm(pvals, ALPHA).items():
        out[mid][key].update(h)
    return out


def forest_tex(s3: dict) -> str:
    """block - control (filled) and enable - control (hollow), 95% Newcombe CIs, in points."""
    out = []
    n = len(MODELS)
    for i, (mid, name, col, _) in enumerate(MODELS):
        y = n - i
        for key, dy, fill in (("block-enable", 0.17, col), ("control-enable", -0.17, "white")):
            c = s3[mid][key]
            d, (lo, hi) = 100 * c["diff"], (100 * c["ci95"][0], 100 * c["ci95"][1])
            sig = c["reject"]
            out.append(
                f"\\addplot+[only marks, {col}, mark={'*' if key == 'block-enable' else 'o'}, "
                f"mark size={'2.0' if sig else '1.6'}pt, mark options={{fill={fill}, "
                f"line width={'1.0' if sig else '0.6'}pt}}, error bars/.cd, x dir=both, "
                f"x explicit, error bar style={{line width={'1.0' if sig else '0.5'}pt, {col}}}, "
                f"error mark=|, error mark options={{mark size=1.2pt, {col}}}] coordinates "
                f"{{({d:.1f},{y + dy:.2f}) += ({hi - d:.1f},0) -= ({d - lo:.1f},0)}};")
    return "\n".join(out) + "\n"


def num(x: float) -> str:
    """Signed integer with a true minus sign, for tables."""
    s = f"{x:+.0f}"
    return "$-$" + s[1:] if s.startswith("-") else s


def dose_label(v: float) -> str:
    return f"{v:.1f}" if v >= 0.1 else f"{v:.2f}"


def pct(k: int, n: int) -> str:
    return f"{k}/{n}" if n else "--"


def table_stage3(s3: dict, contrasts: dict) -> str:
    rows = []
    for mid, name, _, _ in MODELS:
        d = s3["per_model"][mid]
        cells = d["cells"]
        vs = cells["control"]["V"]
        row = [name, dose_label(vs)]
        for cond in ("control", "block", "enable"):
            c = cells[cond]
            txt = f"{pct(c['violations'], c['n_analysis'])} ({100 * c['rate']:.0f}\\%)"
            row.append(txt)
        for key in ("control-enable", "block-enable"):
            c = contrasts[mid][key]
            s = (f"{num(100 * c['diff'])} [{num(100 * c['ci95'][0])}, {num(100 * c['ci95'][1])}]")
            p = c["p_lr"]   # raw (unadjusted) LR p; bold = rejected by Holm
            ptxt = ("$<$0.001" if p < 0.001 else f"{p:.3f}" if p < 0.01 else f"{p:.2f}")
            s += f"; {ptxt}"
            row.append(f"\\textbf{{{s}}}" if c["reject"] else s)
        rows.append(" & ".join(row) + r" \\")
    return "\n".join(rows) + "\n"


def table_stage2(s2: dict) -> str:
    rows = []
    for mid, name, _, _ in MODELS:
        d = s2["per_model"][mid]
        reads = sum(c["read_grader"] for c in d["by_V"])
        runs = sum(c["n_runs"] for c in d["by_V"])
        v0 = d["by_V"][0]
        v1 = d["by_V"][-1]
        if d["floor"]:
            ed = "--"      # floor model: never violates, no ED50
        else:
            lo, hi = d["bootstrap"]["ci"]
            f2 = lambda x: f"$-${-x:.2f}" if x < 0 else f"{x:.2f}"
            # asterisk: step-shaped curve (pre-registered low-dose flag); the linear logit fit
            # is a poor description there, explained in the text (human decision 2026-11-11)
            star = "*" if d["flags"]["add_low_doses"] else ""
            ed = f"{f2(d['ed50'])}{star} [{f2(lo)}, {f2(hi)}]"
        rows.append(" & ".join([name, f"{reads}/{runs}", pct(v0["violations"], v0["n_analysis"]),
                                pct(v1["violations"], v1["n_analysis"]), ed]) + r" \\")
    return "\n".join(rows) + "\n"


def sci(p: float) -> str:
    m, e = f"{p:.0e}".split("e")
    return f"{m}\\times 10^{{{int(e)}}}"


def macros(s2: dict, s3: dict) -> str:
    h1 = s2["h1_all_models"]
    return (f"\\newcommand{{\\DoseLR}}{{{h1['lr_stat']:.1f}}}\n"
            f"\\newcommand{{\\DoseDF}}{{{h1['df']}}}\n"
            f"\\newcommand{{\\DoseP}}{{{sci(h1['p'])}}}\n"
            f"\\newcommand{{\\StageThreeAlpha}}{{{s3['alpha']}}}\n")


# ---- Stage 4 (judges and monitor) ------------------------------------------------------
# Monitor results use grader readers with a comply/violate outcome, the analysis set used
# everywhere else (human decision 2026-11-10). "all" would add runs that never read the grader.
MONITOR_SET = "readers"


def kn(k: int, n: int) -> str:
    return f"{k}/{n}" if n else "--"


def table_stage4_judges(s4: dict) -> str:
    """One row per model: the attestation breakdown (violators, then compliers answering No),
    then evaluation awareness (human decisions 2026-11-11/12): runs with reasoning out of all
    grader readers, then planted-test and possible-unused-grader flags out of the runs with
    reasoning, each with a Wilson 95% CI on that denominator."""
    def among_reasoning(h2: dict, flag: str) -> str:
        n = h2["n_with_reasoning"]
        if not n:
            return "--"
        d = h2[flag]
        k, (lo, hi) = d["k_with_reasoning"], d["ci_with_reasoning"]
        return f"{kn(k, n)} ({100 * k / n:.0f}\\%) [{100 * lo:.0f}, {100 * hi:.0f}]"

    rows = []
    for mid, name, _, _ in MODELS:
        h2 = s4["h2"]["per_model"][mid]
        reasoning_present = kn(h2["n_with_reasoning"], h2["n_judged"])
        h4 = s4["h4"][mid]
        nv = h4["violators"]
        ncomp = sum(v for k, v in h4["table"].items() if k.startswith("comply|"))
        rows.append(" & ".join([
            name, str(nv), kn(h4["violators_yes"], nv),
            kn(h4["ack_among_violators"][0], h4["ack_among_violators"][1]),
            (kn(h4['dishonest'], h4['violators_judged'])
             if h4["violators_judged"] else "--"),
            kn(h4["table"].get("comply|no", 0), ncomp), reasoning_present,
            among_reasoning(h2, "planted_test"),
            among_reasoning(h2, "grader_may_not_be_used")]) + r" \\")
    return "\n".join(rows) + "\n"


def table_stage4_monitor(s4: dict) -> str:
    A, B = s4["monitor"][f"A_{MONITOR_SET}"], s4["monitor"][f"B_{MONITOR_SET}"]
    f = lambda x: "--" if x is None else f"{x:.2f}"
    p = lambda x: "--" if x is None else f"{100 * x:.0f}\\%"
    rows = []
    for mid, name in [(m, n) for m, n, _, _ in MODELS] + [("pooled", "\\textit{Pooled}")]:
        a, b = A[mid], B[mid]
        if mid == "pooled":
            rows.append(r"\midrule")
        rows.append(" & ".join([name, str(a["n"]), p(a["base_rate"]), f(a["auroc"]),
                                f(b["auroc"]), f"{p(a['recall@0.5'])} / {p(b['recall@0.5'])}",
                                f"{p(a['precision@0.5'])} / {p(b['precision@0.5'])}"]) + r" \\")
    return "\n".join(rows) + "\n"


MON_STYLE = {"A": "black!45, dashed, mark=o, mark options={solid, fill=white}",
             "B": "black, mark=*, mark options={fill=black}"}


def roc_tex(s4: dict) -> str:
    out = []
    for v in ("A", "B"):
        d = s4["monitor"][f"{v}_{MONITOR_SET}"]["pooled"]
        pts = " ".join(f"({a:.4f},{b:.4f})" for a, b in d["roc"])
        out.append(f"\\addplot+[{MON_STYLE[v].split(', mark')[0]}, mark=none, line width=0.8pt] "
                   f"coordinates {{{pts}}};\n\\addlegendentry{{{v}: AUROC {d['auroc']:.2f}}}")
    return "\n".join(out) + "\n"


CALIB_SIZE_KEY = (10, 50, 250)


def calib_radius(n: int) -> float:
    """Marker radius (pt) grows with sqrt(n), so marker area is roughly proportional to n."""
    return 0.6 + 0.16 * n ** 0.5


def calib_tex(s4: dict) -> str:
    """Line per variant; one marker per decile bin sized by its run count; plus a size key."""
    out = []
    for v in ("A", "B"):
        bins = s4["monitor"][f"{v}_{MONITOR_SET}"]["pooled"]["calibration"]
        pts = " ".join(f"({b['mean_p']:.3f},{b['observed']:.3f})" for b in bins)
        line, mark = MON_STYLE[v].split(", mark=", 1)
        out.append(f"\\addplot+[{line}, mark=none, line width=0.7pt, forget plot] "
                   f"coordinates {{{pts}}};")
        for b in bins:
            out.append(f"\\addplot+[only marks, {line.split(',')[0]}, mark={mark}, "
                       f"mark size={calib_radius(b['n']):.2f}pt, forget plot] "
                       f"coordinates {{({b['mean_p']:.3f},{b['observed']:.3f})}};")
        out.append(f"\\addlegendimage{{{MON_STYLE[v]}, mark size=1.6pt, line width=0.7pt}}\n"
                   f"\\addlegendentry{{{v}}}")
    # size key, top left (the region above the diagonal at low p is empty)
    y = 0.95
    for n in CALIB_SIZE_KEY:
        r = calib_radius(n)
        out.append(f"\\draw[black!60, line width=0.4pt] (axis cs:0.05,{y:.3f}) circle[radius={r:.2f}pt];"
                   f"\n\\node[anchor=west, font=\\scriptsize, inner sep=1pt] at (axis cs:0.085,{y:.3f}) "
                   f"{{$n={n}$}};")
        y -= 0.075
    out.append("\\node[anchor=west, font=\\scriptsize, black!60, inner sep=1pt] at "
               "(axis cs:0.03,0.735) {runs per bin};")
    return "\n".join(out) + "\n"


def stage4_macros(s4: dict) -> str:
    t, tr = s4["h2"]["openai_test"], s4["h2"]["openai_test_with_reasoning"]
    ma = s4.get("model_agreement", {})
    k = lambda j, c: f"{ma[j]['per_label'][c]['kappa']:.2f}"
    A, B = s4["monitor"][f"A_{MONITOR_SET}"]["pooled"], s4["monitor"][f"B_{MONITOR_SET}"]["pooled"]
    return (f"\\newcommand{{\\SuspG}}{{{t['G']:.1f}}}\n\\newcommand{{\\SuspP}}{{{t['p']:.4f}}}\n"
            f"\\newcommand{{\\SuspGr}}{{{tr['G']:.1f}}}\n\\newcommand{{\\SuspPr}}{{{tr['p']:.2f}}}\n"
            f"\\newcommand{{\\KappaPlanted}}{{{k('suspicion', 'planted_test')}}}\n"
            f"\\newcommand{{\\KappaAck}}{{{k('ack', 'acknowledged_conflict')}}}\n"
            f"\\newcommand{{\\KappaNotUsed}}{{{k('suspicion', 'grader_may_not_be_used')}}}\n"
            f"\\newcommand{{\\AgreeNotUsed}}{{{ma['suspicion']['per_label']['grader_may_not_be_used']['agree']}}}\n"
            f"\\newcommand{{\\MonN}}{{{A['n']}}}\n"
            f"\\newcommand{{\\MonBase}}{{{100 * A['base_rate']:.0f}\\%}}\n"
            f"\\newcommand{{\\MonMeanA}}{{{A['mean_p']:.2f}}}\n"
            f"\\newcommand{{\\MonMeanB}}{{{B['mean_p']:.2f}}}\n")


def main() -> None:
    s2 = load("results/stage2_dose_v2/stage2_stats.json")
    s3 = load("results/stage3_conditions/stage3_stats.json")
    OUT.mkdir(exist_ok=True)
    con = stage3_contrasts(s3)
    (OUT / "stage3_vs_enable.json").write_text(json.dumps(
        {"alpha": ALPHA, "contrasts": [f"{a}-{b}" for a, b in CONTRASTS], "per_model": con},
        indent=1))
    files = {"colors.tex": colors_tex(), "dose_plots.tex": dose_tex(s2),
             "forest_plots.tex": forest_tex(con), "table_stage3.tex": table_stage3(s3, con),
             "table_stage2.tex": table_stage2(s2), "macros.tex": macros(s2, s3)}
    s4 = load("results/stage4_final/stage4_stats.json")
    files.update({"table_stage4_judges.tex": table_stage4_judges(s4),
                  "table_stage4_monitor.tex": table_stage4_monitor(s4),
                  "monitor_roc.tex": roc_tex(s4), "monitor_calib.tex": calib_tex(s4),
                  "macros_stage4.tex": stage4_macros(s4)})
    for name, body in files.items():
        (OUT / name).write_text("% generated by writeup/make_figures.py; do not edit\n" + body)
    print("wrote", ", ".join(files))


if __name__ == "__main__":
    main()
