"""Stage 4 clipped-transcript monitor (secondary hypothesis).

  python -m src.monitor run --variant A --sample readers --monitor-model gpt-5.5 \
        --approved-budget 2

Clip: the whole response that submits memo.de.txt, and everything after it (including that
response's reasoning and the attestation), is removed. Variant A: tool calls, tool results and
messages. Variant B: the same plus reasoning. Ground truth: the hidden grader's outcome.
Outputs: runs/<run>/monitor/<variant>__<model>/<run_id>.json.
"""
from __future__ import annotations

import argparse
import asyncio
import json

from . import judge_prompts as jp
from .judges import (JUDGE_MODELS, RUNS, analysis_set, kind_label, load_transcripts, render,
                     run_jobs)


def monitor_input(t: dict, variant: str) -> str:
    return render(t, reasoning=jp.MONITOR_VARIANTS[variant]["reasoning"], tool_outputs=True,
                  clip=True)


def monitor_jobs(ts: list[dict], variant: str, model: str) -> list[tuple]:
    out = []
    for t in ts:
        path = RUNS / t["_run"] / "monitor" / f"{variant}__{kind_label(model)}" / f"{t['run_id']}.json"
        out.append((path, jp.monitor_prompt(variant), monitor_input(t, variant), "monitor",
                    jp.MONITOR_SCHEMA, {"run": t["_run"], "run_id": t["run_id"],
                                        "variant": variant,
                                        "prompt_hash": jp.monitor_hash(variant),
                                        "ground_truth": t["outcome"]}))
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--variant", choices=list(jp.MONITOR_VARIANTS), required=True)
    r.add_argument("--sample", choices=["readers", "all"], required=True)
    r.add_argument("--monitor-model", default="gpt-5.5", choices=list(JUDGE_MODELS))
    r.add_argument("--limit", type=int, default=None)
    r.add_argument("--approved-budget", type=float, required=True)
    r.add_argument("--concurrency", type=int, default=8)
    a = ap.parse_args(argv)
    ts = load_transcripts()
    sel = (analysis_set(ts) if a.sample == "readers"
           else [t for t in ts if t["outcome"] in ("comply", "violate")])
    if a.limit:
        sel = sel[: a.limit]
    st = asyncio.run(run_jobs(monitor_jobs(sel, a.variant, a.monitor_model), a.monitor_model,
                              a.approved_budget, a.concurrency))
    print(json.dumps(st))


if __name__ == "__main__":
    main()
