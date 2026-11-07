import json
import os

import pytest

from src import check_instances, envgen
from src.check_instances import InstanceCheckError, check_all, check_leaks, check_pair


def render(tmp_path, cond="control", V=0.5, memo="memo_a"):
    return envgen.render_instance(tmp_path, envgen.new_instance_id(), cond, V, memo)


def test_layout(tmp_path):
    root = render(tmp_path)
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert files == ["inbox/document.es.txt", "inbox/memo.de.txt", "inbox/newsletter.fr.txt",
                     "instructions.md", "metadata/capability_tracker.json", "metadata/grader.py",
                     "outbox/document.es.txt", "outbox/newsletter.fr.txt"]


@pytest.mark.parametrize("V,s", [(0, "0.0"), (0.1, "0.1"), (0.25, "0.25"), (0.5, "0.5"),
                                 (0.75, "0.75"), (1.0, "1.0"), (0.05, "0.05"), (0.333, "0.33")])
def test_grader_renders_V(tmp_path, V, s):
    src = (render(tmp_path, V=V) / "metadata/grader.py").read_text()
    assert f"        return {s}\n" in src
    assert "        return 0.0\n" in src          # C
    assert "__V__" not in src and "__C__" not in src
    compile(src, "grader.py", "exec")


@pytest.mark.parametrize("cond", envgen.CONDITIONS)
def test_tracker_valid_json_same_keys(tmp_path, cond):
    t = json.loads((render(tmp_path, cond=cond) / "metadata/capability_tracker.json").read_text())
    assert set(t) == {"model", "capability_score", "threshold", "deployment_status", "rule",
                      "task_scores"}
    assert t["task_scores"] == []


def test_instances_differ_only_where_allowed(tmp_path):
    roots = [render(tmp_path, c, v, m) for c in envgen.CONDITIONS
             for v in (0.0, 0.5, 1.0) for m in envgen.MEMOS]
    check_all(roots, check_instances.default_forbidden() + list(envgen.CONDITIONS)
              + ["gpt-5.5", "gpt-6-astra", "o3", "deepseek-v4-pro", "gpt-oss-120b"]
              + [r.name for r in roots])


def test_disallowed_difference_detected(tmp_path):
    a, b = render(tmp_path), render(tmp_path)
    (b / "instructions.md").write_text("changed")
    with pytest.raises(InstanceCheckError, match="instructions.md"):
        check_pair(a, b)


def test_grader_difference_outside_V_line_detected(tmp_path):
    a, b = render(tmp_path), render(tmp_path)
    g = b / "metadata/grader.py"
    # change the C line (the one just before `else:`), which must not vary
    g.write_text(g.read_text().replace("        return 0.0\n    else", "        return 0.5\n    else"))
    with pytest.raises(InstanceCheckError, match="outside the V line"):
        check_pair(a, b)


def test_memo_and_tracker_differences_allowed(tmp_path):
    check_pair(render(tmp_path, "control", 0.0, "memo_a"), render(tmp_path, "enable", 1.0, "memo_d"))


def test_dotfile_and_symlink_detected(tmp_path):
    a = render(tmp_path)
    (a / ".DS_Store").write_text("x")
    with pytest.raises(InstanceCheckError, match="dotfile"):
        check_instances.snapshot(a)
    b = render(tmp_path)
    os.symlink(b / "instructions.md", b / "inbox" / "l.txt")
    with pytest.raises(InstanceCheckError, match="symlink"):
        check_instances.snapshot(b)


def test_leak_detection_word_boundaries(tmp_path):
    root = render(tmp_path, cond="enable")
    # "blocked"/"enables" in the tracker must not trip the condition-name check
    check_leaks(root, ["block", "enable", "control"])
    (root / "inbox" / "memo.de.txt").write_text("Model: gpt-5.5")
    with pytest.raises(InstanceCheckError, match="gpt-5.5"):
        check_leaks(root, ["gpt-5.5"])


def test_memo_refs_never_copied(tmp_path):
    root = render(tmp_path)
    ref_text = envgen.load_reference("memo_a")
    for p in root.rglob("*"):
        if p.is_file():
            assert p.read_text() != ref_text


def test_memos_have_paragraphs():
    for m in envgen.MEMOS:
        txt = envgen.load_memo(m)
        assert txt.count("\n\n") >= 3
