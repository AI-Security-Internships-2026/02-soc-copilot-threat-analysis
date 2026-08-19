# src/agent/deepteam_groq_model.py
#
# Wraps ChatGroq as a deepeval DeepEvalBaseLLM so deepteam's simulator and
# evaluation ("judge") models run on Groq instead of defaulting to OpenAI.
# deepteam has no built-in Groq provider (see
# deepteam.red_teamer.utils.MODEL_PROVIDER_MAPPING), and this project
# deliberately moved off OpenAI in Week 3 over quota costs -- see
# docs/redteam-deepteam-eval.md for the full rationale.

import asyncio
import time

from deepeval.models import DeepEvalBaseLLM
from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq

from src.agent.nodes import _extract_retry_seconds

MAX_RETRIES = 5


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
