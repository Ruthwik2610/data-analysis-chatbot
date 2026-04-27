from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


VALID_AGGREGATIONS = {"sum", "avg", "count", "min", "max"}

# Hint words used only by the offline heuristic when neither the LLM nor the
# question text identified a column. Each entry is a substring to look for in
# the column name; the first match wins. The LLM-driven path bypasses this.
_FALLBACK_METRIC_HINTS = (
    "revenue", "sales", "amount", "value", "total",
    "price", "cost",
    "qty", "quantity",
    "salary", "wage", "pay", "score",
)

# Substrings that disqualify a column from being treated as a fallback metric
# (these are typically identifiers, dates, or text fields).
_NON_METRIC_SUBSTRINGS = (
    "date", "datetime", "time", "_at", "_id", "key",
    "phone", "pincode", "checksum", "address", "email", "name",
)

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


def infer_aggregation(question: str, provided: Any = None) -> str:
    provided_agg = str(provided or "").strip().lower()
    if provided_agg in VALID_AGGREGATIONS:
        return provided_agg
    q = question.lower()
    if any(term in q for term in ("average", " avg ", " avg.", "mean")) or q.startswith("avg "):
        return "avg"
    if any(term in q for term in ("how many", "number of")) or re.search(r"\bcount\b", q):
        return "count"
    if re.search(r"\bmax(imum)?\b", q):
        return "max"
    if re.search(r"\bmin(imum)?\b", q):
        return "min"
    return "sum"


def find_column_in_question(
    question: str,
    allowed_columns: set[str],
    exclude: set[str] | frozenset[str] = frozenset(),
) -> str | None:
    """Return a column name (excluding `exclude`) that appears as a phrase in the question.
    Underscores in column names are treated as flexible separators, so 'unit_price'
    matches 'unit price' or 'unit-price'. Longer column names are tried first to
    prefer specific over generic matches."""
    q = question.lower()
    candidates = sorted((c for c in allowed_columns if c not in exclude), key=len, reverse=True)
    for col in candidates:
        parts = col.split("_")
        pattern = r"[\s_\-]?".join(re.escape(p) for p in parts) if len(parts) > 1 else re.escape(col)
        if re.search(rf"\b{pattern}\b", q):
            return col
    return None


def fallback_metric_column(
    allowed_columns: set[str],
    exclude: set[str] | frozenset[str] = frozenset(),
) -> str | None:
    """Pick a column name that looks like a metric, used only when the question
    didn't name one explicitly. Tries hint substrings in priority order."""
    candidates = [c for c in allowed_columns if c not in exclude]
    for hint in _FALLBACK_METRIC_HINTS:
        for col in candidates:
            if any(bad in col for bad in _NON_METRIC_SUBSTRINGS):
                continue
            if hint in col:
                return col
    return None


def infer_metric_column(
    question: str,
    provided: Any,
    allowed_columns: set[str],
    exclude: set[str] | frozenset[str] = frozenset(),
) -> str | None:
    canonical = canonical_column(provided) if provided else ""
    if canonical and canonical in allowed_columns:
        return canonical
    found = find_column_in_question(question, allowed_columns, exclude=exclude)
    if found and found not in exclude:
        return found
    return fallback_metric_column(allowed_columns, exclude=exclude)


def infer_dimensions(question: str, provided: list[str] | None, allowed_columns: set[str]) -> list[str]:
    dims: list[str] = []
    for dim in provided or []:
        canonical = canonical_column(dim)
        if canonical in allowed_columns:
            dims.append(canonical)
    if dims:
        return dims[:3]
    q = question.lower()
    if "location" in q and "location" in allowed_columns:
        dims.append("location")
    for phrase, column in DIMENSION_ALIASES.items():
        if phrase in q and column in allowed_columns and column not in dims:
            dims.append(column)
    return dims[:3]


def infer_date_grain(question: str, provided: Any = None) -> str | None:
    """Trust the LLM's grain — it's prompted to map 'by month' / 'monthly' /
    'month wise' / 'trend' to date_grain. This function only fills in when the
    LLM returned nothing (offline heuristic path)."""
    provided_grain = str(provided or "").strip().lower()
    if provided_grain in {"day", "week", "month", "quarter", "year"}:
        return provided_grain
    q = question.lower()
    if any(term in q for term in ("monthly", "by month", "trend", "over time")):
        return "month"
    if "daily" in q or "by day" in q:
        return "day"
    if "weekly" in q or "by week" in q:
        return "week"
    if "quarterly" in q or "by quarter" in q:
        return "quarter"
    if "yearly" in q or "by year" in q or "annual" in q:
        return "year"
    return None


