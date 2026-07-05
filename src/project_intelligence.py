from __future__ import annotations

import json
import re
from typing import Any

from src.domain_detection import detect_domain
from src.semantic_manifest import compact_semantic_context


COUNT_WORDS = ("how many", "count", "number of")
ROW_WORDS = ("row", "rows", "line item", "line items", "records")
VALID_AGGREGATIONS = {"sum", "avg", "count", "count_distinct", "min", "max"}
SEMANTIC_ROLES = {"metric", "measure", "dimension", "date", "id", "text", "unknown"}
PLACEHOLDER_TOKENS = ["n/a", "na", "none", "null", "unknown", "not available", "tbd", "-", "--"]


def _columns(schema: dict[str, Any] | None) -> set[str]:
    return {
        str(col.get("name") or col.get("column"))
        for col in (schema or {}).get("columns", [])
        if col.get("name") or col.get("column")
    }


def _has_any(text: str, terms: list[str] | tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _clean_terms(values: Any, *, limit: int = 10) -> list[str]:
    if not isinstance(values, list):
        return []
    clean: list[str] = []
    for value in values:
        term = re.sub(r"\s+", " ", str(value or "").strip().lower())
        if term and term not in clean:
            clean.append(term[:80])
        if len(clean) >= limit:
            break
    return clean


def _canonical(value: Any) -> str:
    return re.sub(r"[^0-9a-z]+", "_", str(value or "").strip().lower()).strip("_")


def _column_type(column: dict[str, Any]) -> str:
    return str(column.get("type") or column.get("dtype") or "").lower()


def _is_numeric_type(type_text: str) -> bool:
    return any(token in type_text for token in ("int", "double", "float", "decimal", "numeric", "real"))


def _is_date_type(type_text: str) -> bool:
    return any(token in type_text for token in ("date", "time", "timestamp"))


def _is_id_name(name: str) -> bool:
    canon = _canonical(name)
    return (
        canon == "id"
        or canon.endswith("_id")
        or canon.endswith("_key")
        or canon.endswith("_no")
        or canon.endswith("_number")
        or canon in {"vno", "voucher_no", "voucher_number", "sku"}
    )


def _is_date_name(name: str) -> bool:
    canon = _canonical(name)
    return bool(re.search(r"(^|_)(date|datetime|timestamp|time)$|_at$|_on$", canon))


def _metric_terms(name: str) -> set[str]:
    canon = _canonical(name)
    terms: set[str] = set()
    if any(token in canon for token in ("sales", "sale", "revenue", "turnover", "gmv", "gross_amount", "gross_value", "total_amount", "total_price", "order_val")):
        terms.update({"sales", "revenue", "turnover"})
    if any(token in canon for token in ("profit", "margin", "net_income", "net_profit", "loss")):
        terms.update({"profit", "loss", "margin"})
    if any(token in canon for token in ("quantity", "qty", "units", "items", "item_count")):
        terms.update({"quantity", "items", "units"})
    if "discount" in canon:
        terms.add("discount")
    if "tax" in canon or canon in {"cgst", "sgst", "igst", "gst"}:
        terms.update({"tax", "gst"})
    if "debit" in canon:
        terms.add("debit")
    if "credit" in canon:
        terms.add("credit")
    return terms


def _guess_role(column: dict[str, Any]) -> str:
    name = str(column.get("name") or column.get("column") or "")
    type_text = _column_type(column)
    if _is_date_type(type_text) or _is_date_name(name):
        return "date"
    if _is_id_name(name):
        return "id"
    if _is_numeric_type(type_text) or _metric_terms(name):
        return "metric"
    return "dimension"


def _business_name(name: str) -> str:
    return _canonical(name).replace("_", " ") or str(name)


def _entity_name_for_column(name: str) -> str | None:
    canon = _canonical(name)
    for entity in ("order", "customer", "cust", "product", "prod", "account", "branch", "location", "voucher", "invoice", "user"):
        if entity in canon:
            return {"cust": "customer", "prod": "product"}.get(entity, entity)
    if _is_id_name(name):
        return canon.removesuffix("_id").removesuffix("_key").removesuffix("_no") or "id"
    return None


def _default_metric_name(column: str, synonyms: list[str]) -> str:
    terms = set(synonyms) | _metric_terms(column)
    if {"sales", "revenue", "turnover"} & terms:
        return "revenue"
    if {"profit", "loss", "margin"} & terms:
        return "profit"
    if {"quantity", "items", "units"} & terms:
        return "items_sold"
    if "discount" in terms:
        return "discount"
    if {"tax", "gst"} & terms:
        return "tax"
    if "debit" in terms:
        return "debit"
    if "credit" in terms:
        return "credit"
    return _canonical(column) or "metric"


def _default_aggregation(column: str, role: str) -> str | None:
    canon = _canonical(column)
    if role == "id":
        return "count_distinct"
    if role not in {"metric", "measure"}:
        return None
    if any(token in canon for token in ("rate", "ratio", "percent", "percentage", "margin")):
        return "avg"
    return "sum"


def _deterministic_semantic_profile(schema: dict[str, Any], display_name: str = "") -> dict[str, Any]:
    columns: dict[str, Any] = {}
    default_date_column: str | None = None
    for column in (schema or {}).get("columns", []):
        if not isinstance(column, dict):
            continue
        name = str(column.get("name") or column.get("column") or "").strip()
        if not name:
            continue
        role = _guess_role(column)
        synonyms = sorted(_metric_terms(name) | {_business_name(name)})
        entity = _entity_name_for_column(name) if role in {"id", "dimension"} else None
        if role == "date" and default_date_column is None:
            default_date_column = name
            synonyms = list(dict.fromkeys(synonyms + ["date", "time"]))
        columns[name] = {
            "role": role,
            "business_name": _business_name(name),
            "meaning": f"{_business_name(name)} column",
            "synonyms": synonyms[:8],
            "default_aggregation": _default_aggregation(name, role),
            "entity": entity,
        }

    return {
        "version": 1,
        "source": "deterministic",
        "columns": columns,
        "data_quality": {
            "placeholder_tokens": PLACEHOLDER_TOKENS,
            "notes": [
                "Check nulls, empty strings, placeholder values, duplicate rows, invalid dates, and numeric parse anomalies by column."
            ],
        },
        "default_date_column": default_date_column,
        "row_grain": "line_item" if "pizza" in display_name.lower() and "quantity" in columns else "row",
    }


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
    if raw.get("profile_source"):
        normalized["profile_source"] = str(raw.get("profile_source"))[:40]

    for name, column in (raw.get("entities") or {}).items():
        col = str(column or "").strip()
        if col in allowed_columns:
            normalized["entities"][str(name).strip().lower()] = col

    for name, metric in (raw.get("metrics") or {}).items():
        if not isinstance(metric, dict):
            continue
        col = str(metric.get("column") or "").strip()
        agg = str(metric.get("aggregation") or "sum").strip().lower()
        if col not in allowed_columns or agg not in VALID_AGGREGATIONS:
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

    profile_raw = raw.get("semantic_profile") if isinstance(raw.get("semantic_profile"), dict) else {}
    profile_columns: dict[str, Any] = {}
    for column, payload in (profile_raw.get("columns") or raw.get("columns") or {}).items():
        col = str(column or "").strip()
        if col not in allowed_columns or not isinstance(payload, dict):
            continue
        role = str(payload.get("role") or "unknown").strip().lower()
        if role == "measure":
            role = "metric"
        if role not in SEMANTIC_ROLES:
            role = "unknown"
        aggregation = str(payload.get("default_aggregation") or "").strip().lower()
        if aggregation not in VALID_AGGREGATIONS:
            aggregation = None
        entity = str(payload.get("entity") or "").strip().lower() or None
        profile_columns[col] = {
            "role": role,
            "business_name": str(payload.get("business_name") or _business_name(col)).strip()[:80],
            "meaning": str(payload.get("meaning") or "").strip()[:240],
            "synonyms": _clean_terms(payload.get("synonyms")),
            "default_aggregation": aggregation,
            "entity": entity,
        }

    if profile_columns:
        semantic_profile = {
            "version": int(profile_raw.get("version") or 1) if str(profile_raw.get("version") or "1").isdigit() else 1,
            "source": str(profile_raw.get("source") or raw.get("profile_source") or "deterministic")[:40],
            "columns": profile_columns,
        }
        data_quality = profile_raw.get("data_quality") if isinstance(profile_raw.get("data_quality"), dict) else raw.get("data_quality")
        if isinstance(data_quality, dict):
            semantic_profile["data_quality"] = {
                "placeholder_tokens": _clean_terms(data_quality.get("placeholder_tokens"), limit=20) or PLACEHOLDER_TOKENS,
                "notes": [str(note).strip()[:160] for note in (data_quality.get("notes") or []) if str(note).strip()][:8],
            }
        normalized["semantic_profile"] = semantic_profile
        normalized["profile_source"] = semantic_profile["source"]

        if normalized["default_date_column"] is None:
            profile_date = str(profile_raw.get("default_date_column") or "").strip()
            if profile_date in allowed_columns:
                normalized["default_date_column"] = profile_date
            else:
                normalized["default_date_column"] = next((col for col, payload in profile_columns.items() if payload["role"] == "date"), None)

        for col, payload in profile_columns.items():
            role = payload["role"]
            if role in {"metric", "measure"}:
                metric_name = _default_metric_name(col, payload.get("synonyms") or [])
                if metric_name not in normalized["metrics"]:
                    normalized["metrics"][metric_name] = {
                        "column": col,
                        "aggregation": payload.get("default_aggregation") or "sum",
                        "synonyms": _clean_terms(
                            [payload.get("business_name"), *(payload.get("synonyms") or []), col.replace("_", " ")]
                        ),
                    }
            if role == "id" and payload.get("entity"):
                normalized["entities"].setdefault(str(payload["entity"]).strip().lower(), col)

    if raw.get("data_quality") and "semantic_profile" not in normalized:
        dq = raw.get("data_quality")
        if isinstance(dq, dict):
            normalized["data_quality"] = {
                "placeholder_tokens": _clean_terms(dq.get("placeholder_tokens"), limit=20) or PLACEHOLDER_TOKENS,
                "notes": [str(note).strip()[:160] for note in (dq.get("notes") or []) if str(note).strip()][:8],
            }
    return normalized


def _default_instruction_payload(schema: dict[str, Any], display_name: str = "") -> dict[str, Any]:
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

    return {
        "row_grain": row_grain,
        "entities": entities,
        "metrics": metrics,
        "default_date_column": date_col,
        "synonyms": {},
        "notes": "",
    }


def build_source_semantic_profile(
    schema: dict[str, Any],
    display_name: str = "",
    *,
    ai_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    allowed = _columns(schema)
    base = _default_instruction_payload(schema, display_name)
    deterministic = _deterministic_semantic_profile(schema, display_name)
    profile = dict(deterministic)
    profile["columns"] = dict(deterministic.get("columns") or {})
    profile_source = "deterministic"

    if isinstance(ai_profile, dict):
        ai_columns = ai_profile.get("columns") if isinstance(ai_profile.get("columns"), dict) else {}
        if ai_columns:
            profile["columns"] = {**profile["columns"], **ai_columns}
            profile_source = "ai"
        for key in ("row_grain", "default_date_column", "data_quality"):
            if ai_profile.get(key):
                profile[key] = ai_profile[key]

    instructions = {
        **base,
        "profile_source": profile_source,
        "semantic_profile": {
            "version": 1,
            "source": profile_source,
            "columns": profile.get("columns") or {},
            "data_quality": profile.get("data_quality") or deterministic["data_quality"],
            "default_date_column": profile.get("default_date_column"),
            "row_grain": profile.get("row_grain"),
        },
    }

    if isinstance(ai_profile, dict):
        if isinstance(ai_profile.get("metrics"), dict):
            instructions["metrics"] = {**instructions["metrics"], **ai_profile["metrics"]}
        if isinstance(ai_profile.get("entities"), dict):
            instructions["entities"] = {**instructions["entities"], **ai_profile["entities"]}
        if ai_profile.get("row_grain"):
            instructions["row_grain"] = str(ai_profile["row_grain"])
        if ai_profile.get("default_date_column"):
            instructions["default_date_column"] = ai_profile["default_date_column"]

    normalized = normalize_instructions(instructions, allowed)
    if normalized.get("semantic_profile"):
        normalized["data_quality"] = normalized["semantic_profile"].get("data_quality", {})
    return normalized


def default_source_instructions(schema: dict[str, Any], display_name: str = "") -> dict[str, Any]:
    return build_source_semantic_profile(schema, display_name)


def detect_project_category(project: dict[str, Any] | None, source_rows: list[dict[str, Any]] | None = None) -> str:
    text_parts = [str((project or {}).get("title") or "")]
    all_schemas: list[dict[str, Any]] = []

    for row in source_rows or []:
        text_parts.append(str(row.get("name") or ""))
        text_parts.append(str(row.get("kind") or ""))
        # Check direct columns list
        cols = row.get("columns") or []
        col_dicts: list[dict[str, Any]] = []
        if isinstance(cols, list):
            for c in cols:
                if isinstance(c, dict):
                    text_parts.append(str(c.get("name") or c.get("column") or ""))
                    col_dicts.append(c)
                else:
                    text_parts.append(str(c))
                    col_dicts.append({"name": str(c)})

        # Check schema_json if present
        schema_json = row.get("schema_json")
        if schema_json:
            try:
                schema = json.loads(schema_json)
                for c in schema.get("columns", []):
                    text_parts.append(str(c.get("name") or c.get("column") or ""))
                all_schemas.append(schema)
            except Exception:
                pass
        elif col_dicts:
            all_schemas.append({"columns": col_dicts})

    # ── Schema-signal domain detection (travel, education) ────────────────
    for schema in all_schemas:
        domain = detect_domain(schema)
        if domain == "travel":
            return "travel"
        if domain == "education":
            return "education"

    # ── Keyword fallback ─────────────────────────────────────────────────
    text = " ".join(text_parts).lower()
    if any(term in text for term in ("airline", "flight", "departure", "arrival", "airport", "cabin", "pnr", "itinerary")):
        return "travel"
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

    deduped: list[dict[str, Any]] = []
    seen_metric_columns: set[tuple[str, str]] = set()
    for metric in sorted(matched, key=lambda item: item.get("_pos", len(q))):
        key = (metric["column"], metric["aggregation"])
        if key in seen_metric_columns:
            continue
        seen_metric_columns.add(key)
        deduped.append(metric)
    matched = deduped

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

    profile_columns = {
        **((project.get("semantic_profile") or {}).get("columns") or {}),
        **((source.get("semantic_profile") or {}).get("columns") or {}),
    }

    if not next_intent.get("dimensions"):
        dimensions: list[str] = []
        for column, payload in profile_columns.items():
            if column not in allowed_columns or not isinstance(payload, dict):
                continue
            role = str(payload.get("role") or "").lower()
            if role not in {"dimension", "id", "text"}:
                continue
            terms = _clean_terms([payload.get("business_name"), *(payload.get("synonyms") or []), column.replace("_", " ")])
            cue_match = any(re.search(rf"\b(?:by|per|across|split by|breakdown by|broken down by)\s+{re.escape(term)}s?\b", q) for term in terms)
            bare_match = any(re.search(rf"\b{re.escape(term)}s?\b", q) for term in terms) and re.search(
                r"\b(loss[-\s]?making|negative\s+profit|unprofitable|top|highest|lowest|best|worst)\b",
                q,
            )
            if cue_match or bare_match:
                dimensions.append(column)
            if len(dimensions) >= 3:
                break
        if dimensions:
            next_intent["dimensions"] = dimensions
            next_intent["applied_rules"] = list(dict.fromkeys([*(next_intent.get("applied_rules") or []), "semantic_dimensions"]))

    if re.search(r"\b(loss[-\s]?making|negative\s+profit|unprofitable)\b", q):
        profit_metric = next(
            (
                metric
                for metric in merged_metrics.values()
                if metric.get("column") in allowed_columns
                and any(term in {"profit", "loss", "margin"} for term in _clean_terms(metric.get("synonyms") or []))
            ),
            None,
        )
        if profit_metric:
            filters = list(next_intent.get("filters") or [])
            if not any(f.get("column") == profit_metric["column"] and f.get("operator") == "<" for f in filters if isinstance(f, dict)):
                filters.append({"column": profit_metric["column"], "operator": "<", "value": 0})
            next_intent["filters"] = filters
            next_intent["metric_column"] = profit_metric["column"]
            next_intent["aggregation"] = profit_metric["aggregation"]
            next_intent["applied_rules"] = list(dict.fromkeys([*(next_intent.get("applied_rules") or []), "semantic_loss_filter"]))

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
        category = str(project_raw.get("category"))[:80]
        project_clean["category"] = category
        if category == "education":
            project_clean["education_context"] = "This is an education dataset. If asked for a timetable or schedule by an entity (like professor or class), generate a PIVOT query to draw a whole table with days/hours as columns and the entity as rows."
    if project_raw.get("notes"):
        project_clean["notes"] = str(project_raw.get("notes"))[:800]
    payload = {
        "source": normalize_instructions(source_instructions, allowed_columns),
        "project": project_clean,
        "semantic": {
            "source": compact_semantic_context(source_instructions, allowed_columns=allowed_columns),
            "project": compact_semantic_context(project_instructions, allowed_columns=allowed_columns),
        },
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
