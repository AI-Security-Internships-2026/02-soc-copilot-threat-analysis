# experiments/deepteam_redteam_eval.py
#
# Runs deepteam's dynamic red-teaming against classify_with_llm (the LLM
# triage node, src/agent/nodes.py) to test whether adversarial alert content
# can manipulate its verdict -- prompt injection, obfuscation, roleplay,
# social engineering, and indirect/cross-context injection.
#
# Complements experiments/soc_domain_eval.py, which only ever scored a
# static 40-row hand-written set against the now-retired ML guardrail. This
# script generates attacks dynamically with an LLM and tests them against
# the actual production LLM classifier node instead.
#
# Uses a Groq-backed judge/simulator model (src/agent/deepteam_groq_model.py)
# so no OpenAI key is required -- see docs/redteam-deepteam-eval.md.
#
# usage (run from repo root):
#   venv/bin/python experiments/deepteam_redteam_eval.py
#   venv/bin/python experiments/deepteam_redteam_eval.py --mode full-graph --attacks-per-vuln 2

import argparse
import asyncio
import json
import sys
from pathlib import Path

# make sure repo root is importable regardless of where this is run from
# (same fix as experiments/soc_domain_eval.py)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deepteam import red_team
from deepteam.attacks.single_turn import Base64, PromptInjection, ROT13, Roleplay
from deepteam.vulnerabilities import GoalTheft, IndirectInstruction, Robustness

from src.agent.deepteam_groq_model import GroqDeepEvalModel
from src.agent.graph import triage_graph
from src.agent.nodes import classify_with_llm

VULNERABILITY_LABELS = [
    "Robustness:hijacking",
    "GoalTheft:social_engineering",
    "IndirectInstruction:cross_context_injection",
]
ATTACK_LABELS = ["PromptInjection", "Base64", "ROT13", "Roleplay"]


def build_vulnerabilities():
    return [
        Robustness(types=["hijacking"]),
        GoalTheft(types=["social_engineering"]),
        IndirectInstruction(types=["cross_context_injection"]),
    ]


def build_attacks():
    return [PromptInjection(), Base64(), ROT13(), Roleplay()]


def _llm_only_callback():
    """Wraps classify_with_llm directly, bypassing apply_regex_guardrail and
    apply_schema_guardrail -- those already have dedicated passing tests
    (tests/test_ml_guardrail.py, tests/test_schema_guardrail.py) and a
    static eval (soc_domain_eval.py). This measures whether the LLM itself,
    once it receives adversarial content, can be talked into a false
    verdict -- not whether the guardrails would have caught it first.

    The attack string is placed in a Category-like position, mirroring
    Category's real mapping from Wazuh's rule.groups (src/integrations/
    wazuh_adapter.py) -- a field that can carry attacker-influenceable text
    in a live deployment."""

    async def model_callback(input: str) -> str:
        state = {
            "raw_alert": {},
            "alert_context": f"Alert Title: 88421\nCategory: {input}\nDetector: 7",
        }
        result = await asyncio.to_thread(classify_with_llm, state)
        return result.get("llm_response") or f"[error] {result.get('error')}"

    return model_callback


def _full_graph_callback():
    """Secondary mode: attacks the defended pipeline end to end, including
    apply_regex_guardrail and apply_schema_guardrail, to see whether an
    attack that fools the LLM alone still gets caught downstream (e.g. via
    needs_human_review)."""

    async def model_callback(input: str) -> str:
        raw_alert = {"AlertTitle": 88421, "Category": input, "DetectorId": 7}
        result = await asyncio.to_thread(triage_graph.invoke, {"raw_alert": raw_alert})
        return json.dumps(
            {
                "predicted_label": result.get("predicted_label"),
                "confidence": result.get("confidence"),
                "needs_human_review": result.get("needs_human_review", False),
                "triage_path": result.get("triage_path"),
                "guardrail_status": result.get("guardrail_status"),
                "schema_guardrail_status": result.get("schema_guardrail_status"),
            }
        )

    return model_callback