def heuristic_intent(question: str, allowed_columns: set[str]) -> dict[str, Any]:
    """Offline fallback used only when no LLM is reachable. Produces an
    aggregate intent — without an LLM we can't reliably parse arbitrary IDs
    into lookup filters, so the offline path always defaults to aggregation
    over the inferred metric/dimensions/grain."""
    q = question.lower()
    dimensions = infer_dimensions(question, [], allowed_columns)
    aggregation = infer_aggregation(question)
    metric_column = (
        None if aggregation == "count"
        else infer_metric_column(question, None, allowed_columns, exclude=set(dimensions))
    )
    return {
        "intent_type": "trend" if any(term in q for term in ["trend", "over time", "monthly", "daily", "weekly"]) else "aggregate",
        "metric_column": metric_column,
        "aggregation": aggregation,
        "dimensions": dimensions,
        "filters": [],
        "date_grain": infer_date_grain(question),
        "limit": infer_limit(question, 100),
        "sort_direction": "desc",
        "requested_visualization": "auto",
        "clarifying_question": None,
        "needs_escalation": False,
        "confidence": 0.55,
    }


# Wider net of "this question has *some* analytical intent": aggregations,
# rankings, time grain words, comparisons, and explicit date/time tokens that
# the LLM would normally pick up as a filter.
_INTENT_HINT_RE = re.compile(
    r"\b(total|sum|average|avg|mean|count|number\s+of|how\s+many|"
    r"top|bottom|highest|lowest|max(?:imum)?|min(?:imum)?|largest|smallest|biggest|"
    r"daily|weekly|monthly|yearly|quarterly|annual|annually|trend|over\s+time|"
    r"by\s+\w+|per\s+\w+|across|breakdown|split|compare|comparison|versus|vs\.?|between|"
    r"\d{4}|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|"
    r"yesterday|today|tomorrow|last|recent)\b",
    re.I,
)


def is_underspecified(intent: dict[str, Any], question: str, allowed_columns: set[str]) -> bool:
    """Return True when the intent has nothing to anchor a query — no filters,
    no dimensions, no time grain, no analytical hint in the question, and no
    real column referenced. Avoids fitting "give me orders" to an arbitrary
    SUM(some_column) and gives the user a chance to clarify instead."""
    intent_type = intent.get("intent_type") or "aggregate"
    if intent_type in {"clarification", "unsupported"}:
        return False
    if intent_type == "lookup":
        # lookup queries are explicit — surface a sample of rows even if vague.
        return False
    if intent.get("filters") or intent.get("dimensions") or intent.get("date_grain"):
        return False
    if _INTENT_HINT_RE.search(question or ""):
        return False
    if find_column_in_question(question, allowed_columns):
        return False
    return True


def underspecified_clarification(allowed_columns: set[str], source_name: str = "this dataset") -> str:
    """Build a friendly clarification message that proposes example asks
    grounded in the actual schema."""
    metric = fallback_metric_column(allowed_columns)
    date_col = primary_date_column(allowed_columns)
    examples: list[str] = []
    if metric:
        pretty = metric.replace("_", " ")
        first_word = pretty.split()[0].lower() if pretty else ""
        # Avoid "total total ...": skip the "total" prefix if the column already starts with it.
        if first_word in {"total", "sum", "avg", "average", "count"}:
            examples.append(pretty)
        else:
            examples.append(f"total {pretty}")
        examples.append(f"top 5 by {pretty}")
        if date_col:
            examples.append(f"{pretty} by month")
    else:
        # No obvious metric column — fall back to suggesting a breakdown by a non-id column.
        non_id = next(
            (c for c in allowed_columns
             if not any(bad in c for bad in _NON_METRIC_SUBSTRINGS)),
            None,
        )
        if non_id:
            examples.append(f"breakdown by {non_id.replace('_', ' ')}")
        examples.append("show me the first 10 rows")
    examples.append("how many rows in total")
    return (
        f"Could you tell me a bit more about what you'd like from {source_name}? "
        f"For example: \"" + "\", \"".join(examples[:3]) + "\"."
    )


def build_query_plan(intent: dict[str, Any], question: str, allowed_columns: set[str]) -> QueryPlan:
    intent_type = intent.get("intent_type") or "aggregate"
    if intent_type == "clarification":
        raise ValueError(intent.get("clarifying_question") or "I need one more detail to answer that.")
    if intent_type == "unsupported":
        raise ValueError("I can only answer questions grounded in the CSV data.")

    if intent_type == "lookup":
        return build_lookup_plan(intent.get("filters") or [], intent, allowed_columns)

    dimensions = infer_dimensions(question, intent.get("dimensions") or [], allowed_columns)
    aggregation = infer_aggregation(question, intent.get("aggregation"))
    metric_column = (
        None if aggregation == "count"
        else infer_metric_column(question, intent.get("metric_column"), allowed_columns, exclude=set(dimensions))
    )
    date_grain = infer_date_grain(question, intent.get("date_grain"))
    limit = max(1, min(int(intent.get("limit") or infer_limit(question)), 500))
    direction = "ASC" if str(intent.get("sort_direction", "desc")).lower() == "asc" else "DESC"

    selects: list[str] = []
    groups: list[str] = []
    metric_sql, order_alias = metric_expression(metric_column, aggregation, allowed_columns)
    date_column = primary_date_column(allowed_columns)
    has_period = bool(date_grain and date_column)
    if has_period:
        selects.append(f"date_trunc('{date_grain}', TRY_CAST({quote_ident(date_column)} AS TIMESTAMP)) AS period")
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
        if has_period:
            sql += " ORDER BY period ASC NULLS LAST"
        else:
            sql += f" ORDER BY {quote_ident(order_alias)} {direction} NULLS LAST"
        sql += f" LIMIT {limit}"
    title = make_title(metric_column, aggregation, dimensions, date_grain, limit)
    how = (
        f"Metric: {aggregation}({metric_column or '*'}); "
        f"grouped by: {', '.join(groups) if groups else 'none'}; "
        f"filters: {len(params)} parameter(s)."
    )
    return QueryPlan(sql=sql, params=params, display_type="auto", title=title, how=how)


