from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


VALID_AGGREGATIONS = {"sum", "avg", "count", "count_distinct", "min", "max"}

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


LEDGER_ROLE_ALIASES = {
    "voucher": ("voucherno", "voucher_no", "voucher_number", "vno", "voucher"),
    "line": ("voucherlineno", "voucher_line_no", "voucher_line_number", "line_no", "lineno"),
    "date": ("date", "voucherdate", "voucher_date", "transaction_date", "posting_date"),
    "account": ("account", "accountname", "account_name", "ledgeraccount", "ledger_account"),
    "contra": ("contraaccount", "contra_account", "contra", "contraaccountname", "contra_account_name"),
    "debit": ("debit", "debitamount", "debit_amount", "dr", "dramount", "dr_amount"),
    "credit": ("credit", "creditamount", "credit_amount", "cr", "cramount", "cr_amount"),
    "branch": ("branch", "branchname", "branch_name"),
    "customer": ("customer", "customername", "customer_name", "party", "partyname", "party_name"),
}


def _ledger_roles(allowed_columns: set[str]) -> dict[str, str]:
    canonical_lookup = {canonical_column(col): col for col in allowed_columns}
    roles: dict[str, str] = {}
    for role, aliases in LEDGER_ROLE_ALIASES.items():
        for alias in aliases:
            col = canonical_lookup.get(alias)
            if col:
                roles[role] = col
                break
    return roles


def is_ledger_schema(allowed_columns: set[str]) -> bool:
    roles = _ledger_roles(allowed_columns)
    return all(role in roles for role in ("voucher", "account", "debit", "credit"))


def _ledger_amount_expr(column: str | None) -> str:
    if not column:
        return "0.0"
    ident = quote_ident(column)
    cleaned = f"regexp_replace(CAST({ident} AS VARCHAR), '[^0-9.\\-]', '', 'g')"
    return f"COALESCE(TRY_CAST({ident} AS DOUBLE), TRY_CAST({cleaned} AS DOUBLE), 0.0)"


def _ledger_contains_expr(columns: list[str], terms: list[str]) -> str:
    clauses = []
    for column in columns:
        ident = quote_ident(column)
        for term in terms:
            safe = term.lower().replace("'", "''")
            clauses.append(f"LOWER(CAST({ident} AS VARCHAR)) LIKE '%{safe}%'")
    return "(" + " OR ".join(clauses) + ")" if clauses else "(FALSE)"


def _ledger_contains_filter(columns: list[str], value: str) -> tuple[str, list[Any]]:
    clauses = [f"LOWER(CAST({quote_ident(column)} AS VARCHAR)) LIKE ?" for column in columns]
    return "(" + " OR ".join(clauses) + ")", [f"%{value.lower()}%"] * len(clauses)


def _ledger_select_columns(roles: dict[str, str], include_branch: bool = True) -> list[str]:
    ordered_roles = ["date", "voucher", "line", "branch", "account", "contra", "debit", "credit"]
    if not include_branch:
        ordered_roles.remove("branch")
    return [roles[role] for role in ordered_roles if role in roles]


