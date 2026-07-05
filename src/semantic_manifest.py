from __future__ import annotations

import re
from typing import Any


VALID_AGGREGATIONS = {"sum", "avg", "count", "count_distinct", "min", "max"}
DEFAULT_CATALOG = "wren"
DEFAULT_SCHEMA = "main"


def _column_name(column: dict[str, Any]) -> str | None:
    name = column.get("name") or column.get("column")
    if not name:
        return None
    return str(name)


def _column_type(column: dict[str, Any]) -> str:
    raw = column.get("type") or column.get("dtype") or "VARCHAR"
    text = str(raw).strip().upper()
    return text or "VARCHAR"


def _clean_name(value: Any) -> str:
    return re.sub(r"[^0-9a-zA-Z_]+", "_", str(value or "").strip()).strip("_")


def build_wren_mdl_from_schema(
    schema: dict[str, Any],
    *,
    model_name: str,
    table_name: str,
    data_source: str,
    catalog: str = DEFAULT_CATALOG,
    schema_name: str = DEFAULT_SCHEMA,
    relationships: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the minimal Wren MDL shape DataChat can generate from a source schema."""
    safe_model = _clean_name(model_name) or "orders"
    safe_table = table_name or safe_model
    columns: list[dict[str, Any]] = []
    for column in schema.get("columns") or []:
        if not isinstance(column, dict):
            continue
        name = _column_name(column)
        if not name:
            continue
        columns.append({
            "name": name,
            "type": _column_type(column),
            "isCalculated": False,
        })

    return {
        "catalog": catalog,
        "schema": schema_name,
        "dataSource": data_source,
        "models": [
            {
                "name": safe_model,
                "tableReference": {"catalog": "", "schema": schema_name, "table": safe_table},
                "columns": columns,
            }
        ],
        "relationships": list(relationships or []),
    }


def _metric_expression(metric: dict[str, Any]) -> str | None:
    expression = str(metric.get("expression") or "").strip()
    if expression:
        return expression
    column = str(metric.get("column") or "").strip()
    aggregation = str(metric.get("aggregation") or "sum").strip().lower()
    if not column or aggregation not in VALID_AGGREGATIONS:
        return None
    return f"{aggregation}({column})"


def compact_semantic_context(instructions: dict[str, Any] | None, *, allowed_columns: set[str]) -> dict[str, Any]:
    """Return a compact, prompt-safe semantic context from DataChat instructions.

    This is intentionally conservative: invalid column references are omitted
    instead of being handed to the model as if they were usable business facts.
    """
    raw = dict(instructions or {})
    context: dict[str, Any] = {
        "row_grain": str(raw.get("row_grain") or "").strip() or None,
        "columns": {},
        "entities": {},
        "metrics": {},
        "relationships": [],
        "routing": {},
    }

    profile = raw.get("semantic_profile") if isinstance(raw.get("semantic_profile"), dict) else {}
    for name, payload in sorted((profile.get("columns") or {}).items()):
        column = str(name or "").strip()
        if column not in allowed_columns or not isinstance(payload, dict):
            continue
        item: dict[str, Any] = {
            "role": str(payload.get("role") or "unknown")[:40],
        }
        business_name = str(payload.get("business_name") or "").strip()
        if business_name:
            item["business_name"] = business_name[:80]
        synonyms = [str(s).strip().lower() for s in payload.get("synonyms", []) if str(s).strip()]
        if synonyms:
            item["synonyms"] = synonyms[:8]
        aggregation = str(payload.get("default_aggregation") or "").strip().lower()
        if aggregation:
            item["default_aggregation"] = aggregation
        meaning = str(payload.get("meaning") or "").strip()
        if meaning:
            item["meaning"] = meaning[:160]
        context["columns"][column] = item

    for name, column in sorted((raw.get("entities") or {}).items()):
        col = str(column or "").strip()
        if col in allowed_columns:
            context["entities"][str(name).strip().lower()] = col

    for name, metric in sorted((raw.get("metrics") or {}).items()):
        if not isinstance(metric, dict):
            continue
        column = str(metric.get("column") or "").strip()
        if column and column not in allowed_columns:
            continue
        expression = _metric_expression(metric)
        if not expression:
            continue
        synonyms = [str(s).strip().lower() for s in metric.get("synonyms", []) if str(s).strip()]
        payload = {"expression": expression}
        if synonyms:
            payload["synonyms"] = synonyms
        default_date_column = str(metric.get("default_date_column") or "").strip()
        if default_date_column and default_date_column in allowed_columns:
            payload["default_date_column"] = default_date_column
        fmt = str(metric.get("format") or "").strip()
        if fmt:
            payload["format"] = fmt
        context["metrics"][str(name).strip().lower()] = payload

    for rel in raw.get("relationships") or []:
        if not isinstance(rel, dict):
            continue
        from_model = str(rel.get("from_model") or "").strip()
        from_column = str(rel.get("from_column") or "").strip()
        to_model = str(rel.get("to_model") or "").strip()
        to_column = str(rel.get("to_column") or "").strip()
        if not all([from_model, from_column, to_model, to_column]):
            continue
        cardinality = str(rel.get("cardinality") or "unknown").strip()
        approval = "approved" if rel.get("approved") else "suggested"
        context["relationships"].append(
            f"{from_model}.{from_column} -> {to_model}.{to_column} ({cardinality}, {approval})"
        )

    routing = raw.get("routing")
    if isinstance(routing, dict):
        context["routing"] = {
            key: [str(item) for item in value if str(item).strip()]
            for key, value in routing.items()
            if isinstance(value, list)
        }

    data_quality = profile.get("data_quality") if isinstance(profile.get("data_quality"), dict) else raw.get("data_quality")
    if isinstance(data_quality, dict):
        context["data_quality"] = {
            "placeholder_tokens": [str(item) for item in (data_quality.get("placeholder_tokens") or [])[:20]],
            "notes": [str(item) for item in (data_quality.get("notes") or [])[:8]],
        }

    return context
