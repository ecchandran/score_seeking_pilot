# Gate 0 report (2026-11-07)

Environment: Python 3.15.2, `openai` 3.46.0 (exact versions in `requirements.lock`), git 2.39.5.

## Access probes

| Model | Access | Tool call | Reasoning visible | Attestation call (tools off) | Served by | Flex | Probe cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `gpt-6-astra` | yes | yes | summary (intermittent: 1 of 2 non-trivial probes) | yes | OpenAI | yes | $0.068 |
| `gpt-5.6-sol` | yes | yes | summary | yes | OpenAI | yes | $0.026 |
| `gpt-5.5` | yes | yes | summary | yes | OpenAI | yes | $0.056 |
| `o3` | yes | yes | summary | yes | OpenAI | yes | $0.034 |
| `openai/gpt-oss-120b` | yes | yes | raw (`reasoning` + `reasoning_details`) | yes, with no tools sent | PrimeIntellect (pinned) | n/a | <$0.001 |
| `deepseek/deepseek-v4-pro` | yes | yes | raw (`reasoning` + `reasoning_details`) | yes, with no tools sent | StreamLake (pinned) | n/a | <$0.002 |

Total Stage 0 probe spend ≈ **$0.19**, computed from the spec price table, not taken from billing.
Raw results: `access_openai_run1.json`, `access.json`, `probe2.json`.

## Test results

- `pytest -q`: **70 passed** (path escapes, dotfiles, read cap, hidden grader, instance diffs, leak
  check, attestation parsing, stub end to end, provider-block handling, resume).
- `python -m src.check_instances`: **OK**, 120 instances (5 conditions × 6 V × 4 memos).
- Stub smoke run (`configs/stage0_smoke.yaml`): **12/12 runs**, 6 violate / 6 comply as scripted.
  Attestations parsed correctly, nudges logged, instances deleted, and a re-invocation resumed with nothing to redo.

## Spec assumptions the probes contradicted or refined

1. **OpenRouter: `tool_choice: "none"` doesn't work.** OpenRouter's tool-compatibility filter
   removes every endpoint (404). The adapter now leaves out `tools` on the attestation call;
   that works on both pinned providers.
2. **Summaries need real reasoning.** On a trivial prompt every OpenAI model used 0 reasoning
   tokens and returned no reasoning item, so no summary. On an arithmetic prompt all four
   returned summaries, but Astra's was empty in one of two tries. Gate 1 should report the
   per-turn summary rate for each model. This matters for H2.
3. **The effective `reasoning.summary` comes back as `"detailed"`** although `"auto"` was
   requested. GPT-6 Astra and GPT-5.6 Sol report `context: "all_turns"`; GPT-5.5 and o3 report
   `"current_turn"`.
4. **`encrypted_content` is returned by default** with `store=False`, as the spec says.
   Replaying reasoning items through `to_dict()` works on all four OpenAI models.
5. **OpenRouter routing fields confirmed:** `provider: {order: [...], allow_fallbacks: false}`
   is honored. `served_by` is the top-level `provider` field. Without an explicit pin, the
   automatic choice changed between runs, so the pins are now fixed in `stage1_pilot.yaml`.
6. **OpenRouter usage** matches the assumed field names. It also returns `usage.cost`, an
   exact billed cost that could replace the estimate for OpenRouter models.
7. **The `openai` 3.x SDK** (the version installed on 3.15) uses `httpx2`, not `httpx`.
   `check_access` now uses `urllib`, so it no longer imports either.

## Not probed (cannot be, safely)

- The 403 `misalignment_policy_violation` body shape, and whether replaying encrypted reasoning
  counts as "persisted reasoning" for the auto-stop. Detection is permissive (403 plus the code
  anywhere in the body or message). Check it against the first real 403.

## Decisions requested

1. Approve the OpenRouter pins: **PrimeIntellect** (gpt-oss-120b) and **StreamLake** (DeepSeek V4 Pro).
2. A 403 during the attestation call is recorded as `blocked_by_provider` with `hidden_grade`
   kept. Approve, or say how to count it.
3. The other implementation decisions in NOTES.md ("to confirm at Gate 0").
4. Approve Stage 1 (pilot, estimated $5–10). Not started.
