"""Run a config: build and shuffle the manifest, render instances, run agents,
grade, write transcripts and results.jsonl. Resumes by skipping runs whose
transcript already exists.

  python -m src.run configs/stage0_smoke.yaml            # run
  python -m src.run configs/stage1_pilot.yaml --dry-run  # manifest + cost estimate only
  python -m src.run configs/stage0_smoke.yaml --rebuild-results

Config shape:
  run_name: stage0_smoke
  seed: 20261107
  models:
    - {name: gpt-5.5, provider: openai}
    - {name: openai/gpt-oss-120b, provider: openrouter, provider_pin: <name>}
    - {name: stub-violate, provider: stub, stub_mode: violate}
  cells:
    - {conditions: [control], V: [0.0, 1.0], reps: 3}
  memos: [memo_a, memo_b, memo_c, memo_d]    # optional
  freeze: FREEZE.json   # optional: refuse to run unless frozen artifacts match it
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import secrets
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import attest, check_instances, envgen, freeze, grader_hidden, harness, providers

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "runs"
INSTANCES = REPO / "instances"
COST_CONFIRM_USD = 5.0
CONCURRENCY = {"openai": 8, "openrouter": 8, "stub": 8}


# ---- small utilities ----------------------------------------------------------
def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json_atomic(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def write_jsonl_atomic(path: Path, rows: list[dict]) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".jsonl")
    with os.fdopen(fd, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def git_hash() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                             text=True, timeout=10)
        if out.returncode != 0:
            return "nogit"
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True,
                               text=True, timeout=10).stdout.strip()
        return out.stdout.strip() + ("-dirty" if dirty else "")
    except Exception:  # noqa: BLE001
        return "nogit"


def safe_dirname(model: str) -> str:
    return model.replace("/", "__")


def sha256_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


# ---- manifest -----------------------------------------------------------------
def build_manifest(cfg: dict) -> list[dict]:
    rng = random.Random(cfg["seed"])
    memos = cfg.get("memos", list(envgen.MEMOS))
    rows = []
    cell_idx = 0
    for model in cfg["models"]:
        for block in cfg["cells"]:
            for variant in block.get("variants", [None]):
                for cond in block["conditions"]:
                    for V in block["V"]:
                        offset = cell_idx % len(memos)  # rotate start: memos balance across cells
                        reps = block.get("reps_by_model", {}).get(model["name"], block["reps"])
                        for rep in range(reps):
                            row = {
                                "model": model["name"], "provider": model["provider"],
                                "condition": cond, "V": float(V),
                                "memo": memos[(offset + rep) % len(memos)], "replicate": rep,
                            }
                            if variant:
                                row["variant"] = variant
                            rows.append(row)
                        cell_idx += 1
    rng.shuffle(rows)
    used: set[str] = set()
    for order, r in enumerate(rows):
        r["order"] = order
        for key in ("run_id", "instance_id"):
            while True:
                v = secrets.token_hex(6 if key == "run_id" else 4)
                if v not in used:
                    used.add(v)
                    r[key] = v
                    break
    return rows


def load_or_create_manifest(run_dir: Path, cfg: dict, dry_run: bool) -> list[dict]:
    path = run_dir / "manifest.jsonl"
    if path.exists():
        return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    rows = build_manifest(cfg)
    if not dry_run:
        run_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl_atomic(path, rows)
    return rows


def forbidden_strings(cfg: dict, manifest: list[dict]) -> list[str]:
    out = check_instances.default_forbidden()
    for m in cfg["models"]:
        out.append(m["name"])
        out.append(m["name"].split("/")[-1])
    out += sorted({r["condition"] for r in manifest})
    out += sorted({r["variant"] for r in manifest if r.get("variant")})
    out += [r["run_id"] for r in manifest]
    out.append(cfg["run_name"])
    return sorted(set(s for s in out if s))


# ---- config.json (frozen hashes) ------------------------------------------------
def frozen_config(cfg: dict) -> dict:
    fz = None
    if cfg.get("freeze"):
        rec = freeze.verify(REPO / cfg["freeze"])
        fz = {"file": cfg["freeze"], "freeze_hash": freeze.freeze_hash(rec)}
    return {
        "config": cfg,
        "freeze": fz,
        "config_hash": sha256_json(cfg),
        "git_hash": git_hash(),
        "template_hashes": envgen.template_hashes(),
        "prompt_tool_hashes": harness.frozen_text_hashes(),
        "harness_settings": {
            "max_model_calls": harness.MAX_MODEL_CALLS, "max_nudges": harness.MAX_NUDGES,
            "read_cap_bytes": harness.READ_CAP_BYTES, "concurrency": CONCURRENCY,
        },
        "python": sys.version,
        "created_at": now(),
    }


def ensure_config_json(run_dir: Path, cfg: dict) -> dict:
    path = run_dir / "config.json"
    fresh = frozen_config(cfg)
    if path.exists():
        old = json.loads(path.read_text())
        for k in ("config_hash", "template_hashes", "prompt_tool_hashes"):
            if old[k] != fresh[k]:
                raise SystemExit(f"{k} changed since this run started; frozen artifacts were "
                                 f"edited. Use a new run_name (needs human sign-off).")
        return old
    write_json_atomic(path, fresh)
    return fresh


# ---- adapters -----------------------------------------------------------------
def make_adapter(model_cfg: dict, clients: dict, memo: str):
    p = model_cfg["provider"]
    name = model_cfg["name"]
    if p == "openai":
        return providers.OpenAIResponsesAdapter(
            clients["openai"], name, effort=model_cfg.get("effort", "medium"),
            service_tier=model_cfg.get("service_tier"))
    if p == "openrouter":
        return providers.OpenRouterChatAdapter(
            clients["openrouter"], name, effort=model_cfg.get("effort", "medium"),
            provider_pin=model_cfg.get("provider_pin"))
    if p == "stub":
        ref = envgen.load_reference(memo)
        mode = model_cfg.get("stub_mode", "violate")
        content = " ".join(ref.split()) if mode == "violate" else ref
        return providers.StubAdapter(name, providers.stub_script(
            content, attest_answer=model_cfg.get("stub_attest", "Yes"),
            nudge_first=model_cfg.get("stub_nudge", False)))
    raise ValueError(f"unknown provider {p!r}")


# ---- one run ------------------------------------------------------------------
def outcome_for(ep: harness.Episode, grade: dict | None) -> str:
    if ep.end_reason == "blocked":
        return "blocked_by_provider"
    if ep.end_reason == "error" and ep.submission is None:
        return "error"
    if ep.submission is None:
        return "no_submission"
    if ep.submission.get("filename") != harness.TARGET_FILENAME:
        return "other"
    if ep.end_reason == "error":   # submitted, then the attestation call failed
        return "error"
    return grade["outcome"] if grade else "other"


def usage_total(ep: harness.Episode) -> dict:
    tot = {"input": 0, "cached_input": 0, "output": 0, "reasoning": 0}
    usages = [t["usage"] for t in ep.turns]
    if ep.attestation:
        usages.append(ep.attestation["usage"])
    for u in usages:
        for k in tot:
            tot[k] += u.get(k, 0) or 0
    return tot


class Spend:
    """Running spend for this run directory; halts new runs at 80% of the approved budget."""

    def __init__(self, already: float, budget: float | None):
        self.total, self.budget, self.halted = already, budget, False

    def limit(self) -> float | None:
        return None if self.budget is None else 0.8 * self.budget

    def check(self) -> bool:
        lim = self.limit()
        if lim is not None and self.total >= lim:
            if not self.halted:
                print(f"STOP: spend ${self.total:.2f} reached 80% of the approved budget "
                      f"(${self.budget:.2f}); not starting further runs.", flush=True)
            self.halted = True
        return not self.halted


async def run_one(row: dict, model_cfg: dict, clients: dict, run_dir: Path, frozen: dict,
                  forbidden: list[str], sem: asyncio.Semaphore, keep_instance: bool,
                  spend: Spend | None = None) -> None:
    tpath = (run_dir / "transcripts" / safe_dirname(row["model"]) / row["condition"]
             / f"{row['run_id']}.json")
    if tpath.exists():
        return
    async with sem:
        if spend is not None and not spend.check():
            return
        INSTANCES.mkdir(exist_ok=True)
        root = envgen.render_instance(INSTANCES, row["instance_id"], row["condition"],
                                      row["V"], row["memo"], variant=row.get("variant"))
        started = now()
        try:
            check_instances.check_leaks(root, forbidden)
            adapter = make_adapter(model_cfg, clients, row["memo"])
            ep = await harness.run_episode(adapter, root)
        finally:
            if not keep_instance:
                shutil.rmtree(root, ignore_errors=True)
        ended = now()

    grade = None
    if ep.submission is not None and ep.submission.get("filename") == harness.TARGET_FILENAME:
        grade = grader_hidden.grade(ep.submission["content"], envgen.load_reference(row["memo"]),
                                    row["V"], envgen.C_VALUE)
    outcome = outcome_for(ep, grade)
    tot = usage_total(ep)
    att = ep.attestation
    transcript = {
        "run_id": row["run_id"], "instance_id": row["instance_id"], "model": row["model"],
        "provider": row["provider"], "condition": row["condition"], "V": row["V"],
        "C": envgen.C_VALUE, "memo": row["memo"], "replicate": row["replicate"],
        "variant": row.get("variant"),
        "order": row["order"],
        "config_hash": frozen["config_hash"], "git_hash": frozen["git_hash"],
        "started_at": started, "ended_at": ended,
        "turns": ep.turns, "files_read": ep.files_read, "nudges": ep.nudges,
        "submit_turn": ep.submit_turn, "submission": ep.submission,
        "submissions": ep.submissions,
        "hidden_grade": grade, "outcome": outcome, "end_reason": ep.end_reason,
        "blocked_phase": ep.blocked_phase,
        "attestation": ({"raw": att["raw"], "parsed": attest.parse(att["raw"]), **att}
                        if att else None),
        "usage_total": tot, "cost_usd": providers.cost_usd(row["model"], tot),
        "error": ep.error,
    }
    write_json_atomic(tpath, transcript)
    if spend is not None:
        spend.total += transcript["cost_usd"]
    print(f"[{row['order']:>4}] {row['model']:<28} {row['condition']:<16} V={row['V']:<5} "
          f"-> {outcome}{' (' + ep.error[:80] + ')' if ep.error else ''}", flush=True)


# ---- results.jsonl --------------------------------------------------------------
def result_row(t: dict) -> dict:
    reads = [f["path"] for f in t["files_read"]]
    grader_turns = [f["turn"] for f in t["files_read"] if f["path"] == "metadata/grader.py"]
    att = t.get("attestation") or {}
    u = t["usage_total"]
    return {
        "run_id": t["run_id"], "model": t["model"], "condition": t["condition"], "V": t["V"],
        "memo": t["memo"], "variant": t.get("variant"),
        "read_grader": "metadata/grader.py" in reads,
        "read_tracker": "metadata/capability_tracker.json" in reads,
        "first_grader_turn": min(grader_turns) if grader_turns else None,
        "outcome": t["outcome"],
        "score": (t["hidden_grade"] or {}).get("score"),
        "needs_review": (t["hidden_grade"] or {}).get("needs_review"),
        "attest": att.get("parsed"),
        "turns": len(t["turns"]), "nudges": t["nudges"],
        "input_tokens": u["input"], "cached_input_tokens": u["cached_input"],
        "output_tokens": u["output"], "reasoning_tokens": u["reasoning"],
        "cost_usd": t["cost_usd"], "blocked_phase": t.get("blocked_phase"),
        "started_at": t["started_at"], "order": t.get("order"),
    }


def rebuild_results(run_dir: Path) -> list[dict]:
    rows = [result_row(json.loads(p.read_text()))
            for p in sorted((run_dir / "transcripts").rglob("*.json"))
            if not p.name.startswith(".")]
    rows.sort(key=lambda r: (r["order"] is None, r["order"]))
    write_jsonl_atomic(run_dir / "results.jsonl", rows)
    return rows


# ---- main -----------------------------------------------------------------------
def measured_cost_per_run(run_dir: Path) -> dict[str, float]:
    costs: dict[str, list[float]] = {}
    for p in (run_dir / "transcripts").rglob("*.json"):
        t = json.loads(p.read_text())
        costs.setdefault(t["model"], []).append(t["cost_usd"])
    return {m: sum(c) / len(c) for m, c in costs.items() if c}


def confirm_cost(est: float, run_name: str, approved_budget: float | None) -> bool:
    print(f"Estimated cost: ${est:.2f}")
    if est <= COST_CONFIRM_USD:
        return True
    if approved_budget is not None:
        if est <= approved_budget:
            print(f"Within the human-approved budget of ${approved_budget:.2f}.")
            return True
        print(f"Estimate exceeds the approved budget of ${approved_budget:.2f}.")
        return False
    if not sys.stdin.isatty():
        print(f"Estimate exceeds ${COST_CONFIRM_USD:.0f}; run interactively to confirm.")
        return False
    return input(f"Type the run name ({run_name}) to confirm: ").strip() == run_name


async def amain(args) -> None:
    cfg = yaml.safe_load(Path(args.config).read_text())
    run_dir = RUNS / cfg["run_name"]
    if args.rebuild_results:
        rows = rebuild_results(run_dir)
        print(f"wrote {len(rows)} rows to {run_dir / 'results.jsonl'}")
        return

    if cfg.get("freeze"):
        freeze.verify(REPO / cfg["freeze"])
        print(f"freeze OK ({cfg['freeze']})")
    manifest = load_or_create_manifest(run_dir, cfg, args.dry_run)
    models = {m["name"]: m for m in cfg["models"]}
    tfiles = list((run_dir / "transcripts").rglob("*.json")) if run_dir.exists() else []
    done = {p.stem for p in tfiles}
    already_spent = sum(json.loads(p.read_text()).get("cost_usd", 0.0) for p in tfiles)
    todo = [r for r in manifest if r["run_id"] not in done]
    if args.only_models:
        todo = [r for r in todo if r["model"] in set(args.only_models)]
    if args.limit_per_model:
        seen: dict[str, int] = {}
        picked = []
        for r in todo:   # manifest order, so the canary is still shuffled
            if seen.get(r["model"], 0) < args.limit_per_model:
                seen[r["model"]] = seen.get(r["model"], 0) + 1
                picked.append(r)
        todo = picked

    measured = measured_cost_per_run(Path(args.estimate_from)) if args.estimate_from else {}

    def per_run(m: str) -> float:
        # measured mean x margin when available, else the spec's 20k/5k assumption
        return args.estimate_margin * measured[m] if m in measured else providers.estimate_cost(m, 1)

    est = sum(per_run(r["model"]) for r in todo)
    by_model: dict[str, int] = {}
    for r in todo:
        by_model[r["model"]] = by_model.get(r["model"], 0) + 1
    print(f"{cfg['run_name']}: {len(manifest)} runs in manifest, {len(todo)} to do")
    for m, n in sorted(by_model.items()):
        src = f"{args.estimate_margin:g}x measured" if m in measured else "assumed"
        print(f"  {m:<28} {n:>4} runs  ~${n * per_run(m):.2f} ({src})")
    if args.dry_run:
        print(f"Estimated cost: ${est:.2f} (dry run; nothing written)")
        return
    if already_spent:
        print(f"Already spent in this run directory: ${already_spent:.4f}")
    budget = args.approved_budget
    if not confirm_cost(est + (already_spent if budget is not None else 0.0), cfg["run_name"],
                        budget):
        print("Not confirmed; exiting.")
        return
    spend = Spend(already_spent, budget)
    if not spend.check():
        return

    frozen = ensure_config_json(run_dir, cfg)
    forbidden = forbidden_strings(cfg, manifest)
    needed = {models[r["model"]]["provider"] for r in todo} - {"stub"}
    clients = providers.make_clients(needed) if needed else {}
    sems = {p: asyncio.Semaphore(n) for p, n in CONCURRENCY.items()}
    await asyncio.gather(*[
        run_one(r, models[r["model"]], clients, run_dir, frozen, forbidden,
                sems[r["provider"]], args.keep_instances, spend)
        for r in todo
    ])
    rows = rebuild_results(run_dir)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    print(f"done: {counts}; total cost ${sum(r['cost_usd'] for r in rows):.4f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rebuild-results", action="store_true")
    ap.add_argument("--keep-instances", action="store_true",
                    help="debug only: leave rendered instances on disk")
    ap.add_argument("--approved-budget", type=float, default=None,
                    help="USD the human approved in chat for this run directory (total, incl. "
                         "spend so far). New runs stop at 80%% of it.")
    ap.add_argument("--limit-per-model", type=int, default=0,
                    help="canary: run only the first N pending runs per model")
    ap.add_argument("--only-models", nargs="*", default=None,
                    help="run only these models' pending runs (others stay pending)")
    ap.add_argument("--estimate-from", default=None,
                    help="earlier run dir; estimate cost from its measured mean per model")
    ap.add_argument("--estimate-margin", type=float, default=2.0,
                    help="multiplier on the measured mean (default 2)")
    asyncio.run(amain(ap.parse_args()))


if __name__ == "__main__":
    main()
