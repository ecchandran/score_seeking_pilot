"""Render env_templates/ into a fresh instance directory per run.

An instance holds only what the agent may see. Nothing that names the model,
condition, dose, run ID, or host layout is written into it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATES = REPO / "env_templates"

GRADER_TMPL = "metadata/grader.py.tmpl"
GRADER_OUT = "metadata/grader.py"
TRACKER_OUT = "metadata/capability_tracker.json"
MEMO_OUT = "inbox/memo.de.txt"

MEMOS = ("memo_a", "memo_b", "memo_c", "memo_d")
CONDITIONS = ("control", "block", "enable", "control_approved", "control_blocked")
C_VALUE = 0.0


def format_score(x: float) -> str:
    """Render a score with up to two decimals, always as a float literal."""
    x = round(float(x), 2)
    if not 0.0 <= x <= 1.0:
        raise ValueError(f"score out of range: {x}")
    s = f"{x:.2f}".rstrip("0")
    return s + "0" if s.endswith(".") else s  # 0.5 -> "0.5", 1.0 -> "1.0", 0.25 -> "0.25"


def render_grader(V: float, C: float = C_VALUE, templates: Path = TEMPLATES) -> str:
    tmpl = (templates / "base" / GRADER_TMPL).read_text()
    assert tmpl.count("__V__") == 1 and tmpl.count("__C__") == 1
    return tmpl.replace("__V__", format_score(V)).replace("__C__", format_score(C))


def grader_v_line_index(templates: Path = TEMPLATES) -> int:
    """0-based line number of the `return __V__` line, the only line that varies."""
    lines = (templates / "base" / GRADER_TMPL).read_text().splitlines()
    return next(i for i, l in enumerate(lines) if "__V__" in l)


def render_tracker(condition: str, templates: Path = TEMPLATES) -> str:
    data = json.loads((templates / "conditions" / f"{condition}.json").read_text())
    return json.dumps(data, indent=2) + "\n"


def new_instance_id() -> str:
    return secrets.token_hex(4)


REMOVE_FILE = "_REMOVE"  # in a variant dir: base-relative paths to delete, one per line


def variants(templates: Path = TEMPLATES) -> tuple[str, ...]:
    vdir = templates / "variants"
    return tuple(sorted(p.name for p in vdir.iterdir() if p.is_dir())) if vdir.exists() else ()


def apply_variant(dest: Path, variant: str, templates: Path = TEMPLATES) -> None:
    """Overlay env_templates/variants/<variant>/ onto a rendered base instance."""
    vdir = templates / "variants" / variant
    if not vdir.is_dir():
        raise ValueError(f"unknown variant {variant!r}")
    rm = vdir / REMOVE_FILE
    if rm.exists():
        for rel in rm.read_text().split():
            (dest / rel).unlink()
    for src in sorted(vdir.rglob("*")):
        rel = src.relative_to(vdir)
        if rel.as_posix() == REMOVE_FILE or any(p.startswith(".") for p in rel.parts):
            continue
        target = dest / rel
        if src.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, target)


def render_instance(dest_root: Path, instance_id: str, condition: str, V: float,
                    memo: str, templates: Path = TEMPLATES, variant: str | None = None) -> Path:
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}")
    if memo not in MEMOS:
        raise ValueError(f"unknown memo {memo!r}")
    dest_root.mkdir(parents=True, exist_ok=True)
    dest = dest_root / instance_id
    dest.mkdir(exist_ok=False)

    base = templates / "base"
    for src in sorted(base.rglob("*")):
        rel = src.relative_to(base)
        if any(part.startswith(".") for part in rel.parts):  # e.g. a stray .DS_Store
            continue
        if src.is_symlink():
            raise RuntimeError(f"symlink in templates: {rel}")
        if rel.as_posix() == GRADER_TMPL:
            continue
        target = dest / rel
        if src.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, target)

    (dest / GRADER_OUT).write_text(render_grader(V, C_VALUE, templates))
    (dest / TRACKER_OUT).write_text(render_tracker(condition, templates))
    shutil.copyfile(templates / "memos" / f"{memo}.de.txt", dest / MEMO_OUT)
    if variant:
        apply_variant(dest, variant, templates)
    return dest


def load_reference(memo: str, templates: Path = TEMPLATES) -> str:
    return (templates / "memo_refs" / f"{memo}.en.txt").read_text()


def load_memo(memo: str, templates: Path = TEMPLATES) -> str:
    return (templates / "memos" / f"{memo}.de.txt").read_text()


def template_hashes(templates: Path = TEMPLATES) -> dict[str, str]:
    out = {}
    for p in sorted(templates.rglob("*")):
        rel = p.relative_to(templates)
        if p.is_file() and not any(part.startswith(".") for part in rel.parts):
            out[rel.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Render one instance (for manual inspection).")
    ap.add_argument("--condition", default="control", choices=CONDITIONS)
    ap.add_argument("--V", type=float, default=0.5)
    ap.add_argument("--memo", default="memo_a", choices=MEMOS)
    ap.add_argument("--out", type=Path, default=REPO / "instances")
    a = ap.parse_args()
    print(render_instance(a.out, new_instance_id(), a.condition, a.V, a.memo))


if __name__ == "__main__":
    main()
