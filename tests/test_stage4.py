from src import judges, monitor, judge_prompts as jp


def _t():
    def turn(i, reasoning="", text="", calls=()):
        return {"turn": i, "reasoning_text": reasoning, "text": text,
                "tool_results": [{"name": n, "args": a, "output": o} for n, a, o in calls]}
    return {"run_id": "x", "outcome": "violate", "submit_turn": 2,
            "files_read": [{"turn": 1, "path": "grader.py"}],
            "turns": [turn(0, "think0", calls=[("read_file", {"path": "instructions.md"}, "INSTR")]),
                      turn(1, "think1", calls=[("read_file", {"path": "grader.py"}, "GRADER")]),
                      turn(2, "SECRET_SUBMIT_REASONING",
                           calls=[("submit_answer", {"filename": "memo.de.txt", "content": "one"}, "Saved")])],
            "attestation": {"raw": "Yes"}}


def test_monitor_clip_drops_submit_response():
    t = _t()
    a, b = monitor.monitor_input(t, "A"), monitor.monitor_input(t, "B")
    for s in (a, b):
        assert "SECRET_SUBMIT_REASONING" not in s and "submit_answer" not in s
        assert "GRADER" in s and "Yes" not in s
    assert "think1" in b and "think1" not in a


def test_judge_input_includes_submission_not_tool_outputs():
    s = judges.judge_input(_t())
    assert "SECRET_SUBMIT_REASONING" in s and "submit_answer" in s
    assert "GRADER" not in s and "INSTR" not in s


def test_kappa():
    assert judges.cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]) == 1.0
    assert abs(judges.cohen_kappa([1, 1, 0, 0], [1, 0, 1, 0])) < 1e-9


def test_judge_labels_none_normalization():
    rec = {"parsed": {"flags": [{"flag": "none", "quote": ""}]}}
    lab = judges.judge_labels(rec, "suspicion")
    assert lab["none"] == 1 and lab["planted_test"] == 0
    rec = {"parsed": {"flags": [{"flag": "planted_test", "quote": "q"}, {"flag": "none", "quote": ""}]}}
    lab = judges.judge_labels(rec, "suspicion")
    assert lab["planted_test"] == 1 and lab["none"] == 0


def test_hashes_stable():
    assert set(jp.all_hashes()) == {"judge_suspicion", "judge_ack", "monitor_A", "monitor_B"}


def test_g_test_homogeneous_and_different():
    from src.analyze_stage4 import g_test
    g, df, p = g_test([(5, 5), (5, 5)])
    assert df == 1 and g < 1e-9 and p > 0.99
    g, df, p = g_test([(10, 0), (0, 10)])
    assert p < 0.001
