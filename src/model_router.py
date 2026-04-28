from __future__ import annotations

import json
import re
import time
from typing import Any

from .logging_config import log_event
from .prompting import build_answer_prompt, build_intent_prompt, build_mcp_agent_system_prompt, estimate_tokens

MAX_TOOL_ROUNDS = 8


class LLMUnavailable(RuntimeError):
    pass


def strip_openrouter_prefix(model: str) -> str:
    return model[len("openrouter/"):] if model.lower().startswith("openrouter/") else model


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


class LLMRouter:
    def __init__(
        self,
        model: str,
        logger: Any,
        char_budget: int,
        openrouter_api_key: str | None = None,
        openrouter_provider_order: str = "DeepSeek",
        agent_model: str | None = None,
    ) -> None:
        self.openrouter_api_key = openrouter_api_key
        self.openrouter_provider_order = openrouter_provider_order
        self.model = model
        self.agent_model = agent_model or model
        self.logger = logger
        self.char_budget = char_budget

    @property
    def available(self) -> bool:
        return bool(self.openrouter_api_key)

    def _openrouter_provider_pref(self) -> dict[str, Any]:
        order = [p.strip() for p in (self.openrouter_provider_order or "").split(",") if p.strip()]
        if not order:
            return {}
        return {"provider": {"order": order, "allow_fallbacks": False}}

    def _generate_json(self, prompt: str, request_id: str) -> dict[str, Any]:
        if not self.openrouter_api_key:
            raise LLMUnavailable("OpenRouter API key is not configured.")
        import httpx
        start = time.perf_counter()
        log_event(self.logger, "llm_request", request_id=request_id, model=self.model, prompt_tokens=estimate_tokens(prompt))
        body = {
            "model": strip_openrouter_prefix(self.model),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        body.update(self._openrouter_provider_pref())
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.openrouter_api_key}"},
            json=body,
            timeout=120.0,
        )
        response.raise_for_status()
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        text = response.json()["choices"][0]["message"]["content"] or ""
        parsed = extract_json(text)
        log_event(self.logger, "llm_response", request_id=request_id, model=self.model, elapsed_ms=elapsed_ms)
        return parsed

    def _generate_text(self, prompt: str, request_id: str) -> str:
        if not self.openrouter_api_key:
            raise LLMUnavailable("OpenRouter API key is not configured.")
        import httpx
        start = time.perf_counter()
        log_event(self.logger, "llm_summary_request", request_id=request_id, model=self.model, prompt_tokens=estimate_tokens(prompt))
        body = {
            "model": strip_openrouter_prefix(self.model),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        body.update(self._openrouter_provider_pref())
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.openrouter_api_key}"},
            json=body,
            timeout=120.0,
        )
        response.raise_for_status()
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        text = (response.json()["choices"][0]["message"]["content"] or "").strip()
        log_event(self.logger, "llm_summary_response", request_id=request_id, model=self.model, elapsed_ms=elapsed_ms)
        return text

    def _generate_text_stream(self, prompt: str, request_id: str):
        if not self.openrouter_api_key:
            raise LLMUnavailable("OpenRouter API key is not configured.")
        import httpx
        start = time.perf_counter()
        log_event(self.logger, "llm_stream_request", request_id=request_id, model=self.model, prompt_tokens=estimate_tokens(prompt))
        body = {
            "model": strip_openrouter_prefix(self.model),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "stream": True,
        }
        body.update(self._openrouter_provider_pref())
        with httpx.stream(
            "POST",
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.openrouter_api_key}"},
            json=body,
            timeout=120.0,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[len("data: "):].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk["choices"][0]["delta"].get("content")
                    if delta:
                        yield delta
                except Exception:
                    continue
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        log_event(self.logger, "llm_stream_response", request_id=request_id, model=self.model, elapsed_ms=elapsed_ms)

    def classify_intent(
        self,
        *,
        request_id: str,
        user_question: str,
        schema_context: dict[str, Any],
        conversation_summary: str,
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
        try:
            intent = self._generate_json(prompt, request_id)
            return intent, self.model
        except Exception as exc:  # pragma: no cover - network/API dependent
            log_event(self.logger, "llm_failure", request_id=request_id, model=self.model, error=str(exc))
            raise LLMUnavailable(str(exc)) from exc

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
        try:
            return self._generate_text(prompt, request_id)
        except Exception as exc:  # pragma: no cover - network/API dependent
            log_event(self.logger, "llm_summary_failure", request_id=request_id, model=self.model, error=str(exc))
            raise LLMUnavailable(str(exc)) from exc

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
        try:
            yield from self._generate_text_stream(prompt, request_id)
        except Exception as exc:  # pragma: no cover - network/API dependent
            log_event(self.logger, "llm_stream_failure", request_id=request_id, model=self.model, error=str(exc))
            raise LLMUnavailable(str(exc)) from exc

    async def agent_loop_stream(
        self,
        *,
        request_id: str,
        user_question: str,
        conversation_summary: str,
        tool_specs: list[dict[str, Any]],
        connector_summary: str,
        on_tool_call,
        system_prompt: str | None = None,
    ):
        """Run a function-calling agent loop. Yields events:
            {"kind": "tool_call", "name", "args", "connector_id"}
            {"kind": "tool_result", "name", "text", "error"}
            {"kind": "text", "delta"}

        `on_tool_call(tool_name, args) -> awaitable[(text_result, error_or_none, connector_id)]`.
        Pass `system_prompt` to use a custom base prompt (e.g. local DuckDB agent).
        """
        if not self.openrouter_api_key:
            raise LLMUnavailable("OpenRouter API key is not configured.")
        import httpx

        tools = [{
            "type": "function",
            "function": {
                "name": spec["name"],
                "description": spec.get("description") or "",
                "parameters": spec.get("input_schema") or {"type": "object", "properties": {}},
            },
        } for spec in tool_specs] or None

        system_text = system_prompt if system_prompt is not None else build_mcp_agent_system_prompt(connector_summary)
        if conversation_summary:
            system_text += "\n\n## Recent conversation\n" + conversation_summary[-2000:]

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_question},
        ]
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.openrouter_api_key}"}
        base_body: dict[str, Any] = {
            "model": strip_openrouter_prefix(self.agent_model),
            "temperature": 0.1,
        }
        base_body.update(self._openrouter_provider_pref())

        async def _stream_final(client: httpx.AsyncClient) -> Any:
            stream_body = {**base_body, "messages": messages, "stream": True}
            async with client.stream("POST", url, headers=headers, json=stream_body) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[len("data: "):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        delta = json.loads(data_str)["choices"][0]["delta"].get("content")
                    except Exception:
                        continue
                    if delta:
                        yield delta

        async with httpx.AsyncClient(timeout=120.0) as client:
            for round_idx in range(MAX_TOOL_ROUNDS):
                body = {**base_body, "messages": messages}
                if tools:
                    body["tools"] = tools
                try:
                    resp = await client.post(url, headers=headers, json=body)
                    resp.raise_for_status()
                except Exception as exc:
                    log_event(self.logger, "agent_llm_failure", request_id=request_id, model=self.agent_model, streaming=False, error=str(exc))
                    raise LLMUnavailable(str(exc)) from exc

                msg = resp.json()["choices"][0]["message"]
                tool_calls = msg.get("tool_calls") or []
                log_event(self.logger, "agent_round", request_id=request_id, round=round_idx, model=self.agent_model, tool_calls=len(tool_calls))

                if not tool_calls:
                    # Final answer — re-issue as a stream so the user sees deltas.
                    async for delta in _stream_final(client):
                        yield {"kind": "text", "delta": delta}
                    return

                # V4 Pro thinking mode requires the assistant message be passed back verbatim
                # (including reasoning / reasoning_details), so append the message dict as-is.
                messages.append(msg)

                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    tool_name = fn.get("name") or ""
                    args_raw = fn.get("arguments") or "{}"
                    try:
                        args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
                    except Exception:
                        args = {}
                    yield {"kind": "tool_call", "name": tool_name, "args": args}
                    try:
                        result_text, error, connector_id = await on_tool_call(tool_name, args)
                    except Exception as exc:
                        result_text, error, connector_id = "", str(exc), None
                    yield {"kind": "tool_result", "name": tool_name, "text": result_text, "error": error, "connector_id": connector_id}
                    tool_content = json.dumps({"error": error}) if error else (result_text or "")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id"),
                        "content": tool_content,
                    })

            # Hit the cap — final answer attempt with no tools.
            async for delta in _stream_final(client):
                yield {"kind": "text", "delta": delta}