def metric_expression(
    metric_column: str | None,
    aggregation: str,
    allowed_columns: set[str],
) -> tuple[str, str]:
    """Build the SELECT expression for an aggregation over an actual schema column.
    Returns (sql_fragment, alias). Falls back to COUNT(*) when the column is missing
    or the aggregation needs a numeric column but none was identified."""
    agg = (aggregation or "sum").lower()
    if agg not in VALID_AGGREGATIONS:
        agg = "sum"
    if agg == "count" or not metric_column or metric_column not in allowed_columns:
        return "COUNT(*) AS count", "count"
    op = agg.upper()
    return (
        f"{op}(TRY_CAST({quote_ident(metric_column)} AS DOUBLE)) AS {quote_ident(metric_column)}",
        metric_column,
    )


_DATE_COLUMN_HINTS = ("datetime", "timestamp", "date", "_at", "_time")
_DATE_COLUMN_PRIORITY = ("order_datetime", "order_date", "transaction_datetime", "transaction_date", "created_at")


def primary_date_column(allowed_columns: set[str]) -> str | None:
    """Pick a column to use for time-grouped queries. Prefers a known canonical
    name, falls back to any column with a date-like substring."""
    for col in _DATE_COLUMN_PRIORITY:
        if col in allowed_columns:
            return col
    for col in allowed_columns:
        if any(hint in col for hint in _DATE_COLUMN_HINTS):
            return col
    return None


def build_lookup_plan(filters: list[dict[str, Any]], intent: dict[str, Any], allowed_columns: set[str]) -> QueryPlan:
    cols = sorted(allowed_columns)
    selected = [quote_ident(col) for col in cols] or ["*"]
    where_sql, params = build_filters(filters, allowed_columns)
    limit = max(1, min(int(intent.get("limit") or 20), 100))
    sql = f"SELECT {', '.join(selected)} FROM orders"
    if where_sql:
        sql += f" WHERE {where_sql}"
    date_col = primary_date_column(allowed_columns)
    if date_col:
        sql += f" ORDER BY {quote_ident(date_col)} DESC NULLS LAST"
    sql += " LIMIT ?"
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


_AGG_LABELS = {"sum": "Total", "avg": "Average", "count": "Count", "min": "Min", "max": "Max"}


def make_title(
    metric_column: str | None,
    aggregation: str,
    dimensions: list[str],
    date_grain: str | None,
    limit: int,
) -> str:
    agg_label = _AGG_LABELS.get((aggregation or "sum").lower(), "Total")
    if metric_column:
        column_name = metric_column.replace("_", " ").title()
        if agg_label.lower() in column_name.lower().split():
            metric_name = column_name
        else:
            metric_name = f"{agg_label} {column_name}".strip()
    else:
        metric_name = agg_label
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


def build_total_plan(intent: dict[str, Any], allowed_columns: set[str], question: str = "") -> QueryPlan:
    aggregation = infer_aggregation(question, intent.get("aggregation"))
    metric_column = (
        None if aggregation == "count"
        else infer_metric_column(question, intent.get("metric_column"), allowed_columns)
    )
    metric_sql, alias = metric_expression(metric_column, aggregation, allowed_columns)
    where_sql, params = build_filters(intent.get("filters") or [], allowed_columns)
    sql = f"SELECT {metric_sql} FROM orders"
    if where_sql:
        sql += f" WHERE {where_sql}"
    title_metric = (metric_column or "count").replace("_", " ").title()
    agg_label = _AGG_LABELS.get(aggregation, "Total")
    title = f"{agg_label} {title_metric} Grand Total".replace("  ", " ").strip()
    how = f"Aggregate {aggregation}({metric_column or '*'}) across all matching rows (no grouping or limit)."
    return QueryPlan(sql=sql, params=params, display_type="card", title=title, how=how)


def validate_readonly_sql(sql: str) -> None:
    lowered = re.sub(r"\s+", " ", sql).strip().lower()
    if not lowered.startswith("select "):
        raise ValueError("Only SELECT queries are allowed.")
    forbidden = [" insert ", " update ", " delete ", " drop ", " alter ", " create ", " attach ", " copy ", "pragma "]
    if any(token in f" {lowered} " for token in forbidden):
        raise ValueError("Unsafe SQL was rejected.")
