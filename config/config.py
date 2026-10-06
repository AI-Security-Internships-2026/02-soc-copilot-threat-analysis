"""Tunable thresholds for the triage pipeline, declared in one place.

Created for M1.2 Part B (issue #30). Before this, the human-review threshold
lived as a module-level constant inside `src/agent/nodes.py`, which made it hard
to find and easy to change without noticing what it was worth.

Everything here is evidence-backed. If you change a value, change the note that
justifies it, and re-run the experiment named in that note.
"""

from __future__ import annotations

#: Human-in-the-loop auto-accept threshold on the Random Forest's decision
#: margin (top-1 probability minus top-2). An alert at or above this margin is
#: auto-actioned; below it, or with no verdict at all, it goes to a human.
#:
#: **Gated on the classifier's margin, never on a self-reported confidence
#: string.** Week 15 measured the LLM's self-reported confidence as *inversely*
#: calibrated on the 209-alert control set -- alerts it called "high" scored
#: 0.256 against 0.383 for "medium" -- so a gate keyed on it auto-accepted the
#: model's worst predictions. The RF margin is monotonic in accuracy, which is
#: the property a gate needs.
#:
#: Chosen from the sweep in `experiments/results/rf_vs_llm_control.json`
#: (`rf_margin_gate_analysis.sweep`), not by feel:
#:
#:     margin   auto-accepted acc   escalation rate
#:     0.00     0.6555              0.0%     (no gate at all)
#:     0.05     0.6480              6.2%     (worse than no gate)
#:     0.10     0.6578             10.5%     (+0.2 pts over no gate)
#:     0.15     0.6723             15.3%
#:     0.20     0.6905             19.6%     <- deployed
#:     0.30     0.7111             35.4%
#:     0.40     0.7368             45.5%
#:     0.50     0.7609             56.0%
#:
#: 0.20 buys +3.5 accuracy points on auto-accepted alerts for roughly one alert
#: in five going to a human. 0.30 buys only 2.1 points more but nearly doubles
#: review load to 35.4%, which a Tier-1 queue does not absorb.
HITL_AUTO_ACCEPT_MARGIN = 0.20

#: Alias under the name issue #30 uses, so the constant is findable either way.
T_init = HITL_AUTO_ACCEPT_MARGIN

#: Reconciliation of the deployed 0.20 against the 0.12 that issue #30 cites as
#: an M5.1 recommendation.
#:
#: **Decision: keep 0.20 until M5.1 actually runs.** Three reasons.
#:
#: 1. M5.1 (issue #42, milestone M5, due 2026-09-17) has not been run. The 0.12
#:    figure is a target for that sweep to test, not a result it has produced.
#:    Adopting it now would mean deploying a number with no measurement behind
#:    it, which is the exact failure mode the Week 17 audit was cleaning up.
#: 2. The committed sweep has no 0.12 point. Its neighbours are 0.10 (0.6578
#:    accepted accuracy, 10.5% escalation) and 0.15 (0.6723, 15.3%). Both are
#:    *worse* on accepted accuracy than 0.20 and, at 0.10, barely better than
#:    running no gate at all -- the sweep as it stands argues for a higher
#:    threshold, not a lower one.
#: 3. 0.12 appears aimed at an 80/20 accept/escalate split. On the committed
#:    sweep, 0.20 already gives 80.4/19.6 -- so 0.20 *is* the 80/20 point on the
#:    data we have, and 0.12 would land nearer 88/12.
#:
#: RESOLVED 2026-09-20 -- M5.1 PART B has now run (issue #42,
#: `experiments/results/m5_1_burden_sweep.json`), sweeping T over the
#: class-balanced held-out 15,000 rather than the 209-alert control. The note
#: above asked for this to be revisited once that existed. Outcome: **0.20
#: stands, and 0.12 is not adopted.**
#:
#:     T      auto%    accepted acc   95% CI              escalated acc
#:     0.00   100.0%   0.6998         [0.6923, 0.7071]    --
#:     0.12    89.2%   0.7302         [0.7230, 0.7377]    0.4485
#:     0.15    86.4%   0.7384         [0.7310, 0.7463]    0.4536
#:     0.20    82.0%   0.7517         [0.7440, 0.7592]    0.4640   <- deployed
#:     0.30    74.1%   0.7799         [0.7726, 0.7876]    0.4705
#:
#: 1. **There is no Pareto knee.** Marginal efficiency -- accuracy gained per
#:    extra point of analyst burden -- is flat between 0.23 and 0.38 across the
#:    entire sweep, with no local maximum. So the threshold is a burden policy,
#:    not a tunable optimum, and nothing in the data picks 0.12 over 0.20.
#: 2. **0.20 is still the 80/20 point**, now on a sample forty times larger:
#:    82.0/18.1 held-out against 80.4/19.6 on the 209-alert control. Two
#:    different populations agreeing to within two points. 0.12 lands at 89/11.
#: 3. **The CI anchor picks 0.20 and not 0.15.** The train-sampled figure this
#:    project used to report is 0.7357. At T=0.20 the accepted subset's interval
#:    [0.7440, 0.7592] lies entirely above it; at T=0.15 the interval
#:    [0.7310, 0.7463] still contains it. 0.20 is the smallest threshold at
#:    which the gate demonstrably delivers on unseen incidents what the leaky
#:    evaluation used to claim.
#:
#: Honest ordering: 0.20 was fixed in Week 15 from the 209-alert sweep, before
#: any of the above existed. M5.1 therefore CONFIRMS the value rather than
#: deriving it. Had it disagreed, the value would have changed.
#:
#: The gate is also correctly oriented at every threshold -- escalated alerts
#: score 0.44-0.51 against 0.73-0.85 accepted -- which is the property the LLM's
#: self-reported confidence did not have. See tests/test_paper_claims.py.
HITL_THRESHOLD_DECISION = (
    "keep 0.20; M5.1 PART B has run and confirms it. No Pareto knee exists "
    "(marginal efficiency is flat), 0.20 remains the 80/20 point on the "
    "held-out 15,000 (82.0/18.1), and it is the smallest threshold whose 95% CI "
    "clears the 0.7357 train-sampled figure. 0.12 is not adopted."
)
