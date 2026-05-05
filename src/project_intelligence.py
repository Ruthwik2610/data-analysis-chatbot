from __future__ import annotations

import json
import re
from typing import Any


COUNT_WORDS = ("how many", "count", "number of")
ROW_WORDS = ("row", "rows", "line item", "line items", "records")


def _columns(schema: dict[str, Any] | None) -> set[str]:
    return {
        str(col.get("name") or col.get("column"))
        for col in (schema or {}).get("columns", [])
        if col.get("name") or col.get("column")
    }


def _has_any(text: str, terms: list[str] | tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def normalize_instructions(instructions: dict[str, Any] | None, allowed_columns: set[str]) -> dict[str, Any]:
    raw = dict(instructions or {})
    normalized: dict[str, Any] = {
        "row_grain": str(raw.get("row_grain") or "").strip() or None,
        "entities": {},
        "metrics": {},
        "default_date_column": None,
        "synonyms": {},
        "notes": str(raw.get("notes") or "").strip(),
    }

    for name, column in (raw.get("entities") or {}).items():
        col = str(column or "").strip()
        if col in allowed_columns:
            normalized["entities"][str(name).strip().lower()] = col

    for name, metric in (raw.get("metrics") or {}).items():
        if not isinstance(metric, dict):
            continue
        col = str(metric.get("column") or "").strip()
        agg = str(metric.get("aggregation") or "sum").strip().lower()
        if col not in allowed_columns or agg not in {"sum", "avg", "count", "count_distinct", "min", "max"}:
            continue
        synonyms = [str(s).strip().lower() for s in metric.get("synonyms", []) if str(s).strip()]
        normalized["metrics"][str(name).strip().lower()] = {
            "column": col,
            "aggregation": agg,
            "synonyms": synonyms,
        }

    date_col = str(raw.get("default_date_column") or "").strip()
    if date_col in allowed_columns:
        normalized["default_date_column"] = date_col

    for key, values in (raw.get("synonyms") or {}).items():
        if isinstance(values, list):
            clean = [str(v).strip().lower() for v in values if str(v).strip()]
            if clean:
                normalized["synonyms"][str(key).strip().lower()] = clean
    return normalized


def default_source_instructions(schema: dict[str, Any], display_name: str = "") -> dict[str, Any]:
    allowed = _columns(schema)
    lowered_name = display_name.lower()
    entities: dict[str, str] = {}
    metrics: dict[str, dict[str, Any]] = {}
    row_grain = "row"

    if "order_id" in allowed:
        entities["order"] = "order_id"
        metrics["orders"] = {
            "column": "order_id",
            "aggregation": "count_distinct",
            "synonyms": ["orders", "order count", "number of orders", "how many orders"],
        }
        row_grain = "line_item" if any(c in allowed for c in ("order_details_id", "quantity", "pizza_id")) else "order"
    if "order_details_id" in allowed:
        entities["line_item"] = "order_details_id"
    if "quantity" in allowed:
        metrics["items_sold"] = {
            "column": "quantity",
            "aggregation": "sum",
            "synonyms": ["items sold", "pizzas sold", "units sold", "quantity sold"],
        }
    if "total_price" in allowed:
        metrics["revenue"] = {
            "column": "total_price",
            "aggregation": "sum",
            "synonyms": ["revenue", "sales", "total sales"],
        }
    date_col = next((c for c in ("order_date", "order_datetime", "date", "created_at") if c in allowed), None)
    if "pizza" in lowered_name and "quantity" in allowed:
        row_grain = "line_item"

    return normalize_instructions(
        {
            "row_grain": row_grain,
            "entities": entities,
            "metrics": metrics,
            "default_date_column": date_col,
            "synonyms": {},
            "notes": "",
        },
        allowed,
    )


def detect_project_category(project: dict[str, Any] | None, source_rows: list[dict[str, Any]] | None = None) -> str:
    text_parts = [str((project or {}).get("title") or "")]
    for row in source_rows or []:
        text_parts.append(str(row.get("name") or ""))
        text_parts.append(str(row.get("kind") or ""))
    text = " ".join(text_parts).lower()
    if any(term in text for term in ("pizza", "sales", "order", "revenue", "customer")):
        return "sales"
    if any(term in text for term in ("invoice", "ledger", "finance", "payment", "expense")):
        return "finance"
    if any(term in text for term in ("stock", "inventory", "warehouse", "sku")):
        return "inventory"
    if any(term in text for term in ("ticket", "support", "case")):
        return "customer_support"
    if any(term in text for term in ("timetable", "schedule", "teacher", "class", "student", "enrollment", "school", "college")):
        return "education"
    if any(term in text for term in ("ops", "operation", "delivery")):
        return "operations"
    return "general"


def apply_instruction_rules(
    intent: dict[str, Any],
    question: str,
    allowed_columns: set[str],
    *,
    source_instructions: dict[str, Any] | None = None,
    project_instructions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = normalize_instructions(source_instructions, allowed_columns)
    project = normalize_instructions(project_instructions, allowed_columns)
    merged_metrics = {**project.get("metrics", {}), **source.get("metrics", {})}
    q = question.lower()
    next_intent = dict(intent or {})

    matched: list[dict[str, Any]] = []
    for name, metric in merged_metrics.items():
        terms = [name.replace("_", " ")] + list(metric.get("synonyms") or [])
        positions = [q.find(term) for term in terms if term and q.find(term) >= 0]
        if positions or any(re.search(rf"\b{re.escape(term)}\b", q) for term in terms if term):
            matched.append({
                "name": name,
                "column": metric["column"],
                "aggregation": metric["aggregation"],
                "_pos": min(positions) if positions else len(q),
            })

    order_col = source.get("entities", {}).get("order") or project.get("entities", {}).get("order")
    if not matched and order_col and _has_any(q, COUNT_WORDS) and re.search(r"\border(s)?\b", q):
        matched.append({"name": "orders", "column": order_col, "aggregation": "count_distinct", "_pos": q.find("order")})

    matched = sorted(matched, key=lambda item: item.get("_pos", len(q)))

    if len(matched) > 1:
        next_intent["metrics"] = [
            {key: value for key, value in metric.items() if key != "_pos"}
            for metric in matched[:5]
        ]
        next_intent["intent_type"] = "comparison"
        next_intent["dimensions"] = []
        next_intent["date_grain"] = None
        next_intent["applied_rules"] = ["instruction_metrics"]
    elif len(matched) == 1:
        metric = matched[0]
        next_intent["metric_column"] = metric["column"]
        next_intent["aggregation"] = metric["aggregation"]
        next_intent["metric_definition"] = metric["name"]
        next_intent["applied_rules"] = ["instruction_metric"]
        if metric["aggregation"] == "count_distinct":
            next_intent["count_distinct_column"] = metric["column"]

    if _has_any(q, ROW_WORDS) and _has_any(q, COUNT_WORDS):
        next_intent.pop("metrics", None)
        next_intent["aggregation"] = "count"
        next_intent["metric_column"] = None
        next_intent["applied_rules"] = ["row_count"]

    return next_intent


def build_instruction_context(
    *,
    source_instructions: dict[str, Any] | None,
    project_instructions: dict[str, Any] | None,
    memory_snippets: list[dict[str, Any]] | None,
    allowed_columns: set[str],
    char_budget: int = 3000,
) -> str:
    project_raw = dict(project_instructions or {})
    project_clean = normalize_instructions(project_raw, allowed_columns)
    if project_raw.get("category"):
        project_clean["category"] = str(project_raw.get("category"))[:80]
    if project_raw.get("notes"):
        project_clean["notes"] = str(project_raw.get("notes"))[:800]
    payload = {
        "source": normalize_instructions(source_instructions, allowed_columns),
        "project": project_clean,
        "memory": [
            {
                "title": str(item.get("title") or "")[:120],
                "content": str(item.get("content") or "")[:500],
            }
            for item in (memory_snippets or [])[:5]
        ],
    }
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(text) > char_budget:
        return text[: max(0, char_budget - 80)] + ',"truncated":true}'
    return text


def clarification_suggestions(schema: dict[str, Any], display_name: str) -> list[dict[str, Any]]:
    allowed = _columns(schema)
    suggestions: list[dict[str, Any]] = []
    if "order_id" in allowed and ("quantity" in allowed or "order_details_id" in allowed):
        suggestions.append({
            "id": "row_grain",
            "question": "This looks like an order line item file. Should one row be treated as a line item while orders are counted by distinct order_id?",
            "options": [
                {"label": "Line item", "value": "line_item"},
                {"label": "Order", "value": "order"},
                {"label": "Transaction", "value": "transaction"},
            ],
        })
    return suggestions
