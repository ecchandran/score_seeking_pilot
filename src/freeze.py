"""Gate 1 freeze: record hashes of everything frozen after Gate 1 in FREEZE.json (committed).

  python -m src.freeze write    # once, after human approval at Gate 1
  python -m src.freeze check    # verify the working tree still matches FREEZE.json

Frozen: every file under env_templates/ (base, variants, memos, memo refs, conditions), the
agent prompts and tool descriptions, harness settings, and the host-side grader and attestation
parser (they define the outcome). A config with `freeze: FREEZE.json` refuses to run if any of
these changed. Judge and monitor prompts are added to the freeze when they are written (Stage 4).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from . import envgen, harness

REPO = Path(__file__).resolve().parent.parent
FREEZE_PATH = REPO / "FREEZE.json"
SOURCE_FILES = ["src/grader_hidden.py", "src/attest.py"]


def current() -> dict:
    return {
        "template_hashes": envgen.template_hashes(),
        "prompt_tool_hashes": harness.frozen_text_hashes(),
        "harness_settings": {"max_model_calls": harness.MAX_MODEL_CALLS,
                             "max_nudges": harness.MAX_NUDGES,
                             "read_cap_bytes": harness.READ_CAP_BYTES},
        "source_hashes": {f: hashlib.sha256((REPO / f).read_bytes()).hexdigest()
                          for f in SOURCE_FILES},
    }


def diff(frozen: dict, now: dict) -> list[str]:
    out = []
    for section in ("template_hashes", "prompt_tool_hashes", "harness_settings", "source_hashes"):
        a, b = frozen.get(section, {}), now.get(section, {})
        for k in sorted(set(a) | set(b)):
            if a.get(k) != b.get(k):
                out.append(f"{section}/{k}")
    return out


def verify(path: Path = FREEZE_PATH) -> dict:
    """Return the frozen record if the tree matches it; raise SystemExit otherwise."""
    if not path.exists():
        raise SystemExit(f"{path.name} not found; the design has not been frozen.")
    frozen = json.loads(path.read_text())
    changed = diff(frozen, current())
    if changed:
        raise SystemExit("Frozen artifacts changed since Gate 1 (needs human sign-off and a new "
                         "freeze): " + ", ".join(changed))
    return frozen


def freeze_hash(frozen: dict) -> str:
    body = {k: frozen[k] for k in ("template_hashes", "prompt_tool_hashes", "harness_settings",
                                   "source_hashes")}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["write", "check"])
    ap.add_argument("--note", default="")
    ap.add_argument("--path", default=FREEZE_PATH.name,
                    help="freeze file at the repo root (a new design gets a new file)")
    a = ap.parse_args()
    path = REPO / a.path
    if a.action == "write":
        if path.exists():
            sys.exit(f"{path.name} already exists; changing it needs human sign-off.")
        rec = {"frozen_at_gate": 1, "note": a.note, **current()}
        path.write_text(json.dumps(rec, indent=2) + "\n")
        print(f"wrote {path.name}: freeze_hash {freeze_hash(rec)}")
    else:
        rec = verify(path)
        print(f"OK: tree matches {path.name} (freeze_hash {freeze_hash(rec)})")


if __name__ == "__main__":
    main()
