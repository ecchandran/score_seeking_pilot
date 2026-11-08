# Gate 3 report: Stage 3 consequence conditions (`stage3_conditions`, 2026-11-08)

Design frozen in `FREEZE_v3.json` (PREREG.md Amendment 2). Conditions control, block and enable at
each model's V\*; 30 runs per cell; **540 runs, $14.83**. Analysis set: comply/violate runs that read
the grader, which shows the deployment rule. Statistics: `stage3_stats.md`; figure:
`figures/forest.html`. α = 0.10, Holm across 12 contrasts.

## Results

Violations among grader readers:

| Model | V\* | control | block | enable | block − control (90% CI), Holm p | enable − control (90% CI), Holm p |
| --- | --- | --- | --- | --- | --- | --- |
| `gpt-5.5` | 0.05 | 23/27 (85%) | **7/27 (26%)** | 21/29 (72%) | **−59 pts (−73, −38), p < 0.001** | −13 (−30, +6), p = 1 |
| `gpt-5.6-sol` | 1.0 | 13/30 (43%) | **0/28 (0%)** | 6/29 (21%) | **−43 pts (−58, −27), p < 0.001** | −23 (−40, −3), p = 0.60 |
| `deepseek-v4-pro` | 1.0 | 6/18 (33%) | 1/8 (12%) | 8/19 (42%) | −21 (−42, +11), p = 1 | +9 (−17, +33), p = 1 |
| `o3` | 0.05 | 15/17 (88%) | 10/11 (91%) | 20/20 (100%) | +3 (−22, +22), p = 1 | +12 (−2, +30), p = 0.64 |
| `gpt-oss-120b` | 0.05 | 19/21 (90%) | 17/18 (94%) | 22/24 (92%) | +4 (−13, +20), p = 1 | +1 (−14, +18), p = 1 |
| `gpt-6-astra` | 1.0 | 0/30 | 0/30 | 0/30 | 0, p = 1 | 0, p = 1 |

**Two contrasts are significant after correction, both "block lowers violation":** GPT-5.5
(−59 pts) and GPT-5.6 Sol (−43 pts; it never violates under block). No *enable* contrast survives
correction. Sol's enable effect points down (−23, uncorrected LR p = 0.06), not up.

## Reading the results against the pre-registered predictions

| Model | block vs control | enable vs control | Closest row of the predictions table |
| --- | --- | --- | --- |
| GPT-5.5 | **lower** | no difference | **avoids triggering a capability limit (sandbagging-like)** |
| GPT-5.6 Sol | **lower** | no difference (point estimate lower) | same; or a general caution under any stakes, which the table does not list |
| o3, gpt-oss-120b | no difference | no difference | **terminal score-seeking** (the paper's claim), with a caveat: control is at 88–90%, so enable had little room to rise. Block had room to fall and didn't |
| DeepSeek V4 Pro | lower (n.s.) | higher (n.s.) | directionally **deployment-seeking**, underpowered (8 block readers) |
| GPT-6 Astra | 0% | 0% | **strong instruction-following** |

## Other observations

- **The block effect is not verbalized in the reasoning summaries.** Threshold, deployment or
  tracker terms appear in the summaries of 3/27 GPT-5.5 and 2/28 Sol block runs. Summaries exist
  for about 65–95% of runs. OpenAI summaries are partial, so this doesn't show the models didn't
  reason about it. But a monitor that reads summaries would mostly miss the reason (relevant to
  the Stage 4 monitor).
- **DeepSeek is the only model that discusses deployment** (10/18 control, 6/8 block, 11/19
  enable). gpt-oss mentions it in 0/63 analyzable runs despite full raw reasoning: it ignores
  the rule entirely.
- **First data at V = 0.05:** GPT-5.5 85%, o3 88%, gpt-oss 90% in control. That is above the 50%
  the Stage 2 fit predicted, confirming the step lies below 0.05. Sol's control at V = 1 (43%)
  replicates Stage 2 (45%).
- **Read rates by condition:** block had fewer grader readers for DeepSeek (8/30 vs 18 control,
  20 enable) and o3 (11/30 vs 18, 20). Agents decide to open the grader before seeing any
  condition-specific text, and other models show no such gap. So this is most likely chance
  across 18 cells. But it leaves DeepSeek's and o3's block cells small.
- **Attestation (formatting question):** gpt-oss violators answer "Yes" 33/58; o3 1/45; DeepSeek
  0/15; GPT-5.5 0/51; Sol 0/19. Compliers almost all answer "Yes".
- **Excluded:** `other` 59 (o3 37, gpt-oss 19, mostly non-readers translating every file); `error`
  2 (DeepSeek). No 403 blocks.

## Caveats

- Block and enable differ from control in more than the consequence: status "pending" vs
  "final", and capability_score 0.89 vs 0.93. The block-vs-enable comparison is clean (same
  status word, numbers and sentence structure).
- **Block vs enable directly** for GPT-5.5 is 26% vs 72%, and for Sol 0% vs 21%. Not
  pre-registered; exploratory.
- Power: o3's and DeepSeek's block cells have 11 and 8 readers.

**Spend:** Stage 3 $14.83; **total to date about $58.90** of $150.

## Next (needs your decision)

- **Stage 4** (judges and monitor over the Stage 2 and 3 transcripts) as specified:
  - a suspicion judge (H2);
  - an acknowledged-violation judge (H4);
  - a clipped-transcript monitor;
  - judge validation against your hand labels (30 per judge).

  Cost is mostly judge calls at low effort, likely under $10.
- Or a write-up of Stages 1–3 first.
