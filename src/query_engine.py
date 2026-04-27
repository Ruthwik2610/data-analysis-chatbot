from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


METRICS = {
    "revenue": 'SUM("total_order_val") AS revenue',
    "order_count": 'COUNT(*) AS order_count',
    "quantity": 'SUM("qty") AS quantity',
    "avg_order_value": 'AVG("total_order_val") AS avg_order_value',
    "shipping_cost": 'SUM("shipping_cost") AS shipping_cost',
    "discount": 'SUM("discount_amt") AS discount',
    "tax": 'SUM("tax_amt") AS tax',
    "delivery_delay_days": 'AVG(date_diff(\'day\', "expected_delivery", "actual_delivery")) AS avg_delivery_delay_days',
}

METRIC_CANDIDATES = {
    "revenue": ["total_order_val", "revenue", "sales", "amount", "total", "order_total"],
    "quantity": ["qty", "quantity", "units", "items"],
    "avg_order_value": ["total_order_val", "revenue", "sales", "amount", "total", "order_total"],
    "shipping_cost": ["shipping_cost", "shipping", "freight"],
    "discount": ["discount_amt", "discount"],
    "tax": ["tax_amt", "tax"],
}

DIMENSION_ALIASES = {
    "customer": "cust_name",
    "customers": "cust_name",
    "customer segment": "cust_segment",
    "segment": "cust_segment",
    "product": "prod_name",
    "products": "prod_name",
    "category": "prod_category",
    "categories": "prod_category",
    "subcategory": "prod_subcategory",
    "brand": "prod_brand",
    "city": "ship_city",
    "location": "ship_city",
    "locations": "ship_city",
    "state": "ship_state",
    "country": "ship_country",
    "zone": "ship_zone",
    "carrier": "carrier_name",
    "warehouse": "warehouse_id",
    "payment": "payment_mode",
    "status": "order_status",
    "device": "device_type",
}

LOOKUP_COLUMNS = [
    "order_key",
    "order_datetime",
    "order_status",
    "cust_key",
    "cust_name",
    "cust_email",
    "cust_phone",
    "ship_city",
    "ship_state",
    "ship_country",
    "prod_key",
    "prod_name",
    "prod_category",
    "qty",
    "unit_price",
    "total_order_val",
    "payment_mode",
    "transaction_id",
    "tracking_no",
    "expected_delivery",
    "actual_delivery",
]