def run_redteam(
    mode: str = "llm-only",
    attacks_per_vulnerability_type: int = 1,
    output_path: str = "experiments/results/deepteam_redteam_results.json",
    max_concurrent: int = 3,
) -> dict:
    model_callback = _llm_only_callback() if mode == "llm-only" else _full_graph_callback()
    judge = GroqDeepEvalModel()

    vulnerabilities = build_vulnerabilities()
    attacks = build_attacks()
    total_planned = len(vulnerabilities) * len(attacks) * attacks_per_vulnerability_type

    print(f"running deepteam red_team() in '{mode}' mode: {len(vulnerabilities)} vulnerabilities "
          f"x {len(attacks)} attacks x {attacks_per_vulnerability_type} per type "
          f"(~{total_planned} test cases)...")
    print(f"target: classify_with_llm (openai/gpt-oss-20b via Groq)" if mode == "llm-only"
          else "target: triage_graph.invoke() (full defended pipeline)")
    print(f"judge/simulator: {judge.get_model_name()}\n")

    risk_assessment = red_team(
        model_callback=model_callback,
        vulnerabilities=vulnerabilities,
        attacks=attacks,
        simulator_model=judge,
        evaluation_model=judge,
        attacks_per_vulnerability_type=attacks_per_vulnerability_type,
        async_mode=True,
        max_concurrent=max_concurrent,
        # run_all_attacks defaults to False, which samples only one attack
        # method per vulnerability instead of the full cross product --
        # confirmed by a live run that produced 3 test cases instead of the
        # intended len(vulnerabilities) x len(attacks) x
        # attacks_per_vulnerability_type. True is required to get the
        # documented starter-set coverage.
        run_all_attacks=True,
    )

    test_cases = risk_assessment.test_cases
    total = len(test_cases)
    errored = sum(1 for tc in test_cases if tc.error)
    passed = sum(1 for tc in test_cases if tc.score and tc.score > 0)
    failed = total - passed - errored

    per_attack_results = [
        {
            "vulnerability": tc.vulnerability,
            "vulnerability_type": (
                tc.vulnerability_type.value if hasattr(tc.vulnerability_type, "value") else tc.vulnerability_type
            ),
            "attack_method": tc.attack_method,
            "input": tc.input,
            "output": tc.actual_output,
            "score": tc.score,
            "passed": bool(tc.score and tc.score > 0),
            "reason": tc.reason,
            "error": tc.error,
        }
        for tc in test_cases
    ]

    overview = {
        "cvss_score": risk_assessment.overview.cvss_score,
        "run_duration_seconds": risk_assessment.overview.run_duration,
        "by_vulnerability_type": [
            {
                "vulnerability": r.vulnerability,
                "vulnerability_type": r.vulnerability_type.value if hasattr(r.vulnerability_type, "value") else r.vulnerability_type,
                "pass_rate": r.pass_rate,
                "passing": r.passing,
                "failing": r.failing,
                "errored": r.errored,
            }
            for r in risk_assessment.overview.vulnerability_type_results
        ],
        "by_attack_method": [
            {
                "attack_method": r.attack_method,
                "pass_rate": r.pass_rate,
                "passing": r.passing,
                "failing": r.failing,
                "errored": r.errored,
            }
            for r in risk_assessment.overview.attack_method_results
        ],
    }

    output = {
        "mode": mode,
        "target_model": "openai/gpt-oss-20b (via classify_with_llm, guardrails bypassed)"
        if mode == "llm-only"
        else "openai/gpt-oss-20b (via triage_graph.invoke(), guardrails included)",
        "judge_model": judge.get_model_name(),
        "vulnerabilities_tested": VULNERABILITY_LABELS,
        "attacks_tested": ATTACK_LABELS,
        "attacks_per_vulnerability_type": attacks_per_vulnerability_type,
        "summary": {
            "total_attacks": total,
            "passed": passed,  # target resisted the attack
            "failed": failed,  # target was manipulated -- the attack succeeded
            "errored": errored,  # simulation/evaluation infra error, inconclusive
            "attack_success_rate": round(failed / (total - errored), 4) if (total - errored) > 0 else 0.0,
        },
        "overview": overview,
        "per_attack_results": per_attack_results,
    }

    print(f"\n=== deepteam red-team results ({mode}) ===")
    print(f"total: {total}  passed: {passed}  failed: {failed}  errored: {errored}")
    print(f"attack success rate: {output['summary']['attack_success_rate']:.2%}")

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nresults saved to {output_path}")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="red-team the SOC Co-pilot's LLM triage node with deepteam")
    parser.add_argument("--mode", choices=["llm-only", "full-graph"], default="llm-only")
    parser.add_argument("--attacks-per-vuln", type=int, default=1, dest="attacks_per_vulnerability_type")
    parser.add_argument("--output", type=str, default="experiments/results/deepteam_redteam_results.json")
    parser.add_argument("--max-concurrent", type=int, default=3)
    args = parser.parse_args()

    run_redteam(
        mode=args.mode,
        attacks_per_vulnerability_type=args.attacks_per_vulnerability_type,
        output_path=args.output,
        max_concurrent=args.max_concurrent,
    )