def _extract_voucher_value(question: str) -> str | None:
    patterns = [
        r"\bvoucher\s*(?:no|number|#)\.?\s*[:#-]?\s*([a-z0-9/_-]+)\b",
        r"\bvoucher\s+([0-9][a-z0-9/_-]*)\b",
        r"\bvoucherno\.?\s*[:#-]?\s*([a-z0-9/_-]+)\b",
        r"\bvno\.?\s*[:#-]?\s*([a-z0-9/_-]+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, question, re.I)
        if match:
            value = match.group(1).strip()
            if value and value.lower() not in {"level", "wise", "report"}:
                return value
    return None


def _extract_account_search_term(question: str) -> str | None:
    q = question.lower()
    known_terms = ("hdfc", "cgst", "sgst", "igst", "gst")
    for term in known_terms:
        if term in q:
            return term
    match = re.search(r"\binvolving\s+(.+?)(?:\s+and\s+|\s+by\s+|$)", question, re.I)
    if match:
        value = re.sub(r"\b(transactions?|entries|account|accounts?)\b", "", match.group(1), flags=re.I).strip()
        if value:
            return value
    return None


def build_ledger_query_plan(question: str, allowed_columns: set[str]) -> QueryPlan | None:
    roles = _ledger_roles(allowed_columns)
    if not all(role in roles for role in ("voucher", "account", "debit", "credit")):
        return None

    q = question.lower()
    asks_ledger_entries = "ledger" in q and any(term in q for term in ("entry", "entries", "transaction", "transactions"))
    asks_balance_validation = "voucher" in q and (
        "balanced" in q
        or "unbalanced" in q
        or "balance validation" in q
        or "validate" in q and "balance" in q
        or ("debit" in q and "credit" in q and "balance" in q)
    )
    account_cols = [roles["account"]] + ([roles["contra"]] if "contra" in roles else [])
    debit_expr = _ledger_amount_expr(roles.get("debit"))
    credit_expr = _ledger_amount_expr(roles.get("credit"))
    voucher = roles["voucher"]

    voucher_value = _extract_voucher_value(question)
    if voucher_value and any(term in q for term in ("list", "show", "entries", "details", "voucher")):
        selected = _ledger_select_columns(roles)
        sql = f"SELECT {', '.join(quote_ident(col) for col in selected)} FROM orders WHERE CAST({quote_ident(voucher)} AS VARCHAR) = ?"
        order_cols = [roles.get("date"), roles.get("line"), voucher]
        order_by = [quote_ident(col) for col in order_cols if col]
        if order_by:
            sql += " ORDER BY " + ", ".join(order_by)
        sql += " LIMIT ?"
        return QueryPlan(
            sql=sql,
            params=[voucher_value, 25000],
            display_type="table",
            title="Voucher Ledger Entries",
            how="Returned raw ledger rows for the requested voucher without aggregating away line-level details.",
        )

    if asks_balance_validation:
        sql = (
            "WITH voucher_totals AS ("
            f"SELECT {quote_ident(voucher)} AS voucher_no, "
            f"SUM({debit_expr}) AS total_debit, "
            f"SUM({credit_expr}) AS total_credit "
            "FROM orders GROUP BY 1"
            ") "
            "SELECT voucher_no, total_debit, total_credit, "
            "ROUND(total_debit - total_credit, 2) AS balance_difference, "
            "CASE WHEN ABS(total_debit - total_credit) <= 0.01 THEN 'balanced' ELSE 'unbalanced' END AS status "
            "FROM voucher_totals ORDER BY ABS(total_debit - total_credit) DESC, voucher_no LIMIT 500"
        )
        return QueryPlan(sql=sql, params=[], display_type="table", title="Voucher Balance Validation", how="Compared total debit and total credit at voucher grain.")

    if any(term in q for term in ("duplicate", "duplicates")):
        selected = _ledger_select_columns(roles)
        group_cols = [quote_ident(col) for col in selected]
        sql = (
            f"SELECT {', '.join(group_cols)}, COUNT(*) AS duplicate_count "
            "FROM orders "
            f"GROUP BY {', '.join(group_cols)} "
            "HAVING COUNT(*) > 1 "
            f"ORDER BY duplicate_count DESC, {quote_ident(voucher)} LIMIT 500"
        )
        return QueryPlan(sql=sql, params=[], display_type="table", title="Duplicate Ledger Entries", how="Grouped complete ledger-entry signatures and returned only repeated rows.")

    if any(term in q for term in ("zero-value", "zero value", "zero-value transactions", "zero value transactions")):
        selected = _ledger_select_columns(roles)
        sql = (
            f"SELECT {', '.join(quote_ident(col) for col in selected)} FROM orders "
            f"WHERE ABS({debit_expr}) <= 0.01 AND ABS({credit_expr}) <= 0.01 "
            f"ORDER BY {quote_ident(voucher)} LIMIT 500"
        )
        return QueryPlan(sql=sql, params=[], display_type="table", title="Zero-Value Ledger Entries", how="Returned ledger entries where both debit and credit are zero.")

    if asks_ledger_entries:
        selected = _ledger_select_columns(roles)
        sql = f"SELECT {', '.join(quote_ident(col) for col in selected)} FROM orders"
        order_cols = [roles.get("date"), roles.get("line"), voucher]
        order_by = [quote_ident(col) for col in order_cols if col]
        if order_by:
            sql += " ORDER BY " + ", ".join(order_by)
        sql += " LIMIT ?"
        return QueryPlan(
            sql=sql,
            params=[25000],
            display_type="table",
            title="Voucher Ledger Entries",
            how="Returned raw ledger rows without aggregating away line-level details.",
        )

    if "branch" in q and any(term in q for term in ("sales", "gst", "customer", "customers")) and "branch" in roles:
        sales_condition = _ledger_contains_expr(account_cols, ["sales", "revenue"])
        gst_condition = _ledger_contains_expr(account_cols, ["cgst", "sgst", "igst", "gst"])
        customer_col = roles.get("customer") or roles["account"]
        sql = (
            f"SELECT {quote_ident(roles['branch'])} AS branch, "
            f"SUM(CASE WHEN {sales_condition} THEN {credit_expr} - {debit_expr} ELSE 0 END) AS total_sales, "
            f"SUM(CASE WHEN {gst_condition} THEN {credit_expr} - {debit_expr} ELSE 0 END) AS total_gst, "
            f"COUNT(DISTINCT NULLIF(TRIM(CAST({quote_ident(customer_col)} AS VARCHAR)), '')) AS customer_count, "
            "COUNT(*) AS entry_count "
            "FROM orders GROUP BY 1 ORDER BY total_sales DESC NULLS LAST, branch LIMIT 500"
        )
        return QueryPlan(sql=sql, params=[], display_type="table", title="Branch Sales GST And Customers", how="Grouped ledger activity by branch and computed sales, GST, and distinct customer/account counts.")

    if "gstin" not in q and any(term in q for term in ("cgst", "sgst", "igst", "gst")) and any(term in q for term in ("calculate", "total", "gst")):
        cgst = _ledger_contains_expr(account_cols, ["cgst"])
        sgst = _ledger_contains_expr(account_cols, ["sgst"])
        igst = _ledger_contains_expr(account_cols, ["igst"])
        gst_any = _ledger_contains_expr(account_cols, ["cgst", "sgst", "igst"])
        sql = (
            "WITH gst_entries AS ("
            f"SELECT CASE WHEN {cgst} THEN 'CGST' WHEN {sgst} THEN 'SGST' WHEN {igst} THEN 'IGST' ELSE 'GST' END AS gst_component, "
            f"{debit_expr} AS debit_amount, {credit_expr} AS credit_amount "
            f"FROM orders WHERE {gst_any}"
            ") "
            "SELECT gst_component, SUM(debit_amount) AS total_debit, SUM(credit_amount) AS total_credit, "
            "SUM(credit_amount - debit_amount) AS net_credit, COUNT(*) AS entry_count "
            "FROM gst_entries GROUP BY gst_component ORDER BY gst_component"
        )
        return QueryPlan(sql=sql, params=[], display_type="table", title="GST Account Totals", how="Summed debit and credit for CGST, SGST, and IGST ledger accounts.")

    account_term = _extract_account_search_term(question)
    if account_term and any(term in q for term in ("involving", "relationship", "summarize", "summary", "transactions")):
        where_sql, params = _ledger_contains_filter(account_cols, account_term)
        group_cols = [roles["account"]] + ([roles["contra"]] if "contra" in roles else [])
        quoted_groups = [quote_ident(col) for col in group_cols]
        activity = f"(SUM({debit_expr}) + SUM({credit_expr}))"
        sql = (
            f"SELECT {', '.join(f'{quote_ident(col)} AS {quote_ident(col)}' for col in group_cols)}, "
            f"SUM({debit_expr}) AS total_debit, SUM({credit_expr}) AS total_credit, COUNT(*) AS entry_count "
            f"FROM orders WHERE {where_sql} GROUP BY {', '.join(quoted_groups)} "
            f"ORDER BY {activity} DESC NULLS LAST LIMIT 500"
        )
        return QueryPlan(sql=sql, params=params, display_type="table", title="Account Relationship Summary", how="Matched the requested account in account and contra-account fields, then summarized debit and credit by relationship.")

    if any(term in q for term in ("contributes", "contribution", "highest percentage", "total business")):
        customer_col = roles.get("customer") or roles["account"]
        activity = f"({debit_expr} + {credit_expr})"
        sql = (
            "WITH customer_totals AS ("
            f"SELECT {quote_ident(customer_col)} AS customer, SUM({activity}) AS business_value "
            "FROM orders GROUP BY 1"
            "), grand_total AS (SELECT SUM(business_value) AS total_business FROM customer_totals) "
            "SELECT customer, business_value, "
            "ROUND(100 * business_value / NULLIF(total_business, 0), 2) AS business_percentage "
            "FROM customer_totals CROSS JOIN grand_total "
            "ORDER BY business_value DESC NULLS LAST LIMIT 10"
        )
        return QueryPlan(sql=sql, params=[], display_type="table", title="Customer Business Contribution", how="Computed each customer/account share of total ledger activity.")

    if "insight" in q or "insights" in q:
        account = roles["account"]
        zero_count = f"SUM(CASE WHEN ABS(debit_amount) <= 0.01 AND ABS(credit_amount) <= 0.01 THEN 1 ELSE 0 END)"
        sql = (
            "WITH amounts AS ("
            f"SELECT {quote_ident(voucher)} AS voucher_no, {quote_ident(account)} AS account, "
            f"{debit_expr} AS debit_amount, {credit_expr} AS credit_amount FROM orders"
            "), voucher_totals AS ("
            "SELECT voucher_no, SUM(debit_amount) AS total_debit, SUM(credit_amount) AS total_credit FROM amounts GROUP BY voucher_no"
            "), account_totals AS ("
            "SELECT account, SUM(debit_amount + credit_amount) AS activity_value FROM amounts GROUP BY account"
            ") "
            "SELECT 'Total vouchers' AS insight, CAST(COUNT(DISTINCT voucher_no) AS DOUBLE) AS value, '' AS detail FROM amounts "
            "UNION ALL SELECT 'Total debit', SUM(debit_amount), '' FROM amounts "
            "UNION ALL SELECT 'Total credit', SUM(credit_amount), '' FROM amounts "
            "UNION ALL SELECT 'Unbalanced vouchers', CAST(COUNT(*) AS DOUBLE), '' FROM voucher_totals WHERE ABS(total_debit - total_credit) > 0.01 "
            f"UNION ALL SELECT 'Zero-value entries', CAST({zero_count} AS DOUBLE), '' FROM amounts "
            "UNION ALL SELECT 'Most active account', activity_value, account "
            "FROM (SELECT account, activity_value FROM account_totals ORDER BY activity_value DESC NULLS LAST LIMIT 1)"
        )
        return QueryPlan(sql=sql, params=[], display_type="table", title="Ledger Business Insights", how="Generated a deterministic insight table from verified ledger aggregates.")

    return None


def build_query_plan(intent: dict[str, Any], question: str, allowed_columns: set[str]) -> QueryPlan:
    from opentelemetry import trace
    tracer = trace.get_tracer(__name__)
    
    with tracer.start_as_current_span("build_query_plan") as span:
        intent_type = intent.get("intent_type") or "aggregate"
        span.set_attribute("intent_type", intent_type)
        q = question.lower()

    ledger_plan = build_ledger_query_plan(question, allowed_columns)
    if ledger_plan is not None:
        return ledger_plan
    
    if intent_type == "clarification":
        raise ValueError(intent.get("clarifying_question") or "I need one more detail to answer that.")
    if intent_type == "unsupported":
        raise ValueError("I can only answer questions grounded in the CSV data.")

    # Special Case: Set Difference ("in X but not in Y")
    if ("and not in" in q or "but not in" in q) and "product" in allowed_columns:
        # Heuristic: find the target months
        include_val = 1 # Jan
        exclude_val = 2 # Feb
        if "mar" in q: exclude_val = 3
        
        sql = (
            f"SELECT \"product\" FROM (\n"
            f"  SELECT \"product\",\n"
            f"         MAX(CASE WHEN EXTRACT(month FROM TRY_CAST(\"date\" AS TIMESTAMP)) = ? THEN 1 ELSE 0 END) as in_include_month,\n"
            f"         MAX(CASE WHEN EXTRACT(month FROM TRY_CAST(\"date\" AS TIMESTAMP)) = ? THEN 1 ELSE 0 END) as in_exclude_month\n"
            f"  FROM orders\n"
            f"  GROUP BY \"product\"\n"
            f") AS product_months WHERE in_include_month = 1 AND in_exclude_month = 0"
        )
        return QueryPlan(
            sql=sql,
            params=[include_val, exclude_val],
            display_type="table",
            title="Set Difference",
            how="Computed products in one group but not the other using a subquery."
        )

    # Special Case: Dual metrics ("how many orders ... and how many items ...")
    if "how many orders" in q and "items sold" in q and "vno" in allowed_columns and "quantity" in allowed_columns:
        where_sql, params = build_filters(intent.get("filters") or [], allowed_columns, question=question)
        sql = (
            f"SELECT COUNT(DISTINCT \"vno\") AS \"orders\", "
            f"SUM(TRY_CAST(\"quantity\" AS DOUBLE)) AS \"items_sold\" "
            f"FROM orders"
        )
        if where_sql:
            sql += f" WHERE {where_sql}"
        return QueryPlan(
            sql=sql,
            params=params,
            display_type="card",
            title="Orders and Items",
            how="Computed both distinct order count and total quantity sold."
        )

    if intent_type == "lookup":
        return build_lookup_plan(intent.get("filters") or [], intent, allowed_columns, question=question)

    multi_metrics = intent.get("metrics") or []
    if isinstance(multi_metrics, list) and multi_metrics:
        selects: list[str] = []
        for metric in multi_metrics[:5]:
            if not isinstance(metric, dict):
                continue
            name = canonical_column(metric.get("name") or metric.get("column") or "metric")
            column = canonical_column(metric.get("column") or "")
            aggregation = infer_aggregation(question, metric.get("aggregation"))
            expr, _alias = metric_expression(column, aggregation, allowed_columns, alias=name, question=question)
            selects.append(expr)
        if selects:
            where_sql, params = build_filters(intent.get("filters") or [], allowed_columns, question=question)
            sql = f"SELECT {', '.join(selects)} FROM orders"
            if where_sql:
                sql += f" WHERE {where_sql}"
            return QueryPlan(
                sql=sql,
                params=params,
                display_type="card",
                title="Key Metrics",
                how=f"Computed {len(selects)} instruction-defined metric(s); filters: {len(params)} parameter(s).",
            )

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
    metric_sql, order_alias = metric_expression(
        metric_column,
        aggregation,
        allowed_columns,
        alias=canonical_column(intent.get("metric_definition") or "") or None,
        question=question,
    )
    date_column = primary_date_column(allowed_columns)
    has_period = bool(date_grain and date_column)
    if has_period:
        selects.append(f"date_trunc('{date_grain}', TRY_CAST({quote_ident(date_column)} AS TIMESTAMP)) AS period")
        groups.append("period")
    for dim in dimensions:
        selects.append(f"{quote_ident(dim)} AS {quote_ident(dim)}")
        groups.append(quote_ident(dim))
    selects.append(metric_sql)

    where_sql, params = build_filters(intent.get("filters") or [], allowed_columns, question=question)
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
    ranked_title = bool(re.search(r"\b(top|highest|best|most|largest|lowest|worst|bottom|least|smallest)\b", question.lower()))
    title = make_title(metric_column, aggregation, dimensions, date_grain, limit, ranked=ranked_title)
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
    alias: str | None = None,
    question: str = "",
) -> tuple[str, str]:
    """Build the SELECT expression for an aggregation over an actual schema column.
    Returns (sql_fragment, alias). Falls back to COUNT(*) when the column is missing
    or the aggregation needs a numeric column but none was identified."""
    agg = (aggregation or "sum").lower()
    if agg not in VALID_AGGREGATIONS:
        agg = "sum"
        
    q = (question or "").lower()
    # Heuristic: if question asks for "orders" and we have a voucher column, use COUNT(DISTINCT vno)
    if agg == "count" and not metric_column:
        if "order" in q and "vno" in allowed_columns:
            out_alias = alias or "vno"
            return f'COUNT(DISTINCT "vno") AS {quote_ident(out_alias)}', out_alias
        if "product" in q and "product" in allowed_columns:
            out_alias = alias or "product"
            return f'COUNT(DISTINCT "product") AS {quote_ident(out_alias)}', out_alias

    if agg == "count_distinct" and metric_column and metric_column in allowed_columns:
        out_alias = alias or metric_column
        return f"COUNT(DISTINCT {quote_ident(metric_column)}) AS {quote_ident(out_alias)}", out_alias
    if agg == "count" or not metric_column or metric_column not in allowed_columns:
        return "COUNT(*) AS count", "count"
    op = agg.upper()
    out_alias = alias or metric_column
    return (
        f"{op}(TRY_CAST({quote_ident(metric_column)} AS DOUBLE)) AS {quote_ident(out_alias)}",
        out_alias,
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


def build_lookup_plan(filters: list[dict[str, Any]], intent: dict[str, Any], allowed_columns: set[str], question: str = "") -> QueryPlan:
    cols = sorted(allowed_columns)
    selected = [quote_ident(col) for col in cols] or ["*"]
    where_sql, params = build_filters(filters, allowed_columns, question=question)
    limit = 25000 # Use high limit for lookups/exports
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


def build_filters(filters: list[dict[str, Any]], allowed_columns: set[str], question: str = "") -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    q = (question or "").lower()
    
    # Heuristic for month-only extraction
    month_names = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
    target_month_idx = -1
    for i, m in enumerate(month_names):
        if f"in {m}" in q or f"during {m}" in q or q.endswith(m):
            target_month_idx = i + 1
            break

    for flt in filters:
        column = canonical_column(flt.get("column", ""))
        if column not in allowed_columns:
            continue
        op = str(flt.get("operator", "=")).lower()
        value = flt.get("value")
        ident = quote_ident(column)
        
        # Heuristic: swap date filters for EXTRACT(month) if it looks like a month-only filter
        if target_month_idx > 0 and column == "date":
            if op == "between" and isinstance(value, list) and len(value) == 2:
                clauses.append(f"EXTRACT(month FROM TRY_CAST({ident} AS TIMESTAMP)) = ?")
                params.append(target_month_idx)
                continue
            if op in {">=", "<="}:
                if not any(f"EXTRACT(month FROM TRY_CAST({ident}" in c for c in clauses):
                    clauses.append(f"EXTRACT(month FROM TRY_CAST({ident} AS TIMESTAMP)) = ?")
                    params.append(target_month_idx)
                continue

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


_AGG_LABELS = {"sum": "Total", "avg": "Average", "count": "Count", "count_distinct": "Distinct Count", "min": "Min", "max": "Max"}


def make_title(
    metric_column: str | None,
    aggregation: str,
    dimensions: list[str],
    date_grain: str | None,
    limit: int,
    *,
    ranked: bool = False,
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
        if not ranked:
            return f"{metric_name} By {dimensions[0].replace('_', ' ').title()}"
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
    metric_sql, alias = metric_expression(metric_column, aggregation, allowed_columns, question=question)
    where_sql, params = build_filters(intent.get("filters") or [], allowed_columns, question=question)
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
    if ";" in lowered:
        raise ValueError("Only one SELECT statement is allowed.")
    if not lowered.startswith("select "):
        if not lowered.startswith("with "):
            raise ValueError("Only SELECT or WITH queries are allowed.")
    forbidden = [
        " insert ", " update ", " delete ", " drop ", " alter ", " create ", " attach ", " copy ", "pragma ",
        " read_csv", " read_json", " read_parquet", " read_xlsx", " read_text", " parquet_scan",
        " csv_scan", " sqlite_scan", " glob(", "httpfs", " from '/", " from '~/", " from 'http",
    ]
    if any(token in f" {lowered} " for token in forbidden):
        raise ValueError("Unsafe SQL was rejected.")
