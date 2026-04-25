from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from .logging_config import log_event
from .prompting import build_answer_prompt, build_intent_prompt, estimate_tokens


class LLMUnavailable(RuntimeError):
    pass


@dataclass
class ModelChoice:
    primary: str
    escalation: str
    fallback: str


def extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


class GeminiRouter:
    def __init__(self, api_key: str | None, models: ModelChoice, logger: Any, char_budget: int) -> None:
        self.api_key = api_key
        self.models = models
        self.logger = logger
        self.char_budget = char_budget
        self._client = None

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _client_or_raise(self):
        if not self.api_key:
            raise LLMUnavailable("Gemini API key is not configured.")
        if self._client is None:
            try:
                from google import genai
            except Exception as exc:  # pragma: no cover - depends on optional package
                raise LLMUnavailable("google-genai is not installed.") from exc
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _generate_json(self, model: str, prompt: str, request_id: str) -> dict[str, Any]:
        client = self._client_or_raise()
        start = time.perf_counter()
        log_event(self.logger, "llm_request", request_id=request_id, model=model, prompt_tokens=estimate_tokens(prompt))
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={"temperature": 0, "response_mime_type": "application/json"},
        )
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        text = getattr(response, "text", "") or ""
        parsed = extract_json(text)
        log_event(self.logger, "llm_response", request_id=request_id, model=model, elapsed_ms=elapsed_ms)
        return parsed

    def _generate_text(self, model: str, prompt: str, request_id: str) -> str:
        client = self._client_or_raise()
        start = time.perf_counter()
        log_event(self.logger, "llm_summary_request", request_id=request_id, model=model, prompt_tokens=estimate_tokens(prompt))
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={"temperature": 0.1},
        )
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        text = (getattr(response, "text", "") or "").strip()
        log_event(self.logger, "llm_summary_response", request_id=request_id, model=model, elapsed_ms=elapsed_ms)
        return text

    def classify_intent(
        self,
        *,
        request_id: str,
        user_question: str,
        schema_context: dict[str, Any],
        conversation_summary: str,
    ) -> tuple[dict[str, Any], str]:
        prompt = build_intent_prompt(
            schema_context=schema_context,
            conversation_summary=conversation_summary,
            user_question=user_question,
            char_budget=self.char_budget,
        )
        models_to_try = [self.models.primary]
        if looks_complex(user_question):
            models_to_try = [self.models.escalation, self.models.primary]
        models_to_try.append(self.models.fallback)

        last_error: Exception | None = None
        for model in dict.fromkeys(models_to_try):
            try:
                intent = self._generate_json(model, prompt, request_id)
                if intent.get("needs_escalation") and model != self.models.escalation:
                    intent = self._generate_json(self.models.escalation, prompt, request_id)
                    return intent, self.models.escalation
                return intent, model
            except Exception as exc:  # pragma: no cover - network/API dependent
                last_error = exc
                log_event(self.logger, "llm_failure", request_id=request_id, model=model, error=str(exc))
        raise LLMUnavailable(str(last_error) if last_error else "No model produced a response.")

    def summarize_answer(
        self,
        *,
        request_id: str,
        user_question: str,
        intent: dict[str, Any],
        result_sample: list[dict[str, Any]],
        row_count: int,
    ) -> str:
        prompt = build_answer_prompt(
            user_question=user_question,
            intent=intent,
            result_sample=result_sample,
            row_count=row_count,
            char_budget=self.char_budget,
        )
        last_error: Exception | None = None
        for model in dict.fromkeys([self.models.primary, self.models.fallback]):
            try:
                return self._generate_text(model, prompt, request_id)
            except Exception as exc:  # pragma: no cover - network/API dependent
                last_error = exc
                log_event(self.logger, "llm_summary_failure", request_id=request_id, model=model, error=str(exc))
        raise LLMUnavailable(str(last_error) if last_error else "No model produced a summary.")


def looks_complex(question: str) -> bool:
    q = question.lower()
    complex_terms = ["why", "correlat", "compare", "versus", "vs", "trend", "forecast", "relationship", "cohort"]
    return any(term in q for term in complex_terms)
