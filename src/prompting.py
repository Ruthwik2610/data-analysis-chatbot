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
    available = char_budget - len(marker)
    if available <= 0:
        return marker[:char_budget]
    head_budget = available // 2
    tail_budget = available - head_budget
    return text[:head_budget] + marker + text[-tail_budget:]


def build_intent_prompt(
    *,
    schema_context: dict[str, Any],
    conversation_summary: str,
    user_question: str,
    char_budget: int,
    mcp_summary: str = "",
    local_source_name: str = "the loaded dataset",
    instruction_context: str = "",
) -> str:
    schema_xml = xml_escape(compact_json(schema_context))
    conversation_xml = xml_escape(conversation_summary[-3000:])
    question_xml = xml_escape(user_question)
    local_name_xml = xml_escape(local_source_name)
    has_mcp = bool(mcp_summary.strip())
    mcp_xml = xml_escape(mcp_summary) if has_mcp else ""
    instruction_xml = xml_escape(instruction_context) if instruction_context else ""

    if has_mcp:
        scope_rule = (
            '<rule>SCOPE GUARD: Only handle questions answerable from <local_schema> OR from <mcp_sources>. '
            'If the question is off-topic — general knowledge, opinions/advice, current events, weather, code generation, '
            'jokes, role-play, translation, or anything neither source can answer — return intent_type="unsupported" '
            'and a one-sentence polite refusal in clarifying_question naming what the available sources cover. '
            'Do NOT attempt to answer from training data.</rule>'
        )
        routing_rule = f'''<rule>ROUTING: Set "route" to one of:
      - "local" — the question maps cleanly to columns/concepts in <local_schema>, OR the question explicitly refers to "the table", "the dataset", "this file", or "the uploaded file", AND the user did not explicitly name an MCP source.
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
      - "metric_column" MUST be the EXACT name of a real column from <local_schema>/<schema_context>. Do NOT invent column names. If the user names a measure ("unit price", "revenue", "shipping cost", "mrp", "list price"), pick the schema column whose name matches most closely (e.g. "unit price" → unit_price; "revenue" → revenue or total_order_val if revenue is absent; "shipping" → shipping_cost). Treat metric_column as a numeric measure to aggregate — NEVER put it in dimensions and NEVER treat it as a date.
      - "aggregation" defaults to "sum". Use "avg" for "average/avg/mean", "count" for "how many/number of/count" (in which case metric_column is null), "max" for "max/maximum", "min" for "min/minimum".
      - "Total X", "sum of X", "X across Y" → aggregation "sum" with metric_column=X.
      - "How many orders/rows/records" with no measure → aggregation "count", metric_column null.
      - Missing time range → no date filter (all time). Missing grouping → one overall total (no dimensions).
      - "highest", "top", "best", "most", "largest" → sort_direction "desc", limit 10 unless a number is given.
      - "lowest", "worst", "bottom", "least", "smallest" → sort_direction "asc", limit 10.
      - Phrases like "by X", "per X", "across X", "sort by X", "broken down by X", "split by X" → X is the dimension; this is NEVER a clarification trigger. The dimension MUST be a real column name from the schema.
      - TIME GROUPING is a separate concept from dimensions. If the user says "by month", "monthly", "month wise / month-wise", "each month", "per month" — and equivalents for day / week / quarter / year — set `date_grain` to the matching grain ("day"|"week"|"month"|"quarter"|"year") and do NOT put "month"/"year"/"date" in dimensions. The grouping happens implicitly on the schema's date column (e.g. order_datetime, order_date, invoice_date). Words like "trend" or "over time" with no explicit grain default to date_grain="month". Only put a column in dimensions if it is a real non-time column in the schema.
      - If the user phrases the question as a sort ("sort by payment method by highest revenue"), metric_column is the thing being sorted (e.g. revenue), the dimension is the grouping (e.g. payment_mode), sort is desc.
      - Filters must use real column names from the schema. Date filters use the date column from the schema (often named order_datetime/order_date/created_at/...) with ISO values like "2025-10-01". For "October 2025" → between "2025-10-01" and "2025-10-31"; for "in 2025" → between "2025-01-01" and "2025-12-31".
      - IDENTIFIER FILTERS: when the user writes an identifier value (email, "PREFIX-1234", long alphanumeric token, or "<column> <number>"), emit it as an equality filter on the schema column whose name + role matches the value's shape. Use the EXACT value the user typed; never reformat or invent IDs. If no schema column aligns, drop the filter rather than guessing. Bare numbers ("12345") need an explicit column word in the question ("customer 12345" → cust_key=12345); never filter on a lone number. Set intent_type="lookup" only when the question is essentially "show the record matching this identifier" with no aggregation; otherwise keep the aggregate intent and add the identifier to filters.
      - MULTI-STEP: pick intent_type="multi_step" for chained questions, advanced statistical analysis (variance, coefficient of variation), relationship/basket analysis (items purchased together), and business insight generation. Examples:
        - "which month had the highest sales AND in that month which product contributed most"
        - "show products where the selling rate variation exceeds 20% coefficient of variation"
        - "which products are frequently purchased together in the same invoice"
        - "give 5 business insights and recommendations from this data"
        - "give me a timetable by professor" or "pivot the table to show class schedule"
        Single questions with one basic aggregation are NOT multi_step.
    </rule>
    <rule>Prefer the lightest representation. A top 3 answer should be a compact table/card unless the user explicitly asks for a chart.</rule>
    <rule>PII can be included only when the user explicitly asks for a row-level lookup or personal field.</rule>
  </system_rules>
{sources_block}
  <project_and_source_instructions>{instruction_xml}</project_and_source_instructions>
  <conversation_summary>{conversation_xml}</conversation_summary>
  <user_question>{question_xml}</user_question>
  <output_contract>
    {{
      {route_field}"intent_type": "aggregate|lookup|trend|comparison|chart_request|multi_step|clarification|unsupported",
      "metric_column": "<real_column_name_from_schema_or_null>",
      "aggregation": "sum|avg|count|min|max",
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
  <role>You write very short, business-friendly answers from verified DuckDB results. The user already sees the full data as a chart or table beneath your answer — your job is to add a one-line headline, NOT to re-enumerate the rows.</role>
  <system_rules>
    <rule>BREVITY: Default to ONE sentence (max two). Surface the headline only — peak/top item, grand total, notable pattern, or the answer to the specific question. The chart/table renders every row already; do NOT repeat it as a bulleted list.</rule>
    <rule>NEVER produce long bulleted/numbered lists of rows for breakdown or time-series answers (by month, by category, top N, etc.). One sentence with the highlight is correct. Listing more than 3 rows is almost always wrong.</rule>
    <rule>Single-value answers (count, sum, average, lookup of one record): give the value in one short sentence. No preamble, no "Here is the answer:".</rule>
    <rule>Only enumerate rows when ALL of: row_count is 5 or fewer AND the user explicitly asked to "list", "show each", or similar AND there is no chart context. Otherwise summarize.</rule>
    <rule>Answer only from result_sample, row_count, and total_row. Do not invent rows or values. Do not use general knowledge, training data, or external facts — if the question can't be answered from the data shown, say so plainly.</rule>
    <rule>NEVER compute totals, sums, averages, counts, min, or max by adding or aggregating values across result_sample rows. The sample is at most 50 rows and may be a slice of a larger result. Only quote an aggregate if it appears as a single value in result_sample or total_row.</rule>
    <rule>If <total_row> is non-empty, that single value IS the authoritative grand total. Mention it inline within your one-sentence summary (e.g. "...total 48,620 orders."). Do NOT add a separate "Total: ..." line.</rule>
    <rule>If row_count is greater than sample_size, you MAY add "(showing top {{sample_size}} of {{row_count}})" inline — but still keep the answer to one sentence.</rule>
    <rule>Do not expose chain-of-thought, methodology, or "How I answered" lines. The user sees the SQL in the result block.</rule>
    <rule>Do not write code. If the result is empty, say "No matching rows." in one short sentence.</rule>
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


def build_local_agent_system_prompt(source_name: str, schema: dict[str, Any]) -> str:
    """System prompt for the local-DuckDB agent loop. Used for multi-step questions
    where one query depends on another's result."""
    cols = schema.get("columns") or []
    lines: list[str] = []
    for col in cols[:60]:
        name = col.get("name") or col.get("column") or ""
        ctype = col.get("type") or col.get("dtype") or "?"
        if name:
            lines.append(f"- {name}: {ctype}")
    schema_text = "\n".join(lines) if lines else "(schema unavailable)"
    return f"""You answer questions about a local dataset by writing DuckDB SQL and calling run_sql.

## The dataset
Source: {source_name}
Table name: orders
Columns:
{schema_text}

## How to use run_sql
- DuckDB SQL. SELECT only — no INSERT/UPDATE/DELETE/DROP/ALTER.
- Use ONLY the column names listed above. Never invent columns.
- Quote names with double quotes when in doubt: "column name".
- For numeric ops on text-typed columns: COALESCE(TRY_CAST("col" AS DOUBLE), TRY_CAST(regexp_replace(NULLIF(TRIM(CAST("col" AS VARCHAR)), ''), '[^0-9.-]', '', 'g') AS DOUBLE)).
- Monthly grouping on text/date columns: date_trunc('month', COALESCE(TRY_CAST("date_col" AS TIMESTAMP), try_strptime(NULLIF(TRIM(CAST("date_col" AS VARCHAR)), ''), ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y', '%m-%d-%Y']))).
- Always include a LIMIT (default 100).

## Multi-step & Analytics strategy
For compound questions like "which month had the most X AND in that month which Y":
1. First call run_sql to find the anchor (e.g. peak month).
2. Read the result, then call run_sql again parameterized by that anchor.
3. Stop after the data you need is fetched. Don't make redundant calls.

- Business Insights: If asked for insights or recommendations, write exploratory queries to find top performers, anomalies, or correlations, and then synthesize them. DO NOT refuse to generate insights.
- Basket Analysis: If asked what items are purchased together, perform a self-join on the invoice/order ID column to find top pairs.
- Statistical Analysis: If asked about variation or significance, use DuckDB's statistical functions like STDDEV(col)/AVG(col) for Coefficient of Variation.
- Pivoting / Timetables: If asked for a timetable or to pivot the data, reshape the data using DuckDB's PIVOT. Example: PIVOT table_name ON column_to_become_columns USING first(value) GROUP BY column_to_become_rows. Ensure the query outputs the full cross-tabulated table.

## How to respond
- BREVITY: one short sentence weaving BOTH findings together (e.g. "July 2015 led with $X — within that month, Pepperoni Pizza topped at $Y."). Exception: if the user explicitly asks for multiple insights or a list, you may use a brief bulleted list.
- The user already sees the final table beneath your reply — do NOT echo rows or write a markdown table.
- Empty result → "No matching rows."
- Never mention "tool", "SQL", "run_sql", "query", or other infrastructure names — speak naturally about the data.
"""


def build_mcp_agent_system_prompt(connector_summary: str) -> str:
    """System prompt for the MCP function-calling agent loop."""
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
- BREVITY: One short sentence with the headline (peak/total/notable item, or the direct answer). The user already sees the rows as a table beneath your reply — do NOT echo them as a markdown table or bullet list.
- Single value or yes/no → one short sentence with the value. No preamble.
- Empty result → "I checked and couldn't find anything matching that."
- Listing more than 3 rows in your text is almost always wrong — the table below shows them all.
- Hide SQL/JSON/tool internals unless the user explicitly asks for the query.
- Never mention "MCP", "tool", "function call", "BigQuery", "Salesforce metadata", or other infrastructure names — speak naturally about the data.
"""
