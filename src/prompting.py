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
    mcp_summary: str = "",
    local_source_name: str = "the loaded dataset",
) -> str:
    schema_xml = xml_escape(compact_json(schema_context))
    conversation_xml = xml_escape(conversation_summary[-3000:])
    question_xml = xml_escape(user_question)
    local_name_xml = xml_escape(local_source_name)
    has_mcp = bool(mcp_summary.strip())
    mcp_xml = xml_escape(mcp_summary) if has_mcp else ""

    if has_mcp:
        scope_rule = (
            '<rule>SCOPE GUARD: Only handle questions answerable from <local_schema> OR from <mcp_sources>. '
            'If the question is off-topic — general knowledge, opinions/advice, current events, weather, code generation, '
            'jokes, role-play, translation, or anything neither source can answer — return intent_type="unsupported" '
            'and a one-sentence polite refusal in clarifying_question naming what the available sources cover. '
            'Do NOT attempt to answer from training data.</rule>'
        )
        routing_rule = f'''<rule>ROUTING: Set "route" to one of:
      - "local" — the question maps cleanly to columns/concepts in <local_schema>, AND the user did not name an MCP source.
      - "mcp" — the question explicitly names a connected MCP source (e.g. "BigQuery"), uses concepts only available via MCP tools, is a meta-query about external data ("list datasets", "show tables"), or the conversation_summary shows the user already chose an MCP source.
      - "ambiguous" — the question could plausibly be answered by EITHER the local source OR an MCP source, AND the user gave no hint. In that case ALSO set intent_type="clarification" and write clarifying_question as: "I can answer this from {{local_source_name}} or {{mcp_source_name}} — which would you like?". Use the actual source names from <local_source_name> and <mcp_sources>.
      Honor explicit user choice from conversation_summary (e.g. a prior reply like "use BigQuery") — route accordingly without asking again.
      Default to "local" when in doubt and the local schema covers the question.
    </rule>'''
        sources_block = f'''  <local_source_name>{local_name_xml}</local_source_name>
  <local_schema>{schema_xml}</local_schema>
  <mcp_sources>{mcp_xml}</mcp_sources>'''
        route_field = '"route": "local|mcp|ambiguous",\n      '
    else:
        scope_rule = (
            '<rule>SCOPE GUARD: Only handle questions about the data described in schema_context. '
            'If the question is off-topic — general knowledge ("what is React", "who won the world cup", "explain X concept"), '
            'opinions/advice ("should I", "what do you think"), current events / news / weather, code generation, '
            'math unrelated to the data, jokes, role-play, translation, or anything not answerable from the schema\'s columns — '
            'return intent_type="unsupported" and put a one-sentence polite refusal in clarifying_question naming what the dataset IS about '
            '(e.g. "I can only answer questions about this orders dataset — try asking about revenue, products, customers, or shipping."). '
            'Do NOT attempt to answer from training data.</rule>'
        )
        routing_rule = ""
        sources_block = f"  <schema_context>{schema_xml}</schema_context>"
        route_field = ""

    prompt = f"""<chatbot_instruction>
  <role>You convert business questions into a safe structured query intent. You do not answer from memory or training data.</role>
  <system_rules>
    <rule>Return only valid JSON matching the output contract.</rule>
    <rule>For local queries, use only columns present in <local_schema> (or schema_context).</rule>
    <rule>Do not write Python, Streamlit, shell, or executable code.</rule>
    <rule>Do not invent facts, trends, or columns.</rule>
    {scope_rule}
    {routing_rule}
    <rule>Bias strongly toward answering DATA questions. Return intent_type="clarification" ONLY when (a) the question is on-topic but impossible to answer with the available sources (references a column that does not exist, contradicts itself, has no plausible mapping), or (b) routing is genuinely ambiguous between local and MCP. Do NOT clarify just because details are missing — apply the defaults below silently.</rule>
    <rule>Silent defaults (apply without asking) — these apply to LOCAL routing only:
      - Missing metric → "revenue".
      - Words like "sales", "earnings", "income", "money", "value", "amount", "total" with no other qualifier → "revenue".
      - Words like "orders", "transactions", "purchases", "count", "how many" → "order_count".
      - Words like "units", "items sold", "qty" → "quantity".
      - Missing time range → no date filter (all time).
      - Missing grouping → one overall total (no dimensions).
      - "highest", "top", "best", "most", "largest" → sort_direction "desc", limit 10 unless a number is given.
      - "lowest", "worst", "bottom", "least", "smallest" → sort_direction "asc", limit 10.
      - Phrases like "by X", "per X", "across X", "sort by X", "broken down by X", "split by X" → X is the dimension; this is NEVER a clarification trigger.
      - "payment method/mode/type" → payment_mode dimension. "category" → prod_category. "city/location" → ship_city. "customer/segment" → cust_segment. "product" → prod_name. "carrier" → carrier_name. "country" → ship_country.
      - When a metric is mentioned without an aggregation (e.g. "revenue by category"), treat as SUM of that metric.
      - If the user phrases the question as a sort ("sort by payment method by highest revenue"), the metric is the thing being sorted ("revenue"), the dimension is the grouping ("payment_mode"), sort is desc.
    </rule>
    <rule>Prefer the lightest representation. A top 3 answer should be a compact table/card unless the user explicitly asks for a chart.</rule>
    <rule>PII can be included only when the user explicitly asks for a row-level lookup or personal field.</rule>
  </system_rules>
{sources_block}
  <conversation_summary>{conversation_xml}</conversation_summary>
  <user_question>{question_xml}</user_question>
  <output_contract>
    {{
      {route_field}"intent_type": "aggregate|lookup|trend|comparison|chart_request|clarification|unsupported",
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
    sql: str | None = None,
    total_row: dict[str, Any] | None = None,
) -> str:
    sample_size = min(len(result_sample), 50)
    truncated = row_count > sample_size
    total_xml = xml_escape(compact_json(total_row)) if total_row else ""
    prompt = f"""<answer_instruction>
  <role>You write concise, business-friendly answers from verified DuckDB results.</role>
  <system_rules>
    <rule>Answer only from result_sample, row_count, and total_row. Do not invent rows or values. Do not use general knowledge, training data, or external facts — if the question can't be answered from the data shown, say so plainly.</rule>
    <rule>NEVER compute totals, sums, averages, counts, min, or max by adding or aggregating values across result_sample rows. The sample is at most 50 rows and may be a slice of a larger result. Only quote an aggregate if it appears as a single value in result_sample or total_row (i.e. the SQL itself returned the aggregate).</rule>
    <rule>If <total_row> is non-empty, that single value IS the authoritative grand total computed by a separate aggregate query over all matching rows; quote it directly when the user asks for a total. Combine it naturally with the per-row breakdown — typically: list the rows, then say "Grand total: $X" using the value from total_row.</rule>
    <rule>ONLY if the user's question explicitly asks for a total (contains "grand total", "overall total", "total across", "sum across", or similar) AND <total_row> is empty AND the SQL is a per-row breakdown, then add ONE short line at the end: "Tip: ask 'what is the total {{metric}} for ...?' for the exact grand total." Do NOT add this line for normal breakdown questions that don't mention a total. Do NOT fabricate the total by summing the visible rows.</rule>
    <rule>If row_count is greater than the number of rows shown, say "showing top {{shown}} of {{row_count}}" before the list.</rule>
    <rule>For multi-row breakdown answers (lists, time-series, per-category, per-product, etc.), end with a single line that gives the grand total of the metric using <total_row> — even if the user did not explicitly ask. Format: "Total {{metric}}: $X". If <total_row> is empty, omit this line — do NOT sum the sample to fabricate a total.</rule>
    <rule>Do not expose chain-of-thought. Do NOT add a "How I answered" line, a "Methodology" line, or any meta-explanation of how you produced the answer — the user can see the SQL in the result block.</rule>
    <rule>Do not write code. If the result is empty, say the data returned no matching rows. Do not invent causes beyond the data.</rule>
  </system_rules>
  <user_question>{xml_escape(user_question)}</user_question>
  <intent>{xml_escape(compact_json(intent))}</intent>
  <sql>{xml_escape(sql or "")}</sql>
  <row_count>{row_count}</row_count>
  <sample_size>{sample_size}</sample_size>
  <sample_is_truncated>{str(truncated).lower()}</sample_is_truncated>
  <total_row>{total_xml}</total_row>
  <result_sample>{xml_escape(compact_json(result_sample[:50]))}</result_sample>
  <output_contract>Return a concise markdown answer with no code blocks.</output_contract>
