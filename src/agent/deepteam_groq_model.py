# src/agent/deepteam_groq_model.py
#
# Wraps ChatGroq as a deepeval DeepEvalBaseLLM so deepteam's simulator and
# evaluation ("judge") models run on Groq instead of defaulting to OpenAI.
# deepteam has no built-in Groq provider (see
# deepteam.red_teamer.utils.MODEL_PROVIDER_MAPPING), and this project
# deliberately moved off OpenAI in Week 3 over quota costs -- see
# docs/redteam-deepteam-eval.md for the full rationale.

import asyncio
import re
import time

from deepeval.models import DeepEvalBaseLLM
from deepeval.models.llms.utils import trim_and_load_json
from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq

from src.agent.nodes import _extract_retry_seconds

MAX_RETRIES = 5


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _looks_like_attempted_json(text: str) -> bool:
    return "{" in text or "[" in text


def _is_valid_json(text: str) -> bool:
    try:
        trim_and_load_json(text)
        return True
    except Exception:
        return False


class GroqDeepEvalModel(DeepEvalBaseLLM):
    """DeepEvalBaseLLM adapter around ChatGroq, for use as deepteam's
    simulator_model / evaluation_model (and, indirectly, as the basis for
    the target model_callback -- see experiments/deepteam_redteam_eval.py)."""

    def __init__(
        self,
        model_name: str = "openai/gpt-oss-20b",
        temperature: float = 0,
        max_tokens: int = 2048,
    ):
        self.temperature = temperature
        self.max_tokens = max_tokens
        super().__init__(model=model_name)

    def load_model(self):
        # max_tokens is deliberately generous: openai/gpt-oss-20b is a
        # reasoning model, and deepteam's internal attack-enhancement/judge
        # prompts are long enough that a tight budget truncates the JSON
        # answer before it's complete (seen directly: DeepEvalError
        # "outputted an invalid JSON" during a live red_team() plumbing
        # check, traced to truncation, not a malformed model response).
        return ChatGroq(
            model=self.name, temperature=self.temperature, max_tokens=self.max_tokens
        )

    def generate(self, prompt: str) -> str:
        return self._invoke_with_retry(prompt)

    async def a_generate(self, prompt: str) -> str:
        return await asyncio.to_thread(self._invoke_with_retry, prompt)

    def get_model_name(self) -> str:
        return f"Groq/{self.name}"

    def _invoke_with_retry(self, prompt: str) -> str:
        raw = self._call_model(prompt)
        return self._ensure_valid_json(raw)

    def _call_model(self, prompt: str) -> str:
        """Mirrors classify_with_llm's retry-on-429 loop (src/agent/nodes.py),
        reusing its backoff parser instead of re-deriving it here."""
        last_error = None
        for _ in range(MAX_RETRIES):
            try:
                response = self.model.invoke([HumanMessage(content=prompt)])
                return response.content
            except Exception as exc:
                last_error = str(exc)
                if "rate_limit_exceeded" in last_error or "429" in last_error:
                    time.sleep(_extract_retry_seconds(last_error))
                    continue
                raise

        raise RuntimeError(f"Groq call failed after {MAX_RETRIES} attempts: {last_error}")

    def _ensure_valid_json(self, raw: str) -> str:
        """deepteam/deepeval frequently expect strict JSON back from the
        judge model, at three separate pipeline stages (base attack
        simulation, attack enhancement, and target-output evaluation --
        confirmed live during Week 11's red-team eval: all three failed
        intermittently with DeepEvalError("...outputted an invalid
        JSON...")). openai/gpt-oss-20b (this project's judge -- see
        nodes.py's model-deprecation note for why it's the model in use)
        sometimes wraps JSON in markdown fences, or produces near-miss JSON
        deepeval's own trim_and_load_json can't parse.

        Strip fences first (free, no extra call). If that's not enough and
        the text looks like it was attempting JSON, make exactly one
        self-repair call asking the model to fix its own output -- never
        recurses, and never touches genuinely non-JSON responses (e.g. a
        plain-text refusal), since those are left exactly as returned."""
        cleaned = _strip_markdown_fences(raw)
        if _is_valid_json(cleaned):
            return cleaned
        if not _looks_like_attempted_json(cleaned):
            return raw

        repair_prompt = (
            "The text below was supposed to be a single valid JSON object or "
            "array, but it isn't well-formed. Return ONLY the corrected, "
            "valid JSON -- no explanation, no markdown fences, no extra "
            "text.\n\n" + cleaned
        )
        try:
            repaired = _strip_markdown_fences(self._call_model(repair_prompt))
        except Exception:
            return raw

        return repaired if _is_valid_json(repaired) else raw
