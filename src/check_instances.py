"""Assert that instances differ only where intended and leak nothing.

Allowed differences between any two instances:
  - the `return __V__` line of metadata/grader.py
  - metadata/capability_tracker.json
  - inbox/memo.de.txt

No instance may contain dotfiles, symlinks, or any forbidden string (model
names, condition names, run IDs, host user/home), matched case-insensitively
on word boundaries so that e.g. "block" does not match "blocked".

CLI: renders one instance per (condition, V, memo) into a temp dir and checks
them all.
"""
from __future__ import annotations

import argparse
import getpass
import itertools
import os
import re
import tempfile
from pathlib import Path

from . import envgen

ALLOWED_DIFF = {envgen.GRADER_OUT, envgen.TRACKER_OUT, envgen.MEMO_OUT}


class InstanceCheckError(AssertionError):
    pass


def snapshot(root: Path) -> dict[str, bytes]:
    """Map relative path -> bytes; fail on dotfiles or symlinks."""
    files: dict[str, bytes] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            rel = p.relative_to(root).as_posix()
            if name.startswith("."):
                raise InstanceCheckError(f"dotfile in instance: {rel}")
            if p.is_symlink():
                raise InstanceCheckError(f"symlink in instance: {rel}")
        for name in filenames:
            p = Path(dirpath) / name
            files[p.relative_to(root).as_posix()] = p.read_bytes()
    return files


def check_pair(a: Path, b: Path) -> None:
    sa, sb = snapshot(a), snapshot(b)
    if sa.keys() != sb.keys():
        raise InstanceCheckError(f"file sets differ: {sorted(sa.keys() ^ sb.keys())}")
    v_line = envgen.grader_v_line_index()
    for rel in sa:
        if sa[rel] == sb[rel]:
            continue
        if rel not in ALLOWED_DIFF:
            raise InstanceCheckError(f"disallowed difference in {rel}")
        if rel == envgen.GRADER_OUT:
            la = sa[rel].decode().splitlines()
            lb = sb[rel].decode().splitlines()
            if len(la) != len(lb):
                raise InstanceCheckError("grader.py line counts differ")
            bad = [i for i, (x, y) in enumerate(zip(la, lb)) if x != y and i != v_line]
            if bad:
                raise InstanceCheckError(f"grader.py differs outside the V line: lines {bad}")


def default_forbidden() -> list[str]:
    out = [getpass.getuser(), str(Path.home()), "instances", "env_templates", "memo_refs"]
    return [s for s in out if s]


def check_leaks(root: Path, forbidden: list[str]) -> None:
    pats = [(s, re.compile(rf"(?<![A-Za-z0-9_]){re.escape(s)}(?![A-Za-z0-9_])", re.IGNORECASE))
            for s in forbidden if s]
    for rel, data in snapshot(root).items():
        text = rel + "\n" + data.decode("utf-8", errors="replace")
        for s, pat in pats:
            if pat.search(text):
                raise InstanceCheckError(f"forbidden string {s!r} found in {rel}")


def check_all(roots: list[Path], forbidden: list[str]) -> None:
    """Every instance vs the first (sufficient: difference sets are transitive
    through the reference), plus a leak scan of each."""
    for r in roots:
        check_leaks(r, forbidden)
    for r in roots[1:]:
        check_pair(roots[0], r)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--forbid", nargs="*", default=[],
                    help="extra forbidden strings (model names, run IDs)")
    a = ap.parse_args()
    grid_v = [0.0, 0.1, 0.25, 0.5, 0.75, 1.0]
    forbidden = default_forbidden() + list(envgen.CONDITIONS) + a.forbid
    with tempfile.TemporaryDirectory() as td:
        total = 0
        for variant in (None,) + envgen.variants():  # pairwise checks within each variant
            roots = [envgen.render_instance(Path(td), envgen.new_instance_id(), cond, v, memo,
                                            variant=variant)
                     for cond, v, memo in itertools.product(envgen.CONDITIONS, grid_v, envgen.MEMOS)]
            # instance IDs stand in for run IDs: none may appear inside any instance
            check_all(roots, forbidden + list(envgen.variants()) + [r.name for r in roots])
            print(f"OK: {len(roots)} instances checked (variant={variant or 'base'})")
            total += len(roots)
    print(f"OK: {total} instances checked")


if __name__ == "__main__":
    main()
