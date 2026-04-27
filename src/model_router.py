from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from .logging_config import log_event
from .prompting import build_answer_prompt, build_intent_prompt, build_mcp_agent_system_prompt, estimate_tokens

MAX_TOOL_ROUNDS = 8


class LLMUnavailable(RuntimeError):
    pass


FallbackCallback = Callable[[str, str, str], None]


def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).upper()
    return (
        "429" in msg
        or "RESOURCE_EXHAUSTED" in msg
        or "RATE LIMIT" in msg
        or "QUOTA" in msg
    )


@dataclass
class ModelChoice:
    primary: str
    escalation: str
    fallback: str


def provider_for_model(model: str) -> str:
    """Pick a provider from a model name. Groq hosts llama/mixtral/qwen/gemma2;
    everything else falls through to the Gemini provider."""
    name = (model or "").lower()
    if name.startswith(("llama", "mixtral", "qwen")) or "groq" in name or name.startswith("gemma2"):
        return "groq"
    return "gemini"


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
    def __init__(
        self,
        api_key: str | None,
        models: ModelChoice,
        logger: Any,
        char_budget: int,
        groq_api_key: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.groq_api_key = groq_api_key
        self.models = models
        self.logger = logger
        self.char_budget = char_budget
        self._client = None
        self._groq_client = None

    @property
    def available(self) -> bool:
        return bool(self.api_key) or bool(self.groq_api_key)

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

    def _groq_client_or_raise(self):
        if not self.groq_api_key:
            raise LLMUnavailable("Groq API key is not configured.")
        if self._groq_client is None:
            try:
                from groq import Groq
            except Exception as exc:  # pragma: no cover - depends on optional package
                raise LLMUnavailable("groq SDK is not installed.") from exc
            self._groq_client = Groq(api_key=self.groq_api_key)
        return self._groq_client

    def _generate_json(self, model: str, prompt: str, request_id: str) -> dict[str, Any]:
        if provider_for_model(model) == "groq":
            return self._generate_json_groq(model, prompt, request_id)
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

    def _generate_json_groq(self, model: str, prompt: str, request_id: str) -> dict[str, Any]:
        client = self._groq_client_or_raise()
        start = time.perf_counter()
        log_event(self.logger, "llm_request", request_id=request_id, model=model, prompt_tokens=estimate_tokens(prompt))
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        text = (response.choices[0].message.content or "") if response.choices else ""
        parsed = extract_json(text)
        log_event(self.logger, "llm_response", request_id=request_id, model=model, elapsed_ms=elapsed_ms)
        return parsed

    def _generate_text(self, model: str, prompt: str, request_id: str) -> str:
        if provider_for_model(model) == "groq":
            return self._generate_text_groq(model, prompt, request_id)
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

    def _generate_text_groq(self, model: str, prompt: str, request_id: str) -> str:
        client = self._groq_client_or_raise()
        start = time.perf_counter()
        log_event(self.logger, "llm_summary_request", request_id=request_id, model=model, prompt_tokens=estimate_tokens(prompt))
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        text = ((response.choices[0].message.content or "").strip()) if response.choices else ""
        log_event(self.logger, "llm_summary_response", request_id=request_id, model=model, elapsed_ms=elapsed_ms)
        return text

    def _generate_text_stream_groq(self, model: str, prompt: str, request_id: str):
        client = self._groq_client_or_raise()
        start = time.perf_counter()
        log_event(self.logger, "llm_stream_request", request_id=request_id, model=model, prompt_tokens=estimate_tokens(prompt))
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        log_event(self.logger, "llm_stream_response", request_id=request_id, model=model, elapsed_ms=elapsed_ms)

    def classify_intent(
        self,
        *,
        request_id: str,
        user_question: str,
        schema_context: dict[str, Any],
        conversation_summary: str,
        on_fallback: FallbackCallback | None = None,
        mcp_summary: str = "",
        local_source_name: str = "the loaded dataset",
    ) -> tuple[dict[str, Any], str]:
        prompt = build_intent_prompt(
            schema_context=schema_context,
            conversation_summary=conversation_summary,
            user_question=user_question,
            char_budget=self.char_budget,
            mcp_summary=mcp_summary,
            local_source_name=local_source_name,
        )
        models_to_try = [self.models.primary, self.models.escalation, self.models.fallback]
        canonical_primary = models_to_try[0]
        fallback_reason: str | None = None
        last_error: Exception | None = None
        for model in dict.fromkeys(models_to_try):
            try:
                intent = self._generate_json(model, prompt, request_id)
                if fallback_reason and on_fallback and model != canonical_primary:
                    on_fallback(canonical_primary, model, fallback_reason)
                if intent.get("needs_escalation") and model != self.models.escalation:
                    intent = self._generate_json(self.models.escalation, prompt, request_id)
                    return intent, self.models.escalation
                return intent, model
            except Exception as exc:  # pragma: no cover - network/API dependent
                last_error = exc
                if not fallback_reason and _is_rate_limit_error(exc):
                    fallback_reason = "rate_limit"
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
        sql: str | None = None,
    ) -> str:
        prompt = build_answer_prompt(
            user_question=user_question,
            intent=intent,
            result_sample=result_sample,
            row_count=row_count,
            char_budget=self.char_budget,
            sql=sql,
        )
        last_error: Exception | None = None
        for model in dict.fromkeys([self.models.primary, self.models.escalation, self.models.fallback]):
            try:
                return self._generate_text(model, prompt, request_id)
            except Exception as exc:  # pragma: no cover - network/API dependent
                last_error = exc
                log_event(self.logger, "llm_summary_failure", request_id=request_id, model=model, error=str(exc))
        raise LLMUnavailable(str(last_error) if last_error else "No model produced a summary.")

    def summarize_answer_stream(
        self,
        *,
        request_id: str,
        user_question: str,
        intent: dict[str, Any],
        result_sample: list[dict[str, Any]],
        row_count: int,
        sql: str | None = None,
        total_row: dict[str, Any] | None = None,
        on_fallback: FallbackCallback | None = None,
        prefer_model: str | None = None,
    ):
        prompt = build_answer_prompt(
            user_question=user_question,
            intent=intent,
            result_sample=result_sample,
            row_count=row_count,
            char_budget=self.char_budget,
            sql=sql,
            total_row=total_row,
        )
        cascade = [self.models.primary, self.models.escalation, self.models.fallback]
        canonical_primary = cascade[0]
        # When intent classification just had to fall back, the caller passes the
        # winning model so we don't pay the same Gemini 503/429 round-trip again.
        if prefer_model and prefer_model in cascade and prefer_model != cascade[0]:
            cascade = [prefer_model] + [m for m in cascade if m != prefer_model]
        models = list(dict.fromkeys(cascade))
        fallback_reason: str | None = None
        last_error: Exception | None = None
        for model in models:
            try:
                if provider_for_model(model) == "groq":
                    yield from self._generate_text_stream_groq(model, prompt, request_id)
                else:
                    client = self._client_or_raise()
                    start = time.perf_counter()
                    log_event(self.logger, "llm_stream_request", request_id=request_id, model=model, prompt_tokens=estimate_tokens(prompt))
                    stream = client.models.generate_content_stream(
                        model=model,
                        contents=prompt,
                        config={"temperature": 0.1},
                    )
                    for chunk in stream:
                        text = getattr(chunk, "text", None)
                        if text:
                            yield text
                    elapsed_ms = int((time.perf_counter() - start) * 1000)
                    log_event(self.logger, "llm_stream_response", request_id=request_id, model=model, elapsed_ms=elapsed_ms)
                if fallback_reason and on_fallback and model != canonical_primary:
                    on_fallback(canonical_primary, model, fallback_reason)
                return
            except Exception as exc:  # pragma: no cover - network/API dependent
                last_error = exc
                if not fallback_reason and _is_rate_limit_error(exc):
                    fallback_reason = "rate_limit"
                log_event(self.logger, "llm_stream_failure", request_id=request_id, model=model, error=str(exc))
        raise LLMUnavailable(str(last_error) if last_error else "No model produced a streamed summary.")

    async def agent_loop_stream(
        self,
        *,
        request_id: str,
        user_question: str,
        conversation_summary: str,
        tool_specs: list[dict[str, Any]],
        connector_summary: str,
        on_tool_call,
    ):
        """Run a function-calling agent loop. Yields events:
            {"kind": "tool_call", "name", "args", "connector_id"}
            {"kind": "tool_result", "name", "text", "error"}
            {"kind": "text", "delta"}

        `on_tool_call(tool_name, args) -> awaitable[(text_result, error_or_none, connector_id)]`.
        """
        from google.genai import types as gtypes

        client = self._client_or_raise()
        async_client = client.aio

        function_decls = []
        for spec in tool_specs:
            schema = spec.get("input_schema") or {"type": "object", "properties": {}}
            function_decls.append(gtypes.FunctionDeclaration(
                name=spec["name"],
                description=spec.get("description") or "",
                parameters_json_schema=schema,
            ))
        tools_config = [gtypes.Tool(function_declarations=function_decls)] if function_decls else None

        system_text = build_mcp_agent_system_prompt(connector_summary)
        if conversation_summary:
            system_text += "\n\n## Recent conversation\n" + conversation_summary[-2000:]

        contents: list[Any] = [gtypes.Content(role="user", parts=[gtypes.Part.from_text(text=user_question)])]
        # MCP agent loop uses Gemini's function-calling schema; skip non-Gemini models.
        models = [m for m in dict.fromkeys([self.models.primary, self.models.escalation, self.models.fallback])
                  if provider_for_model(m) == "gemini"]
        if not models:
            raise LLMUnavailable("No Gemini model is configured for the MCP agent loop.")

        async def _generate_once(streaming: bool):
            last_err: Exception | None = None
            for model in models:
                try:
                    config = gtypes.GenerateContentConfig(
                        temperature=0.1,
                        system_instruction=system_text,
                        tools=tools_config,
                        automatic_function_calling=gtypes.AutomaticFunctionCallingConfig(disable=True),
                    )
                    if streaming:
                        return model, await async_client.models.generate_content_stream(
                            model=model, contents=contents, config=config,
                        )
                    return model, await async_client.models.generate_content(
                        model=model, contents=contents, config=config,
                    )
                except Exception as exc:
                    last_err = exc
                    log_event(self.logger, "agent_llm_failure", request_id=request_id, model=model, streaming=streaming, error=str(exc))
            raise LLMUnavailable(str(last_err) if last_err else "No model responded to the agent step.")

        for round_idx in range(MAX_TOOL_ROUNDS):
            model_used, response = await _generate_once(streaming=False)
            function_calls = getattr(response, "function_calls", None) or []
            log_event(self.logger, "agent_round", request_id=request_id, round=round_idx, model=model_used, tool_calls=len(function_calls))

            if not function_calls:
                # No more tool calls — re-issue the same prompt as a stream for the final text answer.
                _, stream = await _generate_once(streaming=True)
                async for chunk in stream:
                    text = getattr(chunk, "text", None)
                    if text:
                        yield {"kind": "text", "delta": text}
                return

            # Append the model's tool-call turn so subsequent calls have full history.
            model_content = response.candidates[0].content if response.candidates else None
            if model_content is not None:
                contents.append(model_content)

            response_parts = []
            for fc in function_calls:
                tool_name = fc.name
                args = dict(fc.args or {})
                yield {"kind": "tool_call", "name": tool_name, "args": args}
                try:
                    result_text, error, connector_id = await on_tool_call(tool_name, args)
                except Exception as exc:
                    result_text, error, connector_id = "", str(exc), None
                yield {"kind": "tool_result", "name": tool_name, "text": result_text, "error": error, "connector_id": connector_id}
                payload = {"error": error} if error else {"result": result_text}
                response_parts.append(gtypes.Part.from_function_response(name=tool_name, response=payload))
            contents.append(gtypes.Content(role="tool", parts=response_parts))

        # Hit the cap — ask once more for a final answer with no tools allowed.
        _, stream = await _generate_once(streaming=True)
        async for chunk in stream:
            text = getattr(chunk, "text", None)
            if text:
                yield {"kind": "text", "delta": text}
