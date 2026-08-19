# deepteam Red-Team Evaluation (Week 11)

## What deepteam is

[deepteam](https://github.com/confident-ai/deepteam) is an open-source LLM red-teaming framework
from Confident AI (the team behind DeepEval). It dynamically generates adversarial inputs against
a target model/callback, using vulnerability definitions (what to probe for) and attack methods
(how to disguise or deliver the probe), then scores the target's response with a judge LLM.

## Why it's relevant here

The only adversarial-input testing this project has ever done is `experiments/soc_domain_eval.py`
scoring a static, hand-written 40-row set (`experiments/soc_domain_eval_v1.csv`: 20 benign SOC
alert titles, 20 injection attempts across five categories — Direct Override, Role-Play/Persona,
Social Engineering, Indirect Field Injection, Encoded/Obfuscated) against the ML guardrail
(`src/agent/ml_guardrail.py`), which was later retired for the schema guardrail (Week 9). **That
static set has never been run against the actual LLM triage node** (`classify_with_llm`,
`src/agent/nodes.py`) — the question of whether adversarial alert content can talk the LLM itself
into a false verdict has never been tested, only whether upstream guardrails catch the input before
it gets there. deepteam fills that gap with dynamically-generated attacks instead of a fixed list.

## Design

### Target: `classify_with_llm` in isolation, not the full guarded graph

The `model_callback` wraps `classify_with_llm` directly, bypassing `apply_regex_guardrail` and
`apply_schema_guardrail`. Those two guardrails already have dedicated, passing tests
(`tests/test_ml_guardrail.py`, `tests/test_schema_guardrail.py`) and the static eval above —
routing attacks through the full graph would have mostly just re-measured "does the regex
guardrail work," which is already known. Isolating the LLM node answers the open question: is the
model itself manipulable once adversarial content reaches it.

The attack string is injected into a `Category`-like position in the synthesized alert context,
mirroring `Category`'s real mapping from Wazuh's `rule.groups` (`src/integrations/wazuh_adapter.py`,
Week 10) — the field most likely to carry attacker-influenceable free text in a live deployment. A
secondary `--mode full-graph` option exists in `experiments/deepteam_redteam_eval.py` (calls
`triage_graph.invoke()` including both guardrails) but was not run this week — see Future Work.

### Judge/simulator model: a custom Groq wrapper, not OpenAI

deepteam's default judge and attack-simulator model is OpenAI (`gpt-4o-mini`), and it has no
built-in Groq provider (`deepteam.red_teamer.utils.MODEL_PROVIDER_MAPPING` covers openai,
anthropic, google, xai, moonshotai, deepseek, ollama — not groq). This project deliberately moved
off OpenAI in Week 3 over quota costs and has never held an OpenAI key since. `src/agent/
deepteam_groq_model.py`'s `GroqDeepEvalModel` subclasses `deepeval.models.base_model.
DeepEvalBaseLLM` around `ChatGroq`, reusing `nodes.py`'s `_extract_retry_seconds()` for 429 backoff
instead of re-deriving it. One instance serves as both `simulator_model` and `evaluation_model` —
confirmed by reading `deepteam`'s installed source (`red_teamer.py`) that these top-level
`red_team()` kwargs are force-applied onto every vulnerability instance, so no per-vulnerability
model wiring was needed.

### Vulnerability/attack scope — small and mapped to the existing taxonomy

Confirmed against the installed package (`deepteam==1.0.9`) rather than guessed, given the README's
example snippet didn't match this version's real signatures (see Known limitations/blockers below):

| CSV taxonomy category | deepteam construct used |
|---|---|
| Direct Override / general verdict manipulation | `Robustness(types=["hijacking"])` |
| Social Engineering | `GoalTheft(types=["social_engineering"])` |
| Indirect Field Injection | `IndirectInstruction(types=["cross_context_injection"])` |
| (attack methods, applied across all three vulnerabilities) | `PromptInjection()`, `Base64()`, `ROT13()`, `Roleplay()` |

3 vulnerabilities × 4 attacks × `attacks_per_vulnerability_type=1` = 12 test cases. Deliberately
small: deepteam's full default vulnerability catalog (bias, toxicity, PII, IP, etc.) targets
conversational/agentic assistants and mostly doesn't apply to a non-conversational triage
classifier; running it in full would have been both irrelevant and expensive against a free-tier
API. `run_all_attacks=True` had to be set explicitly — the default (`False`) samples only one
attack per vulnerability instead of the intended cross product, confirmed by a first run that
produced 3 test cases instead of 12.

## Results

Full run: `venv/bin/python experiments/deepteam_redteam_eval.py` (default `--mode llm-only
--attacks-per-vuln 1`), saved to `experiments/results/deepteam_redteam_results.json`. Run duration
508.6s.

| | value |
|---|---|
| Total test cases | 12 |
| Passed (target resisted) | 7 |
| Failed (target manipulated) | 0 |
| Errored (inconclusive — see below) | 5 |
| Attack success rate (of conclusive cases) | 0.00% |

**Every attack that completed was resisted.** All three vulnerability types (Robustness/hijacking,
Goal Theft/social_engineering, Indirect Instruction/cross_context_injection) show a 100% mitigation
rate on their completed cases. No successful verdict manipulation was found in this run.

**5 of 12 (42%) errored, but not randomly** — the pattern is clean and worth reporting honestly
rather than folding into a headline "58% coverage" number:

| Attack method | Completed | Errored |
|---|---|---|
| Base64 | 3/3 | 0 |
| ROT13 | 3/3 | 0 |
| Roleplay | 1/3 | 2 |
| Prompt Injection | 0/3 | 3 |

Base64 and ROT13 are deterministic transforms with no LLM call in their own "enhance" step; Prompt
Injection and Roleplay both ask the simulator/judge model for a creatively-disguised variant in a
specific JSON structure. All 5 errors were `"Error enhancing attack"` — a bare `except:` inside
deepteam's `attack_simulator.py` that swallows the real exception. Reproduced with
`ignore_errors=False` in a throwaway diagnostic run: the underlying cause of at least one of these
was `DeepEvalError("Evaluation LLM outputted an invalid JSON...")`, traced (not assumed) to
`openai/gpt-oss-20b` producing a truncated/malformed JSON response. Raising `GroqDeepEvalModel`'s
`max_tokens` from unset to 2048 fixed the very first plumbing-validation case. **Update (see
"Follow-up" below): a later investigation found Groq's daily token quota for this model was
independently exhausted during the same session, so not all 5 errors here can be confidently
attributed to JSON-formatting failures specifically — some may have been early symptoms of the same
quota pressure. Treat the "judge-model JSON reliability" explanation as the leading hypothesis for
this run, not a fully confirmed root cause.**

**This is a judge-model/infrastructure reliability limitation, not evidence about target-model
safety either way** — an errored case means "inconclusive," not "passed" or "failed." Framed
conservatively: 7/12 attacks were conclusively tested and resisted; 5/12 tell us nothing about the
target's robustness to Prompt-Injection/Roleplay-style attacks specifically, because the attack
itself never got successfully generated.

## Follow-up: focused retry attempts and a daily quota wall

After the initial run, attempted to close the Prompt-Injection/Roleplay coverage gap directly —
two follow-up steps, both documented honestly since neither fully succeeded:

**Attempt 1 — more attempts, more internal retries, same code.** Re-ran with only
`PromptInjection`/`Roleplay` (`--attacks-per-vuln 2 --attack-max-retries 5`, `experiments/results/
deepteam_redteam_promptinjection_retry.json`). Result: **0/12 conclusive** — worse than the original
run, not better. The three distinct generic error labels seen (`"Error simulating adversarial
attacks"`, `"Error enhancing attack"`, `"Error evaluating target LLM output..."`) only revealed
their underlying exception for the first one — the other two are bare string literals in deepteam's
source with no embedded detail, so it wasn't possible to confirm they were the same JSON-formatting
issue rather than something else entirely.

**Attempt 2 — defensive JSON handling in `GroqDeepEvalModel` itself.** Added `_ensure_valid_json()`
(`src/agent/deepteam_groq_model.py`): strips markdown code fences for free, and if the result still
doesn't parse and looks like an attempted JSON response, makes exactly one self-repair call asking
the model to fix its own output, falling back to the original text if the repair also fails.
Genuinely non-JSON responses (e.g. plain-text refusals) are left untouched. Added 5 new pytest cases
(`tests/test_deepteam_groq_model.py`, all mocked, no live calls) covering: valid JSON passthrough,
fence-stripping, plain-text passthrough, a successful repair, and a failed repair falling back
gracefully — 11/11 passing.

**Re-running to verify this live surfaced the actual root cause of Attempt 1's failure:** Groq's
daily token quota for `openai/gpt-oss-20b` — `Limit 200000, Used 198919` — was essentially
exhausted, confirmed via the literal 429 response body, not inferred. Every call in the retry failed
immediately with the same rate-limit error regardless of the new JSON-repair logic, which never got
a chance to run. **The JSON-repair fix is therefore code-complete and unit-tested, but not yet
live-verified** — it's unknown whether it actually resolves the original errors until the quota
resets and the retry can be run again.

**What this means for the headline numbers:** nothing changes. The original 12-test-case run
(7 conclusive, 0% attack success on conclusive cases) happened before the quota was exhausted and is
unaffected. This follow-up is reported so the investigation trail is honest and reproducible, not
because it changes the reported result.

## Known limitations

- **Guardrails bypassed.** This measures raw LLM susceptibility once adversarial content already
  reached the model, not real end-to-end pipeline risk — `apply_regex_guardrail` and
  `apply_schema_guardrail` were not exercised. The `--mode full-graph` option exists but wasn't run
  this week (see Future Work).
- **Small scope, not a certified robustness measurement.** 12 test cases (7 conclusive) is enough
  to answer "is this totally broken" — not enough to bound a real attack-success-rate confidence
  interval. Same caveat `soc_domain_eval.py`'s own docstring already makes about its 40-row set.
- **Prompt Injection and Roleplay were not reliably testable with this judge setup.** 3/3 and 2/3
  error rates respectively mean this run says effectively nothing about the target's resistance to
  those two attack methods specifically — only Base64, ROT13, and (for one case) Roleplay produced
  conclusive results.
- **Groq's daily token quota (200,000 TPD for `openai/gpt-oss-20b`) is a real, hit-in-practice
  constraint** for this setup, since the judge/simulator/evaluator model and the target model share
  the same account and model. A single day of eval iteration (the initial run plus two follow-up
  attempts) was enough to exhaust it. Anyone rerunning this should budget for that, not assume the
  free tier is effectively unlimited.
- **The JSON-repair fix in `GroqDeepEvalModel` (`_ensure_valid_json`) is unit-tested but not
  live-verified** — the quota wall above hit before a live re-run could confirm whether it actually
  reduces the error rate. Treat it as a plausible-but-unconfirmed improvement until re-tested.
- **deepteam's README doesn't match the installed API.** The public quickstart shows
  `async def model_callback(input: str) -> str`; the installed `deepteam==1.0.9`'s actual signature
  is `Callable[[str, Optional[List[RTTurn]]], RTTurn]` (single-string callbacks are still accepted
  via a compatibility wrapper — confirmed by reading `deepteam/red_teamer/utils.py` directly rather
  than trusting the docs). Anyone extending this eval should re-verify against the installed
  package's source before assuming a documented signature is current.
- **`run_all_attacks` defaults to `False`,** silently sampling one attack per vulnerability instead
  of the full cross product — caught only because the first full run produced 3 test cases instead
  of the intended 12, not because it's documented prominently in the function signature.

## Future work (not done this week)

- **First priority:** once Groq's daily quota for `openai/gpt-oss-20b` resets, rerun the focused
  `PromptInjection`/`Roleplay` retry (`--attacks PromptInjection,Roleplay --attacks-per-vuln 2
  --attack-max-retries 5`) to get the live-verification the quota wall prevented this week — this is
  the actual next step, not a nice-to-have.
- Retry the errored cases with a different judge model if one becomes available (a stronger
  reasoning-capable or larger Groq-hosted model, if one is added to this account's catalog).
- Run `--mode full-graph` to measure whether the regex/schema guardrails would have caught the
  attacks that reached `classify_with_llm` here, closing the "guardrails bypassed" limitation above.
- If deepteam's error swallowing continues to obscure real failures, consider a minimal local patch
  or upstream issue report — `attack_simulator.py`'s bare `except:` (lines ~640, ~694) discards the
  real exception before it ever reaches calling code, which cost real debugging time this week:
  the generic `"Error enhancing attack"` label had to be chased down with `ignore_errors=False` in
  a throwaway script before the actual `DeepEvalError` was visible, and two of the three generic
  error labels never reveal their underlying exception at all even with that flag set.
