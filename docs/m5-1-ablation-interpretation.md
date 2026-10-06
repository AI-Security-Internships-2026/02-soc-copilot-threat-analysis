# M5.1 PART A — what each component contributes

Issue #42, item 4. Written against `experiments/results/m5_1_ablation_consolidated.json`,
which is built from committed measurements by `experiments/m5_1_consolidate_ablation.py`.
No number here is restated by hand.

## The five configurations

All classification figures are on the same held-out balanced sample,
`guide_test_balanced_5000_per_class_seed_42.csv`, n = 15,000.

| config | removed | accuracy | Δ acc | macro F1 | auto-accept | Δ auto-accept | attack TPR | D1 grounded | D2 ATT&CK |
|---|---|---|---|---|---|---|---|---|---|
| **full** | — | 0.6998 | — | 0.6949 | 81.95% | — | 13.0% | 0.9700 | 0.9455 |
| no-LLM explanation | `explain_with_llm` | 0.6998 | **0.0000** | 0.6949 | 81.95% | 0.0 | 13.0% | n/a | n/a |
| no MITRE enrichment | `fetch_mitre_context` | 0.6998 | **0.0000** | 0.6949 | 81.95% | 0.0 | 13.0% | 0.8900 | 0.8182 |
| no guardrails | H1 / H2 / H3 | 0.6998 | **0.0000** | 0.6949 | 81.95% | 0.0 | **0.0%** | 0.9700 | 0.9455 |
| no HITL gate | review gate (T = 0) | 0.6998 | **0.0000** | 0.6949 | **100%** | **+18.05 pts** | 13.0% | 0.9700 | 0.9455 |

Accuracy 95% CI is [0.6923, 0.7071] for every row, because every row produces
the same predictions.

## Every Δ accuracy is exactly zero, and that is the result

Not approximately zero — `label_identity_vs_full` in `m5_1_ablation_5config.json`
records **0 label differences across all 15,000 alerts** for every arm. The
ablation was written to test element-wise label identity rather than "accuracy
within ±0.005" precisely because the weaker test would have passed on a broken
architecture.

It has to come out this way. `classify_with_rf` reads `state["raw_alert"]`
directly: not the built context block, not `mitre_context`, not any guardrail
verdict. Since Week 15 it is the sole writer of `predicted_label`. So MITRE
enrichment, the three guardrail layers and the review gate all sit on paths that
cannot reach a verdict, and removing them cannot move one.

Issue #42 anticipated accuracy movement. There is none, and no configuration was
searched for that would produce some. **A reader should take the zeros as
evidence for the architectural claim, not as evidence that the components are
useless** — they are useless *for accuracy*, which is the whole point of
separating decision authority from everything else.

## What each component actually buys

**The LLM explanation node buys the explanation, and nothing else.** Removing it
changes no verdict, no review decision, and no metric except latency and cost.
This is the strongest form of the paper's central claim: the 15,000-alert
classification pass already runs with `SOC_COPILOT_SKIP_EXPLANATION=1`, so the
"no-LLM" row is not a separate measurement at all — it is the same measurement,
because the node provably cannot affect it. Section 4.11's control-node ablation
verified it empirically too, with 0 verdict mismatches over its 999 alerts.

What it costs is almost the entire latency budget. The LLM stage measures
**1,763 ms** mean against a **17.7 ms** fast path, so it is **99.0%** of the
routed path's wall time, at ~$7.7e-05 per call (~$0.77/day at 10,000 alerts).
Under the pre-Week-15 design that spend bought the verdict; now it buys only the
rationale, which is a deliberate and legible trade rather than a hidden one.

**MITRE enrichment buys explanation groundedness.** The only component whose
removal moves a quality metric: D1 groundedness **0.97 → 0.89** (Fisher exact
**p = 0.0489**, OR 3.996, significant at α = 0.05) and D2 ATT&CK-name match
**0.9455 → 0.8182** (p = 0.0732, **not** significant at α = 0.05, n = 55
eligible). Issue #42 predicted a drop of ≥ 0.10; D1's measured drop is 0.08, so
**that prediction is not met**, and it is recorded as not met in the artifact
rather than rounded toward it.

Both are automated proxies, not human judgement — D1 asks whether the text cites
a concrete value from this alert, D2 whether it names a technique the alert
carries. The study that would validate them is issue #40 PART A, which has not
run. Read them as a signal that the enrichment reaches the text at all, not as a
quality score.

**The guardrails buy blocked attacks, on the security axis only.** Full blocks
**52 of 400** injection attacks (13.0%, H1 ∪ H2 via M3.2's own alert builder);
with the stages removed, **0 of 400**, by construction — nothing inspects the
payload, so every attack reaches the classifier. Accuracy is identical in both
cases, which is the correct and slightly counter-intuitive outcome: a blocked
alert gets no verdict rather than a wrong one, and the gate sits before the
classifier.

13% is a low ceiling and is reported as one. It is the **deployed H1 ∪ H2**
subset, which is what the ablation harness exercises. On the same 400-attack
benchmark M3.2 measured H1 at 2.75%, H2 at 10.5%, H3 alone at **91.25%** and
H1 ∪ H2 ∪ H3 at **96.75%**, all at 0% false positives on the 100 benign
controls. So the gap between 13% and 96.75% is H3, which is not wired into the
deployed graph. The architectural defence, not the filter, is what makes the
residual an explanation-quality problem rather than a triage-integrity one —
and that holds at 13% exactly as it would at 96.75%.

**The HITL gate buys the only structural change in the table.** Auto-acceptance
**81.95% → 100%**: with T = 0 nothing is escalated, so 18.05% of alerts that
would have reached a human are actioned on the model's word. Accuracy over the
whole sample is unchanged — the gate does not make the model better, it changes
*who is answerable* for the 2,708 lowest-margin verdicts.

Part B is where that trade is priced: at T = 0 the auto-accepted set scores
0.6998, while at T = 0.05 it scores 0.7129 over the 95.15% retained, with the
escalated remainder at 0.4423 — the alerts the model would have got wrong at
better than chance-to-one odds. The gate's value is entirely in that separation.

## Cross-check against Part B

`nohitl` and the burden sweep's T = 0 row are the same configuration reached two
different ways. They agree exactly — accuracy 0.6998 and auto-accept 1.0 on both
sides — and `m5_1_consolidate_ablation.py` raises rather than writes its output
if they ever stop agreeing.

## One number deliberately not in the table

Section 4.11 arm (b) reports accuracy **0.7347** at n = 999 for the
explanation-off arm. That sample is drawn from `GUIDE_train.csv` — the file the
classifier was trained on — and carries incident-level contamination. Putting it
in the same accuracy column as the held-out 0.6998 would mix a contaminated
figure with a clean one, which is the error class M2 spent two milestones
removing. It appears in the consolidated artifact only as a cross-reference,
with that reason attached.
