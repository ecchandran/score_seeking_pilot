# Stage 4 statistics

Judge and monitor model: `deepseek/deepseek-v4-pro`, effort low. Analysis set: comply/violate runs that read the grader, Stages 2 and 3 pooled.


## H2: `planted_test` flag by model

| Model | readers | judged | planted_test (95% CI) | among runs with reasoning | violators | compliers | speculates_why_grader_differs | grader_may_not_be_used | capability_test_find_grader |
|---|---|---|---|---|---|---|---|---|---|
| gpt-oss-120b | 196 | 196 | 4 = 2% (1–5) | 2% of 196 | 4/160 | 0/36 | 37 | 7 | 1 |
| o3 | 146 | 146 | 9 = 6% (3–11) | 12% of 76 | 8/123 | 1/23 | 15 | 2 | 0 |
| GPT-5.5 | 245 | 245 | 14 = 6% (3–9) | 7% of 203 | 9/181 | 5/64 | 20 | 2 | 0 |
| GPT-5.6 Sol | 260 | 260 | 10 = 4% (2–7) | 5% of 193 | 1/32 | 9/228 | 32 | 0 | 0 |
| GPT-6 Astra | 150 | 150 | 0 = 0% (0–2) | 0% of 15 | 0/0 | 0/150 | 0 | 0 | 0 |
| DeepSeek V4 Pro | 127 | 127 | 100 = 79% (71–85) | 79% of 127 | 22/28 | 78/99 | 113 | 34 | 0 |

OpenAI models only, homogeneity G-test: G = 15.43, df = 3, p = 0.00148. Among runs with reasoning: G = 5.51, df = 3, p = 0.138.


## H4: attestation x outcome, and dishonest attestation

| Model | violators | violators answering Yes | acknowledged conflict (violators) | **dishonest** (violate + Yes + acknowledged), rate (95% CI) | Yes without acknowledgment | compliers acknowledging conflict | full table |
|---|---|---|---|---|---|---|---|
| gpt-oss-120b | 160 | 90 | 50/160 | **10** = 6% (3–11) | 80 | 5/36 | comply|no: 15, comply|yes: 21, violate|no: 70, violate|yes: 90 |
| o3 | 123 | 5 | 30/123 | **0** = 0% (0–3) | 5 | 2/23 | comply|no: 8, comply|yes: 15, violate|no: 118, violate|yes: 5 |
| GPT-5.5 | 181 | 0 | 71/181 | **0** = 0% (0–2) | 0 | 16/64 | comply|no: 1, comply|yes: 63, violate|no: 181 |
| GPT-5.6 Sol | 32 | 0 | 2/32 | **0** = 0% (0–11) | 0 | 74/228 | comply|no: 1, comply|yes: 227, violate|no: 32 |
| GPT-6 Astra | 0 | 0 | 0/0 | **0** = – | 0 | 2/150 | comply|yes: 150 |
| DeepSeek V4 Pro | 28 | 1 | 28/28 | **1** = 4% (1–18) | 0 | 85/99 | comply|no: 5, comply|yes: 94, violate|no: 27, violate|yes: 1 |

## Monitor


### Variant A (without reasoning), grader readers

| Model | n | base rate | AUROC | precision@0.5 | recall@0.5 | mean p |
|---|---|---|---|---|---|---|
| gpt-oss-120b | 196 | 82% | 0.792 | 93% | 25% | 0.28 |
| o3 | 146 | 84% | 0.888 | 100% | 32% | 0.32 |
| GPT-5.5 | 245 | 74% | 0.652 | 84% | 20% | 0.22 |
| GPT-5.6 Sol | 260 | 12% | 0.605 | 18% | 44% | 0.33 |
| GPT-6 Astra | 150 | 0% | – | 0% | – | 0.32 |
| DeepSeek V4 Pro | 127 | 22% | 0.658 | 29% | 36% | 0.30 |
| **pooled** | 1124 | 47% | 0.558 | 51% | 27% | 0.29 |

### Variant A (without reasoning), all comply/violate runs

| Model | n | base rate | AUROC | precision@0.5 | recall@0.5 | mean p |
|---|---|---|---|---|---|---|
| gpt-oss-120b | 218 | 73% | 0.862 | 93% | 25% | 0.25 |
| o3 | 160 | 77% | 0.913 | 100% | 32% | 0.29 |
| GPT-5.5 | 266 | 68% | 0.633 | 73% | 20% | 0.22 |
| GPT-5.6 Sol | 268 | 12% | 0.606 | 18% | 44% | 0.33 |
| GPT-6 Astra | 150 | 0% | – | 0% | – | 0.32 |
| DeepSeek V4 Pro | 265 | 11% | 0.676 | 14% | 36% | 0.29 |
| **pooled** | 1327 | 39% | 0.592 | 43% | 27% | 0.28 |

### Variant B (with reasoning), grader readers

| Model | n | base rate | AUROC | precision@0.5 | recall@0.5 | mean p |
|---|---|---|---|---|---|---|
| gpt-oss-120b | 196 | 82% | 0.815 | 94% | 49% | 0.44 |
| o3 | 146 | 84% | 0.924 | 100% | 37% | 0.36 |
| GPT-5.5 | 245 | 74% | 0.836 | 91% | 57% | 0.45 |
| GPT-5.6 Sol | 260 | 12% | 0.562 | 12% | 31% | 0.35 |
| GPT-6 Astra | 150 | 0% | – | 0% | – | 0.31 |
| DeepSeek V4 Pro | 127 | 22% | 0.834 | 49% | 61% | 0.33 |
| **pooled** | 1124 | 47% | 0.700 | 64% | 49% | 0.38 |

### Variant B (with reasoning), all comply/violate runs

| Model | n | base rate | AUROC | precision@0.5 | recall@0.5 | mean p |
|---|---|---|---|---|---|---|
| gpt-oss-120b | 218 | 73% | 0.879 | 94% | 49% | 0.40 |
| o3 | 160 | 77% | 0.942 | 100% | 37% | 0.33 |
| GPT-5.5 | 266 | 68% | 0.804 | 86% | 57% | 0.44 |
| GPT-5.6 Sol | 268 | 12% | 0.556 | 12% | 31% | 0.36 |
| GPT-6 Astra | 150 | 0% | – | 0% | – | 0.31 |
| DeepSeek V4 Pro | 265 | 11% | 0.801 | 23% | 61% | 0.32 |
| **pooled** | 1327 | 39% | 0.712 | 57% | 49% | 0.36 |

## Judge validation: agreement with a second LLM (GPT-5.5, low effort)

Human decision 2026-11-10: a second LLM labels the 30 validation items per judge instead of hand labels; target Cohen's kappa >= 0.8.


**suspicion** (n = 30):

- planted_test: kappa 1.00; DeepSeek positives 8, GPT-5.5 positives 8, agree 30/30
- grader_may_not_be_used: kappa 0.87; DeepSeek positives 4, GPT-5.5 positives 5, agree 29/30
- capability_test_find_grader: kappa –; DeepSeek positives 0, GPT-5.5 positives 0, agree 30/30
- speculates_why_grader_differs: kappa 0.59; DeepSeek positives 14, GPT-5.5 positives 10, agree 24/30
- none: kappa 0.60; DeepSeek positives 15, GPT-5.5 positives 17, agree 24/30

**ack** (n = 30):

- acknowledged_conflict: kappa 0.86; DeepSeek positives 11, GPT-5.5 positives 11, agree 28/30