</answer_instruction>"""
    return trim_to_budget(prompt, char_budget)


def build_mcp_agent_system_prompt(connector_summary: str) -> str:
    """System prompt for the agent loop. Borrows DMV's anti-fabrication rules."""
    return f"""You are a data assistant. You access data ONLY by calling the tools below.

## Connected sources
{connector_summary or "(no connectors)"}

## Hard rules
1. You CANNOT execute raw SQL on your own. Use the provided tools.
2. You can ONLY retrieve data by calling the tools. If no tool fits, say so plainly.
3. NEVER fabricate, invent, or guess data rows, IDs, emails, names, dates, or totals.
4. If you did not receive data from a tool result, you do not have that data — don't make it up.
5. NEVER write SQL in your reply — the user sees the tool calls separately.

## Discovery sequence (typical)
1. list_datasets → see what's available
2. list_tables(dataset) → see tables
3. get_table_schema(table) → see columns
4. Run the query/get_* tool to retrieve actual data
Chain as many tool calls as you need.

## How to respond
- Multi-row data → markdown table.
- Lists of items → bullet list.
- Single value or yes/no → one short sentence.
- Hide the SQL/JSON/tool internals unless the user explicitly asks for the query.
- If a tool errors or returns nothing, say "I checked and couldn't find anything matching that."
- Never mention "MCP", "tool", "function call", "BigQuery", or other infrastructure names — speak naturally about the data.
"""