@dataclass
class QueryPlan:
    sql: str
    params: list[Any]
    display_type: str
    title: str
    how: str

    @property
    def cache_key(self) -> str:
        payload = json.dumps({"sql": self.sql, "params": self.params}, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def canonical_column(value: Any) -> str:
    return re.sub(r"[^0-9a-z]+", "_", str(value).strip().lower()).strip("_")


def infer_limit(question: str, fallback: int = 100) -> int:
    match = re.search(r"\btop\s+(\d{1,3})\b", question.lower())
    if match:
        return max(1, min(int(match.group(1)), 100))
    return fallback


def infer_metric(question: str, provided: Any = None) -> str:
    provided_metric = str(provided or "").strip().lower()
    if provided_metric in METRICS:
        return provided_metric
    q = question.lower()
    if any(term in q for term in ["quantity", "units", "items sold"]):
        return "quantity"
    if any(term in q for term in ["average order", "aov"]):
        return "avg_order_value"
    if "shipping" in q:
        return "shipping_cost"
    if "discount" in q:
        return "discount"
    if "tax" in q:
        return "tax"
    if any(term in q for term in ["delay", "late", "delivery time"]):
        return "delivery_delay_days"
    if any(term in q for term in ["orders", "count", "number of"]):
        return "order_count"
    return "revenue"


def infer_dimensions(question: str, provided: list[str] | None, allowed_columns: set[str]) -> list[str]:
    dims: list[str] = []
    for dim in provided or []:
        canonical = canonical_column(dim)
        if canonical in allowed_columns:
            dims.append(canonical)
    q = question.lower()
    if "location" in q and "location" in allowed_columns and "location" not in dims:
        dims.append("location")
    for phrase, column in DIMENSION_ALIASES.items():
        if phrase in q and column in allowed_columns and column not in dims:
            dims.append(column)
    return dims[:3]


def infer_date_grain(question: str, provided: Any = None) -> str | None:
    provided_grain = str(provided or "").strip().lower()
    if provided_grain in {"day", "week", "month", "quarter", "year"}:
        return provided_grain
    q = question.lower()
    if any(term in q for term in ["daily", "by day"]):
        return "day"
    if any(term in q for term in ["weekly", "by week"]):
        return "week"
    if any(term in q for term in ["monthly", "by month"]):
        return "month"
    if any(term in q for term in ["quarter", "quarterly"]):
        return "quarter"
    if any(term in q for term in ["yearly", "by year", "annual"]):
        return "year"
    if any(term in q for term in ["trend", "over time"]):
        return "month"
    return None


def heuristic_intent(question: str, allowed_columns: set[str]) -> dict[str, Any]:
    q = question.lower()
    lookup = extract_lookup_filters(question)
    if lookup and not looks_aggregate(question):
        return {
            "intent_type": "lookup",
            "metric": None,
            "dimensions": [],
            "filters": lookup,
            "date_grain": None,
            "limit": infer_limit(question, 20),
            "sort_direction": "desc",
            "requested_visualization": "table",
            "clarifying_question": None,
            "needs_escalation": False,
            "confidence": 0.72,
        }
    return {
        "intent_type": "trend" if any(term in q for term in ["trend", "over time", "monthly", "daily", "weekly"]) else "aggregate",
        "metric": infer_metric(question),
        "dimensions": infer_dimensions(question, [], allowed_columns),
        "filters": lookup,
        "date_grain": infer_date_grain(question),
        "limit": infer_limit(question, 100),
        "sort_direction": "desc",
        "requested_visualization": "auto",
        "clarifying_question": None,
        "needs_escalation": False,
        "confidence": 0.55,
    }


_PREFIXED_ID_PATTERNS = [
    ("order_key", r"\bORD-(\d+)\b", "ORD-"),
    ("cust_key", r"\bCUST-(\d+)\b", "CUST-"),
    ("prod_key", r"\bPROD-(\d+)\b", "PROD-"),
]

_BARE_KEY_PATTERNS = [
    ("order_key", r"\bord(?:er)?[_\s-]?key\s*[=:]\s*['\"]?(\d+)['\"]?", "ORD-"),
    ("cust_key", r"\bcust(?:omer)?[_\s-]?key\s*[=:]\s*['\"]?(\d+)['\"]?", "CUST-"),
    ("prod_key", r"\bprod(?:uct)?[_\s-]?key\s*[=:]\s*['\"]?(\d+)['\"]?", "PROD-"),
]


def extract_lookup_filters(question: str) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(column: str, value: str) -> None:
        key = (column, value)
        if key in seen:
            return
        seen.add(key)
        filters.append({"column": column, "operator": "=", "value": value})

    for column, pattern, prefix in _PREFIXED_ID_PATTERNS:
        for digits in re.findall(pattern, question, flags=re.I):
            add(column, f"{prefix}{digits}")
    for column, pattern, prefix in _BARE_KEY_PATTERNS:
        for digits in re.findall(pattern, question, flags=re.I):
            add(column, f"{prefix}{digits}")
    for match in re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", question, flags=re.I):
        add("cust_email", match)
    for match in re.findall(r"\b(?=[A-Z0-9]*\d)[A-Z0-9]{10,16}\b", question):
        add("transaction_id", match)
    return filters


_AGGREGATE_HINT_RE = re.compile(
    r"\b(total|sum|average|avg|mean|count|how\s+many|revenue|sales|earnings|spend|by\s+\w|per\s+\w|across|breakdown|trend|over\s+time)\b",
    re.I,
)


def looks_aggregate(question: str) -> bool:
    return bool(_AGGREGATE_HINT_RE.search(question))


def build_query_plan(intent: dict[str, Any], question: str, allowed_columns: set[str]) -> QueryPlan:
    intent_type = intent.get("intent_type") or "aggregate"
    if intent_type == "clarification":
        raise ValueError(intent.get("clarifying_question") or "I need one more detail to answer that.")
    if intent_type == "unsupported":
        raise ValueError("I can only answer questions grounded in the CSV data.")

    lookup_filters = extract_lookup_filters(question)
    aggregate_intents = {"aggregate", "trend", "comparison", "chart_request"}
    wants_aggregate = intent_type in aggregate_intents or looks_aggregate(question)

    if intent_type == "lookup" or (lookup_filters and not wants_aggregate):
        filters = lookup_filters or intent.get("filters") or []
        return build_lookup_plan(filters, intent, allowed_columns)

    if lookup_filters:
        merged = list(intent.get("filters") or [])
        existing = {(canonical_column(f.get("column", "")), str(f.get("value"))) for f in merged}
        for lf in lookup_filters:
            key = (canonical_column(lf["column"]), str(lf["value"]))
            if key not in existing:
                merged.append(lf)
                existing.add(key)
        intent = {**intent, "filters": merged}

    metric = infer_metric(question, intent.get("metric"))
    dimensions = infer_dimensions(question, intent.get("dimensions") or [], allowed_columns)
    date_grain = infer_date_grain(question, intent.get("date_grain"))
    limit = max(1, min(int(intent.get("limit") or infer_limit(question)), 500))
    direction = "ASC" if str(intent.get("sort_direction", "desc")).lower() == "asc" else "DESC"

    selects: list[str] = []
    groups: list[str] = []
    metric_sql, order_alias = metric_expression(metric, allowed_columns)
    if date_grain and "order_datetime" in allowed_columns:
        selects.append(f"date_trunc('{date_grain}', TRY_CAST(\"order_datetime\" AS TIMESTAMP)) AS period")
        groups.append("period")
    for dim in dimensions:
        selects.append(f"{quote_ident(dim)} AS {quote_ident(dim)}")
        groups.append(quote_ident(dim))
    selects.append(metric_sql)

    where_sql, params = build_filters(intent.get("filters") or [], allowed_columns)
    sql = f"SELECT {', '.join(selects)} FROM orders"
    if where_sql:
        sql += f" WHERE {where_sql}"
    if groups:
        sql += f" GROUP BY {', '.join(groups)}"
        if date_grain:
            sql += " ORDER BY period ASC NULLS LAST"
        else:
            sql += f" ORDER BY {quote_ident(order_alias)} {direction} NULLS LAST"
        sql += f" LIMIT {limit}"
    title = make_title(metric, dimensions, date_grain, limit)
    how = f"Metric: {metric}; grouped by: {', '.join(groups) if groups else 'none'}; filters: {len(params)} parameter(s)."
    return QueryPlan(sql=sql, params=params, display_type="auto", title=title, how=how)


def metric_expression(metric: str, allowed_columns: set[str]) -> tuple[str, str]:
    if metric == "order_count":
        return "COUNT(*) AS order_count", "order_count"
    if metric == "delivery_delay_days" and {"expected_delivery", "actual_delivery"} <= allowed_columns:
        return 'AVG(date_diff(\'day\', TRY_CAST("expected_delivery" AS TIMESTAMP), TRY_CAST("actual_delivery" AS TIMESTAMP))) AS avg_delivery_delay_days', "avg_delivery_delay_days"
    if metric == "avg_order_value":
        column = first_available(METRIC_CANDIDATES["avg_order_value"], allowed_columns)
        if column:
            return f"AVG(TRY_CAST({quote_ident(column)} AS DOUBLE)) AS avg_order_value", "avg_order_value"
        return "COUNT(*) AS order_count", "order_count"
    column = first_available(METRIC_CANDIDATES.get(metric, []), allowed_columns)
    if column:
        alias = metric if metric in {"revenue", "quantity", "discount", "tax"} else column
        return f"SUM(TRY_CAST({quote_ident(column)} AS DOUBLE)) AS {quote_ident(alias)}", alias
    return "COUNT(*) AS order_count", "order_count"


def first_available(candidates: list[str], allowed_columns: set[str]) -> str | None:
    for column in candidates:
        if column in allowed_columns:
            return column
    return None


def build_lookup_plan(filters: list[dict[str, Any]], intent: dict[str, Any], allowed_columns: set[str]) -> QueryPlan:
    selected = [quote_ident(col) for col in LOOKUP_COLUMNS if col in allowed_columns]
    where_sql, params = build_filters(filters, allowed_columns)
    limit = max(1, min(int(intent.get("limit") or 20), 100))
    sql = f"SELECT {', '.join(selected)} FROM orders"
    if where_sql:
        sql += f" WHERE {where_sql}"
    sql += ' ORDER BY "order_datetime" DESC NULLS LAST LIMIT ?'
    params.append(limit)
    return QueryPlan(
        sql=sql,
        params=params,
        display_type="table",
        title="Matching Records",
        how=f"Looked up matching records using {len(filters)} filter(s).",
    )


def build_filters(filters: list[dict[str, Any]], allowed_columns: set[str]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for flt in filters:
        column = canonical_column(flt.get("column", ""))
        if column not in allowed_columns:
            continue
        op = str(flt.get("operator", "=")).lower()
        value = flt.get("value")
        ident = quote_ident(column)
        if op == "contains":
            clauses.append(f"LOWER(CAST({ident} AS VARCHAR)) LIKE ?")
            params.append(f"%{str(value).lower()}%")
        elif op == "in" and isinstance(value, list):
            placeholders = ", ".join(["?"] * len(value))
            clauses.append(f"{ident} IN ({placeholders})")
            params.extend(value)
        elif op == "between" and isinstance(value, list) and len(value) == 2:
            clauses.append(f"{ident} BETWEEN ? AND ?")
            params.extend(value)
        elif op in {">=", "<=", ">", "<", "="}:
            clauses.append(f"{ident} {op} ?")
            params.append(value)
    return " AND ".join(clauses), params


def make_title(metric: str, dimensions: list[str], date_grain: str | None, limit: int) -> str:
    metric_name = metric.replace("_", " ").title()
    if date_grain:
        return f"{metric_name} Trend"
    if dimensions:
        return f"Top {limit} {dimensions[0].replace('_', ' ').title()} By {metric_name}"
    return metric_name


_GRAND_TOTAL_PATTERNS = [
    r"\bgrand total\b",
    r"\boverall total\b",
    r"\boverall sum\b",
    r"\bsum across\b",
    r"\btotal across\b",
    r"\bin total\b",
    r"\band\s+(?:the\s+)?total\b",
    r"\btotals?\s+and\s+(?:grand\s+)?total\b",
    r"\btotals?\s+and\b",
    r"\btotal\s+for\s+all\b",
    r"\ball\s+\w+\s+totals?\b",
]


def wants_grand_total(question: str) -> bool:
    q = question.lower()
    return any(re.search(p, q) for p in _GRAND_TOTAL_PATTERNS)


def build_total_plan(intent: dict[str, Any], allowed_columns: set[str]) -> QueryPlan:
    metric = infer_metric("", intent.get("metric"))
    metric_sql, alias = metric_expression(metric, allowed_columns)
    where_sql, params = build_filters(intent.get("filters") or [], allowed_columns)
    sql = f"SELECT {metric_sql} FROM orders"
    if where_sql:
        sql += f" WHERE {where_sql}"
    title = f"{metric.replace('_', ' ').title()} Grand Total"
    how = f"Aggregate of {metric} across all matching rows (no grouping or limit)."
    return QueryPlan(sql=sql, params=params, display_type="card", title=title, how=how)


def validate_readonly_sql(sql: str) -> None:
    lowered = re.sub(r"\s+", " ", sql).strip().lower()
    if not lowered.startswith("select "):
        raise ValueError("Only SELECT queries are allowed.")
    forbidden = [" insert ", " update ", " delete ", " drop ", " alter ", " create ", " attach ", " copy ", "pragma "]
    if any(token in f" {lowered} " for token in forbidden):
        raise ValueError("Unsafe SQL was rejected.")
