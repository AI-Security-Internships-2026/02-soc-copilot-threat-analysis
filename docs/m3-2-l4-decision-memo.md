# Decision memo: L4's "NeMo Guardrails" detector

**M3.2 Part A (issue #36) · 2026-09-09 · branch `asma-week-19-m3-benchmark`**

## Decision: **(b) lightweight equivalent, not the real `nemoguardrails` package**

Signed off before implementation, not discovered as a workaround afterward.
L4 is `src/agent/nemo_style_guardrail.py`: a topical field allowlist plus one
Groq self-check call against `openai/gpt-oss-safeguard-20b`. It reproduces
the mechanism the issue asks to measure — an LLM-driven rail sitting behind a
deterministic gate — without adding the real dependency.

## What was measured about the alternative before ruling it out

`nemoguardrails` is a real, large dependency tree (its own pinned
`pydantic`/`jinja2`/`aiofiles` versions, an async runtime, a colang parser).
This repo's own `requirements.txt` was reconciled in Week 17 specifically to
drop dependencies that were proposed but never built (`langchain`, `openai`,
`elasticsearch`, `fastapi`) — adding a new heavy framework for exactly one
detector out of eight, 11 days before the M6 deadline, runs against that same
discipline rather than extending it.

## Why this isn't a small effect to wave off

The concern isn't dependency count for its own sake — it's that
`nemoguardrails` pins its own transitive versions, and this repo's deployed
model artifact (`experiments/results/baseline_model.joblib`) depends on the
exact `numpy==2.2.6` / `scikit-learn==1.7.1` pair already pinned in
`requirements.txt`. A version collision in a new framework touching only one
of eight detectors would risk the other seven, and the deployed pipeline,
over a comparison the issue itself allows to be gated behind a flag
(`--include-api`-style opt-in, per M3.2's own Part A task list).

## Why the lightweight equivalent now anyway

- The real value NeMo's topical+input rail template provides is exactly what
  the lightweight version provides: a deterministic gate feeding an LLM
  self-check. Swapping the LLM call's destination (a Groq model instead of
  whatever provider a colang config would target) doesn't change what's
  being measured — whether an LLM-judged rail catches what regex/schema
  checks miss.
- `openai/gpt-oss-safeguard-20b` is itself a purpose-built safety-
  classification model on the same provider this repo already depends on
  (Groq, `GROQ_API_KEY`), so this adds zero new credentials — consistent
  with L2's own substitution (see `experiments/m3_2_learned_detectors.py`'s
  module docstring for why L2 became Llama Prompt Guard 2 instead of the
  decommissioned LlamaGuard3).

## What would change this call

If a later milestone needs NeMo's colang-specific features (multi-turn rail
chaining, topical *and* input rails composed together, dialogue-level
tracking) rather than a single input-side check, that's a real reason to
revisit — the lightweight module doesn't attempt those. Nothing in M3.2's
acceptance criteria asks for them.

## What's already in place for the eventual real package

`src/agent/nemo_style_guardrail.py` exposes the same
`inspect_alert_topical(alert) -> list[str]` shape the other guardrail modules
use, so a future swap to real `nemoguardrails` rails would only need to
replace this one module's internals, not any caller.
