from __future__ import annotations

import html
import json
from typing import Any


def xml_escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)


def trim_to_budget(text: str, char_budget: int) -> str:
    if len(text) <= char_budget:
        return text
    marker = "\n<truncation_notice>Prompt context was truncated to stay within budget.</truncation_notice>\n"
    return text[: max(0, char_budget - len(marker))] + marker


def build_intent_prompt(
    *,
    schema_context: dict[str, Any],
    conversation_summary: str,
    user_question: str,
    char_budget: int,
) -> str:
    schema_xml = xml_escape(compact_json(schema_context))
    conversation_xml = xml_escape(conversation_summary[-3000:])
    question_xml = xml_escape(user_question)
    prompt = f"""<chatbot_instruction>
  <role>You convert business questions about an ecommerce CSV into a safe structured query intent. You do not answer from memory.</role>
  <system_rules>
    <rule>Return only valid JSON matching the output contract.</rule>
    <rule>Use only columns present in schema_context.</rule>
    <rule>Do not write Python, Streamlit, shell, or executable code.</rule>
    <rule>Do not invent facts, trends, or columns.</rule>
    <rule>If the user question lacks the metric, entity, date range, or grouping needed for a reliable answer, return intent_type "clarification".</rule>
    <rule>Prefer the lightest representation. A top 3 answer should be a compact table/card unless the user explicitly asks for a chart.</rule>
    <rule>PII can be included only when the user explicitly asks for a row-level lookup or personal field.</rule>
  </system_rules>
  <schema_context>{schema_xml}</schema_context>
  <conversation_summary>{conversation_xml}</conversation_summary>
  <user_question>{question_xml}</user_question>
  <output_contract>
    {{
      "intent_type": "aggregate|lookup|trend|comparison|chart_request|clarification|unsupported",
      "metric": "revenue|order_count|quantity|avg_order_value|shipping_cost|discount|tax|delivery_delay_days|null",
      "dimensions": ["column_name"],
      "filters": [{{"column":"column_name","operator":"=|in|contains|between|>=|<=|>|<","value":"string_or_number_or_array"}}],
      "date_grain": "day|week|month|quarter|year|null",
      "limit": 100,
      "sort_direction": "desc|asc",
      "requested_visualization": "auto|table|card|bar|line|pie",
      "clarifying_question": "string|null",
      "needs_escalation": false,
      "confidence": 0.0
    }}
  </output_contract>
</chatbot_instruction>"""
    return trim_to_budget(prompt, char_budget)


def build_answer_prompt(
    *,
    user_question: str,
    intent: dict[str, Any],
    result_sample: list[dict[str, Any]],
    row_count: int,
    char_budget: int,
) -> str:
    prompt = f"""<answer_instruction>
  <role>You write concise, business-friendly answers from verified DuckDB results.</role>
  <system_rules>
    <rule>Answer only from result_sample and row_count.</rule>
    <rule>Do not expose chain-of-thought. You may provide a short "How I answered" summary.</rule>
    <rule>Do not write code.</rule>
    <rule>If the result is empty, say the data returned no matching rows.</rule>
    <rule>Do not invent causes or explanations beyond the data.</rule>
  </system_rules>
  <user_question>{xml_escape(user_question)}</user_question>
  <intent>{xml_escape(compact_json(intent))}</intent>
  <row_count>{row_count}</row_count>
  <result_sample>{xml_escape(compact_json(result_sample[:50]))}</result_sample>
  <output_contract>Return a concise markdown answer with no code blocks.</output_contract>
</answer_instruction>"""
    return trim_to_budget(prompt, char_budget)
