from __future__ import annotations

import unittest
import math
import types
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import duckdb
import pandas as pd

from src.data_sources import prepare_api_source, prepare_csv_memory_source, prepare_csv_source, prepare_pdf_source
from src.prompting import build_intent_prompt, xml_escape
from src.project_intelligence import (
    apply_instruction_rules,
    build_instruction_context,
    default_source_instructions,
)
from src.query_engine import build_ledger_query_plan, build_query_plan, heuristic_intent, is_underspecified, validate_readonly_sql
from src.visualization import choose_visualization

class RoutingTests(unittest.TestCase):
    def test_pivot_timetable_question_is_not_underspecified(self) -> None:
        intent = {"intent_type": "aggregate", "aggregation": "sum"}
        question = "infer from the table and produce time table for each individual subject teacher"
        self.assertFalse(is_underspecified(intent, question, {"class", "teacher", "subject", "period_1", "period_2"}))


class CsvSourceTests(unittest.TestCase):
    def test_prepare_csv_source_accepts_cp1252_nbsp(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "orders.csv"
            csv_path.write_bytes(
                b"Order ID,Product Name,Sales\n"
                b"CA-2014-115812,Chromcraft\xa0Rectangular Conference Tables,1706.184\n"
            )

            source = prepare_csv_source(csv_path, root / "cache", logger=None, force=True)

        self.assertEqual(source.schema["row_count"], 1)
        self.assertIn("product_name", source.allowed_columns)

    def test_prepare_csv_memory_source_accepts_cp1252_nbsp(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "orders.csv"
            csv_path.write_bytes(
                b"Order ID,Product Name,Sales\n"
                b"CA-2014-115812,Chromcraft\xa0Rectangular Conference Tables,1706.184\n"
            )

            source = prepare_csv_memory_source(csv_path, logger=None)

        self.assertEqual(source.schema["row_count"], 1)
        self.assertIn("product_name", source.allowed_columns)

ALLOWED = {
    "order_key",
    "order_datetime",
    "cust_name",
    "prod_name",
    "prod_category",
    "total_order_val",
    "qty",
    "payment_mode",
}


LEDGER_ROWS = [
    {
        "voucherlineno": 1,
        "voucherno": 75,
        "date": "2026-04-01",
        "branch": "Hyderabad",
        "customer": "Raghu Agri Care",
        "account": "HDFC Bank",
        "contraaccount": "Raghu Agri Care",
        "debit": "1,000.00",
        "credit": "0",
    },
    {
        "voucherlineno": 2,
        "voucherno": 75,
        "date": "2026-04-01",
        "branch": "Hyderabad",
        "customer": "Raghu Agri Care",
        "account": "Sales",
        "contraaccount": "HDFC Bank",
        "debit": "0",
        "credit": "1,000.00",
    },
    {
        "voucherlineno": 3,
        "voucherno": 75,
        "date": "2026-04-01",
        "branch": "Hyderabad",
        "customer": "Raghu Agri Care",
        "account": "CGST Output",
        "contraaccount": "HDFC Bank",
        "debit": "0",
        "credit": "₹90.00",
    },
    {
        "voucherlineno": 4,
        "voucherno": 75,
        "date": "2026-04-01",
        "branch": "Hyderabad",
        "customer": "Raghu Agri Care",
        "account": "SGST Output",
        "contraaccount": "HDFC Bank",
        "debit": "0",
        "credit": "90.00",
    },
    {
        "voucherlineno": 1,
        "voucherno": 76,
        "date": "2026-04-02",
        "branch": "Bengaluru",
        "customer": "Sai Seeds",
        "account": "Round Off",
        "contraaccount": "Sales",
        "debit": "0",
        "credit": "0",
    },
    {
        "voucherlineno": 1,
        "voucherno": 77,
        "date": "2026-04-03",
        "branch": "Bengaluru",
        "customer": "Sai Seeds",
        "account": "IGST Output",
        "contraaccount": "Sales",
        "debit": "0",
        "credit": "180.00",
    },
    {
        "voucherlineno": 1,
        "voucherno": 88,
        "date": "2026-04-04",
        "branch": "Hyderabad",
        "customer": "Duplicate Customer",
        "account": "Sales",
        "contraaccount": "Cash",
        "debit": "0",
        "credit": "50",
    },
    {
        "voucherlineno": 1,
        "voucherno": 88,
        "date": "2026-04-04",
        "branch": "Hyderabad",
        "customer": "Duplicate Customer",
        "account": "Sales",
        "contraaccount": "Cash",
        "debit": "0",
        "credit": "50",
    },
]


def run_ledger_prompt(question: str) -> tuple[object, pd.DataFrame]:
    df = pd.DataFrame(LEDGER_ROWS)
    plan = build_query_plan(
        {"intent_type": "clarification", "clarifying_question": "Which field?"},
        question,
        set(df.columns),
    )
    validate_readonly_sql(plan.sql)
    con = duckdb.connect(":memory:")
    try:
        con.register("orders", df)
        result = con.execute(plan.sql, plan.params).fetchdf()
    finally:
        con.close()
    return plan, result


class _PdfPage:
    def __init__(self, tables: list[list[list[str]]]) -> None:
        self._tables = tables

    def extract_tables(self) -> list[list[list[str]]]:
        return self._tables


class _PdfDoc:
    def __init__(self, pages: list[_PdfPage]) -> None:
        self.pages = pages

    def __enter__(self) -> "_PdfDoc":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _MuPdfTable:
    def __init__(self, rows: list[list[str]]) -> None:
        self._rows = rows

    def extract(self) -> list[list[str]]:
        return self._rows


class _MuPdfTables:
    def __init__(self, tables: list[_MuPdfTable]) -> None:
        self.tables = tables

    def __len__(self) -> int:
        return len(self.tables)


class _MuPdfPage:
    def __init__(self, tables: list[list[list[str]]]) -> None:
        self._tables = [_MuPdfTable(table) for table in tables]

    def find_tables(self, **kwargs: object) -> _MuPdfTables:
        return _MuPdfTables(self._tables)

    def get_text(self, kind: str) -> object:
        return "" if kind == "text" else []


class _MuPdfDoc:
    def __init__(self, pages: list[_MuPdfPage]) -> None:
        self._pages = pages
        self.page_count = len(pages)

    def __getitem__(self, index: int) -> _MuPdfPage:
        return self._pages[index]

    def close(self) -> None:
        return None


class _TextBlockPage:
    def __init__(self, text: str, blocks: list[str]) -> None:
        self._text = text
        self._blocks = blocks

    def get_text(self, kind: str) -> object:
        if kind == "text":
            return self._text
        return [(0, 0, 1, 1, block) for block in self._blocks]

    def find_tables(self, **kwargs: object) -> _MuPdfTables:
        return _MuPdfTables([])


class PromptTests(unittest.TestCase):
    def test_xml_escape_dynamic_content(self) -> None:
        self.assertEqual(xml_escape('<hello attr="x">&'), "&lt;hello attr=&quot;x&quot;&gt;&amp;")

    def test_prompt_contains_escaped_question(self) -> None:
        prompt = build_intent_prompt(
            schema_context={"columns": [{"name": "prod_category"}]},
            conversation_summary="",
            user_question='top <3 "products"',
            char_budget=24000,
        )
        self.assertIn("&lt;3", prompt)
        self.assertIn("&quot;products&quot;", prompt)

    def test_intent_prompt_preserves_question_when_mcp_summary_is_large(self) -> None:
        question = "Which customer has the highest order value?"
        prompt = build_intent_prompt(
            schema_context={"columns": [{"name": "cust_name"}, {"name": "total_order_val"}]},
            conversation_summary="",
            user_question=question,
            char_budget=1800,
            mcp_summary="\n".join(f"  - warehouse_tool_{i}: tool metadata" for i in range(400)),
            local_source_name="Orders.csv",
        )

        self.assertLessEqual(len(prompt), 1800)
        self.assertIn("<truncation_notice>", prompt)
        self.assertIn(f"<user_question>{xml_escape(question)}</user_question>", prompt)
        self.assertIn("<output_contract>", prompt)


class QueryPlanTests(unittest.TestCase):
    def test_top_three_prefers_table(self) -> None:
        intent = heuristic_intent("give me top 3 categories by revenue", ALLOWED)
        plan = build_query_plan(intent, "give me top 3 categories by revenue", ALLOWED)
        self.assertIn("LIMIT 3", plan.sql)
        df = pd.DataFrame({"prod_category": ["A", "B", "C"], "revenue": [3, 2, 1]})
        self.assertEqual(choose_visualization("give me top 3 categories by revenue", intent, df), "table")

    def test_wide_single_row_prefers_table(self) -> None:
        intent = {"intent_type": "aggregate", "requested_visualization": "bar"}
        df = pd.DataFrame([{
            "voucherlineno": 1,
            "voucherseries": "PR",
            "voucherno": 10,
            "date": "2026-06-29",
            "branch": "Hyderabad",
            "account": "Cash",
        }])

        self.assertEqual(choose_visualization("select rows from VoucherSeries = PR", intent, df), "table")

    def test_trend_prefers_line(self) -> None:
        intent = heuristic_intent("monthly revenue trend", ALLOWED)
        plan = build_query_plan(intent, "monthly revenue trend", ALLOWED)
        self.assertIn("date_trunc('month'", plan.sql)
        df = pd.DataFrame({"period": pd.to_datetime(["2024-01-01", "2024-02-01"]), "revenue": [1, 2]})
        self.assertEqual(choose_visualization("monthly revenue trend", intent, df), "line")

    def test_monthly_trend_executes_with_text_dates_and_currency_amounts(self) -> None:
        plan = build_query_plan(
            {
                "intent_type": "trend",
                "aggregation": "sum",
                "metric_column": "net",
                "dimensions": [],
                "date_grain": "month",
                "filters": [],
                "limit": 100,
            },
            "month wise sales?",
            {"date", "vno", "product", "net"},
        )

        validate_readonly_sql(plan.sql)
        df = pd.DataFrame(
            [
                {"date": "15/01/2026", "vno": 1, "product": "Seeds", "net": "1,000.50"},
                {"date": "20/01/2026", "vno": 2, "product": "Tools", "net": "₹90.00"},
                {"date": "05/02/2026", "vno": 3, "product": "Seeds", "net": "25"},
            ]
        )
        con = duckdb.connect(":memory:")
        try:
            con.register("orders", df)
            result = con.execute(plan.sql, plan.params).fetchdf()
        finally:
            con.close()

        self.assertTrue(result["period"].notna().all())
        self.assertEqual(result["period"].dt.strftime("%Y-%m").tolist(), ["2026-01", "2026-02"])
        self.assertEqual(result["net"].tolist(), [1090.5, 25.0])

    def test_multi_metric_prompt_builds_all_requested_columns(self) -> None:
        allowed = {"order_id", "sales", "profit", "quantity"}
        plan = build_query_plan(
            {
                "intent_type": "aggregate",
                "aggregation": "sum",
                "metric_column": "sales",
                "filters": [],
                "limit": 100,
            },
            "What are total sales, total profit, and total quantity?",
            allowed,
        )

        validate_readonly_sql(plan.sql)
        self.assertIn('AS "total_sales"', plan.sql)
        self.assertIn('AS "total_profit"', plan.sql)
        self.assertIn('AS "total_quantity"', plan.sql)

        df = pd.DataFrame([
            {"order_id": "O-1", "sales": "1,200.50", "profit": "300", "quantity": "3"},
            {"order_id": "O-2", "sales": "800", "profit": "-20", "quantity": "2"},
        ])
        con = duckdb.connect(":memory:")
        try:
            con.register("orders", df)
            result = con.execute(plan.sql, plan.params).fetchdf().iloc[0].to_dict()
        finally:
            con.close()

        self.assertEqual(result["total_sales"], 2000.5)
        self.assertEqual(result["total_profit"], 280.0)
        self.assertEqual(result["total_quantity"], 5.0)

    def test_revenue_and_items_terms_map_to_sales_and_quantity(self) -> None:
        allowed = {"order_id", "sales", "quantity"}
        plan = build_query_plan(
            {"intent_type": "aggregate", "aggregation": "sum", "metric_column": "revenue", "filters": []},
            "Show total revenue and items sold.",
            allowed,
        )

        self.assertIn('SUM(COALESCE(TRY_CAST("sales" AS DOUBLE)', plan.sql)
        self.assertIn('AS "total_sales"', plan.sql)
        self.assertIn('SUM(COALESCE(TRY_CAST("quantity" AS DOUBLE)', plan.sql)
        self.assertIn('AS "total_quantity"', plan.sql)

    def test_loss_making_orders_filter_profit_negative(self) -> None:
        allowed = {"order_id", "order_date", "customer", "sales", "profit", "quantity"}
        plan = build_query_plan(
            {"intent_type": "aggregate", "aggregation": "count", "filters": []},
            "Which orders are loss-making?",
            allowed,
        )

        validate_readonly_sql(plan.sql)
        self.assertIn('"profit"', plan.sql)
        self.assertIn("< 0", plan.sql)

        df = pd.DataFrame([
            {"order_id": "O-1", "order_date": "2026-01-01", "customer": "A", "sales": 100, "profit": 10, "quantity": 1},
            {"order_id": "O-2", "order_date": "2026-01-02", "customer": "B", "sales": 50, "profit": -5, "quantity": 2},
        ])
        con = duckdb.connect(":memory:")
        try:
            con.register("orders", df)
            result = con.execute(plan.sql, plan.params).fetchdf()
        finally:
            con.close()

        self.assertEqual(result["order_id"].tolist(), ["O-2"])
        self.assertEqual(result["profit"].tolist(), [-5])

    def test_data_quality_audit_checks_values_and_duplicate_rows(self) -> None:
        allowed = {"order_id", "order_date", "branch", "sales", "profit"}
        plan = build_query_plan(
            {"intent_type": "multi_step", "requested_visualization": "table"},
            "Are there data quality gaps? Check missing, empty strings, placeholders, invalid dates, numeric anomalies, and duplicates.",
            allowed,
        )

        validate_readonly_sql(plan.sql)
        df = pd.DataFrame([
            {"order_id": "O-1", "order_date": "2026-01-01", "branch": "<Branch>", "sales": "100", "profit": "10"},
            {"order_id": "O-2", "order_date": "not-a-date", "branch": "", "sales": "abc", "profit": "-5"},
            {"order_id": "O-2", "order_date": "not-a-date", "branch": "", "sales": "abc", "profit": "-5"},
        ])
        con = duckdb.connect(":memory:")
        try:
            con.register("orders", df)
            result = con.execute(plan.sql, plan.params).fetchdf()
        finally:
            con.close()

        by_column = {row["column_name"]: row for row in result.to_dict(orient="records")}
        self.assertEqual(by_column["branch"]["empty_string_count"], 2)
        self.assertEqual(by_column["branch"]["placeholder_count"], 1)
        self.assertEqual(by_column["order_date"]["invalid_date_count"], 2)
        self.assertEqual(by_column["sales"]["numeric_anomaly_count"], 2)
        self.assertEqual(by_column["__row__"]["exact_duplicate_rows"], 1)

    def test_table_by_location_groups_by_city(self) -> None:
        allowed = ALLOWED | {"ship_city"}
        intent = heuristic_intent("give me a table by location", allowed)
        self.assertEqual(intent["dimensions"], ["ship_city"])
        df = pd.DataFrame({"ship_city": ["Miami", "Delhi"], "revenue": [10, 5]})
        self.assertEqual(choose_visualization("give me a table by location", intent, df), "table")

    def test_generic_excel_location_revenue_columns(self) -> None:
        allowed = {"location", "revenue"}
        intent = heuristic_intent("give me a table by location", allowed)
        plan = build_query_plan(intent, "give me a table by location", allowed)
        self.assertIn('SUM(COALESCE(TRY_CAST("revenue" AS DOUBLE)', plan.sql)
        self.assertEqual(plan.sql.count('"location" AS "location"'), 1)

    def test_pizza_instructions_distinguish_items_sold_and_orders(self) -> None:
        allowed = {
            "order_details_id",
            "order_id",
            "pizza_id",
            "quantity",
            "order_date",
            "total_price",
            "pizza_category",
        }
        instructions = default_source_instructions(
            {"columns": [{"name": col} for col in sorted(allowed)], "row_count": 48620},
            "pizza_sales.csv",
        )
        intent = apply_instruction_rules(
            heuristic_intent("how many items sold vs how many orders", allowed),
            "how many items sold vs how many orders",
            allowed,
            source_instructions=instructions,
        )

        plan = build_query_plan(intent, "how many items sold vs how many orders", allowed)

        self.assertIn('SUM(COALESCE(TRY_CAST("quantity" AS DOUBLE)', plan.sql)
        self.assertIn('AS "items_sold"', plan.sql)
        self.assertIn('COUNT(DISTINCT "order_id") AS "orders"', plan.sql)

    def test_pizza_instructions_count_rows_line_items_and_distinct_orders(self) -> None:
        allowed = {"order_details_id", "order_id", "quantity", "total_price"}
        instructions = default_source_instructions(
            {"columns": [{"name": col} for col in sorted(allowed)], "row_count": 48620},
            "pizza_sales.csv",
        )

        rows_intent = apply_instruction_rules(
            heuristic_intent("how many rows are there", allowed),
            "how many rows are there",
            allowed,
            source_instructions=instructions,
        )
        rows_plan = build_query_plan(rows_intent, "how many rows are there", allowed)
        self.assertIn("COUNT(*) AS count", rows_plan.sql)

        orders_intent = apply_instruction_rules(
            heuristic_intent("how many orders", allowed),
            "how many orders",
            allowed,
            source_instructions=instructions,
        )
        orders_plan = build_query_plan(orders_intent, "how many orders", allowed)
        self.assertIn('COUNT(DISTINCT "order_id") AS "orders"', orders_plan.sql)

    def test_instruction_context_is_compact_and_schema_safe(self) -> None:
        allowed = {"order_id", "quantity"}
        instructions = {
            "row_grain": "line_item",
            "entities": {"order": "order_id", "bad": "missing_column"},
            "metrics": {
                "items_sold": {"column": "quantity", "aggregation": "sum", "synonyms": ["items sold"]},
                "bad_metric": {"column": "missing_column", "aggregation": "sum"},
            },
            "relationships": [
                {
                    "from_model": "order_lines",
                    "from_column": "order_id",
                    "to_model": "orders",
                    "to_column": "id",
                    "cardinality": "many_to_one",
                    "approved": True,
                }
            ],
            "routing": {"good_for": ["restaurant sales"], "not_for": ["payroll"]},
            "notes": "Use order_id as the order number.",
        }

        context = build_instruction_context(
            source_instructions=instructions,
            project_instructions={"category": "sales", "notes": "Restaurant reporting."},
            memory_snippets=[{"title": "Order meaning", "content": "Orders are unique order_id values."}],
            allowed_columns=allowed,
            char_budget=1000,
        )

        self.assertIn("line_item", context)
        self.assertIn("order_id", context)
        self.assertIn("items_sold", context)
        self.assertIn("sum(quantity)", context)
        self.assertIn("order_lines.order_id -> orders.id", context)
        self.assertIn("restaurant sales", context)
        self.assertIn("payroll", context)
        self.assertNotIn("missing_column", context)

    def test_real_pizza_csv_instruction_metrics_execute(self) -> None:
        csv_path = Path("/Users/rajasekharbandreddy/Downloads/pizza_sales.csv")
        if not csv_path.exists():
            self.skipTest("local pizza_sales.csv fixture is not available")
        import duckdb

        df = pd.read_csv(csv_path)
        allowed = set(df.columns)
        instructions = default_source_instructions(
            {"columns": [{"name": col} for col in sorted(allowed)], "row_count": len(df)},
            "pizza_sales.csv",
        )
        intent = apply_instruction_rules(
            heuristic_intent("how many items sold vs how many orders", allowed),
            "how many items sold vs how many orders",
            allowed,
            source_instructions=instructions,
        )
        plan = build_query_plan(intent, "how many items sold vs how many orders", allowed)
        con = duckdb.connect(":memory:")
        try:
            con.register("orders", df)
            result = con.execute(plan.sql, plan.params).fetchone()
        finally:
            con.close()

        self.assertEqual(result, (49574.0, 21350))

    def test_ledger_report_prompts_compile_and_execute(self) -> None:
        cases = [
            ("List all ledger entries for Voucher No 75 including debit, credit, account, contra account, and date.", "Voucher Ledger Entries"),
            ("Show voucher ledger entries with account, contra account, debit and credit.", "Voucher Ledger Entries"),
            ("Find all transactions involving HDFC Bank and summarize debit and credit values by account.", "Account Relationship Summary"),
            ("Calculate total GST using CGST, SGST and IGST accounts.", "GST Account Totals"),
            ("Are debits and credits balanced at voucher level?", "Voucher Balance Validation"),
            ("Run voucher balance validation.", "Voucher Balance Validation"),
            ("Identify duplicate vouchers or ledger entries.", "Duplicate Ledger Entries"),
            ("Which customer contributes the highest percentage of total business?", "Customer Business Contribution"),
            ("Provide branch-wise sales, GST and customer count.", "Branch Sales GST And Customers"),
            ("Identify zero-value transactions.", "Zero-Value Ledger Entries"),
            ("Generate 5 business insights supported by numbers.", "Ledger Business Insights"),
        ]

        for question, title in cases:
            with self.subTest(question=question):
                plan, result = run_ledger_prompt(question)
                self.assertEqual(plan.title, title)
                self.assertFalse(result.empty)

    def test_ledger_prompt_outputs_match_expected_finance_shapes(self) -> None:
        voucher_plan, voucher_rows = run_ledger_prompt("List all ledger entries for Voucher No 75 including debit, credit, account, contra account, and date.")
        self.assertNotIn("GROUP BY", voucher_plan.sql)
        self.assertEqual(voucher_rows["voucherno"].tolist(), [75, 75, 75, 75])

        hdfc_plan, hdfc_rows = run_ledger_prompt("Find all transactions involving HDFC Bank and summarize debit and credit values by account.")
        self.assertEqual(hdfc_plan.params, ["%hdfc%", "%hdfc%"])
        self.assertEqual(hdfc_rows["total_credit"].sum(), 1180.0)
        self.assertEqual(hdfc_rows["total_debit"].sum(), 1000.0)

        gst_plan, gst_rows = run_ledger_prompt("Calculate total GST using CGST, SGST and IGST accounts.")
        self.assertNotIn("COUNT(*) AS count", gst_plan.sql)
        self.assertEqual(dict(zip(gst_rows["gst_component"], gst_rows["total_credit"])), {"CGST": 90.0, "IGST": 180.0, "SGST": 90.0})

        duplicate_plan, duplicate_rows = run_ledger_prompt("Identify duplicate vouchers or ledger entries.")
        self.assertIn("HAVING COUNT(*) > 1", duplicate_plan.sql)
        self.assertEqual(duplicate_rows["voucherno"].tolist(), [88])
        self.assertEqual(duplicate_rows["duplicate_count"].tolist(), [2])

        branch_plan, branch_rows = run_ledger_prompt("Provide branch-wise sales, GST and customer count.")
        self.assertIn("total_sales", branch_rows.columns)
        hyderabad = branch_rows[branch_rows["branch"] == "Hyderabad"].iloc[0]
        self.assertEqual(hyderabad["total_sales"], 1100.0)
        self.assertEqual(hyderabad["total_gst"], 180.0)
        self.assertEqual(hyderabad["customer_count"], 2)

        insights_plan, insights_rows = run_ledger_prompt("Generate 5 business insights supported by numbers.")
        self.assertEqual(insights_plan.title, "Ledger Business Insights")
        self.assertIn("Total vouchers", insights_rows["insight"].tolist())
        self.assertTrue(insights_rows["value"].notna().all())

    def test_ledger_contact_info_prompt_does_not_trigger_finance_plan(self) -> None:
        plan = build_ledger_query_plan(
            "Provide GSTIN, PAN, email, mobile and contact person for Raghu Agri Care.",
            set(pd.DataFrame(LEDGER_ROWS).columns),
        )

        self.assertIsNone(plan)

    def test_api_source_coerces_comma_and_currency_numeric_columns(self) -> None:
        class Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> list[dict[str, object]]:
                return [
                    {"VoucherNo": 1, "Debit": "1,200.50", "Credit": "₹90.00", "Account": "CGST Output"},
                    {"VoucherNo": 2, "Debit": "0", "Credit": "180.00", "Account": "Sales"},
                ]

        with patch("requests.get", return_value=Response()):
            source = prepare_api_source("https://example.test/table/Ledger_Table", logger=None)

        self.assertIsNotNone(source.dataframe)
        self.assertTrue(math.isclose(float(source.dataframe["debit"].iloc[0]), 1200.5))
        self.assertTrue(math.isclose(float(source.dataframe["credit"].iloc[0]), 90.0))

    def test_api_source_redacts_url_in_display_name_and_logs(self) -> None:
        class Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> list[dict[str, object]]:
                return [{"Order ID": 1, "Sales": "1,200.50"}]

        class Logger:
            def __init__(self) -> None:
                self.messages: list[str] = []

            def info(self, message: str, *args: object) -> None:
                self.messages.append(message % args)

        logger = Logger()

        with patch("requests.get", return_value=Response()):
            source = prepare_api_source(
                "https://example.test/table/Ledger_Table?api_key=secret-token&tenant=acme",
                logger=logger,
            )

        self.assertEqual(source.display_name, "https://example.test/table/Ledger_Table")
        logged = "\n".join(logger.messages)
        self.assertNotIn("secret-token", logged)
        self.assertNotIn("api_key", logged)
        self.assertIn("https://example.test/table/Ledger_Table", logged)

    def test_api_source_accepts_nested_json_list(self) -> None:
        class Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {
                    "status": "ok",
                    "business_data": {
                        "Ledger_Table": [
                            {"VoucherNo": 1, "Debit": "1,200.50"},
                            {"VoucherNo": 2, "Debit": "90.00"},
                        ]
                    },
                }

        with patch("requests.get", return_value=Response()):
            source = prepare_api_source("https://example.test/business_data", logger=None)

        self.assertIsNotNone(source.dataframe)
        self.assertEqual(len(source.dataframe), 2)
        self.assertIn("voucherno", source.dataframe.columns)
        self.assertTrue(math.isclose(float(source.dataframe["debit"].iloc[0]), 1200.5))

    def test_api_source_accepts_object_map_records(self) -> None:
        class Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {
                    "row_1": {"Account": "Sales", "Credit": "180.00"},
                    "row_2": {"Account": "Cash", "Credit": "0"},
                }

        with patch("requests.get", return_value=Response()):
            source = prepare_api_source("https://example.test/accounts", logger=None)

        self.assertIsNotNone(source.dataframe)
        self.assertEqual(len(source.dataframe), 2)
        self.assertEqual(source.dataframe["account"].tolist(), ["Sales", "Cash"])

    def test_api_source_accepts_single_json_object(self) -> None:
        class Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {"status": "ok", "table_count": 695}

        with patch("requests.get", return_value=Response()):
            source = prepare_api_source("https://example.test/tables/summary", logger=None)

        self.assertIsNotNone(source.dataframe)
        self.assertEqual(len(source.dataframe), 1)
        self.assertEqual(source.dataframe["status"].iloc[0], "ok")


class PdfSourceTests(unittest.TestCase):
    def test_prepare_pdf_source_uses_pymupdf_primary_extractor(self) -> None:
        with TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "sales-book.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fake")
            module = types.SimpleNamespace(
                open=lambda _: _MuPdfDoc([
                    _MuPdfPage([
                        [
                            ["Region", "Revenue"],
                            ["North", "1200"],
                            ["South", "900"],
                        ],
                    ]),
                ]),
            )
            with patch.dict("sys.modules", {"pymupdf": module, "fitz": module, "pdfplumber": None}):
                source = prepare_pdf_source(pdf_path, logger=None)

        self.assertEqual(source.row_count, 2)
        self.assertEqual(source.dataframe.columns.tolist(), ["region", "revenue"])
        self.assertEqual(source.dataframe["revenue"].tolist(), [1200, 900])

    def test_prepare_pdf_source_uses_fast_sales_order_text_blocks(self) -> None:
        blocks = [
            "\n".join([
                f"{i} 01/07/2025",
                "1.00",
                f"SO-{2100 + i}",
                "Tirupathi Enterprises",
                "Supreme - Agri PN-06 50mm Pipe",
                "15.00",
                "35.70",
            ])
            for i in range(1, 12)
        ]
        with TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "sales-orders.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fake")
            module = types.SimpleNamespace(
                open=lambda _: _MuPdfDoc([
                    _TextBlockPage("Sales Orders Book Report", blocks),
                ]),
            )
            with patch.dict("sys.modules", {"pymupdf": module, "fitz": module, "pdfplumber": None}):
                source = prepare_pdf_source(pdf_path, logger=None)

        self.assertEqual(source.row_count, 11)
        self.assertEqual(source.dataframe.columns.tolist(), ["s_no", "date", "exchange_rate", "vno", "account", "product", "quantity", "rate"])
        self.assertEqual(source.dataframe["date"].tolist()[0], pd.Timestamp("2025-07-01"))
        self.assertEqual(source.dataframe["quantity"].tolist()[0], 15.0)

    def test_prepare_pdf_source_uses_fast_sales_book_text_blocks(self) -> None:
        blocks = [
            "\n".join([
                f"{i} 01/01/2026",
                f"SIR-{700 + i}",
                "Sriramulu-Warasiguda",
                "36ABCDE1234F1Z5",
                "MP1A6TEE050L",
                "Supreme - Agri PN-06 50mm Hw Tee",
                "2.00",
                "42.10",
                "50.67 39174000",
                "84.20",
                "41.26",
                "9.00",
                "3.86",
                "9.00",
                "3.86",
                "January2026",
            ])
            for i in range(1, 12)
        ]
        with TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "sales-book.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fake")
            module = types.SimpleNamespace(
                open=lambda _: _MuPdfDoc([
                    _TextBlockPage("Sales Book Report", blocks),
                ]),
            )
            with patch.dict("sys.modules", {"pymupdf": module, "fitz": module, "pdfplumber": None}):
                source = prepare_pdf_source(pdf_path, logger=None)

        self.assertEqual(source.row_count, 11)
        self.assertEqual(source.dataframe.columns.tolist(), [
            "s_no", "date", "vno", "account", "gstin", "supplier_part_code", "product", "quantity", "rate",
            "net", "hsn_code", "gross", "discount", "cgst_rate", "cgst", "sgst_rate", "sgst", "igst_rate", "igst", "month_name",
        ])
        self.assertEqual(source.dataframe["date"].tolist()[0], pd.Timestamp("2026-01-01"))
        self.assertEqual(source.dataframe["hsn_code"].tolist()[0], 39174000)

    def test_prepare_pdf_source_handles_split_hsn_in_sales_book_blocks(self) -> None:
        blocks = [
            "\n".join([
                f"{i} 01/01/2026",
                f"SIR-{700 + i}",
                "Sriramulu-Warasiguda",
                "36ABCDE1234F1Z5",
                "MP1A6TEE050L",
                "Supreme - Agri PN-06 50mm Hw Tee",
                "2.00",
                "42.10",
                "50.67",
                "39174000",
                "84.20",
                "41.26",
                "9.00",
                "3.86",
                "9.00",
                "3.86",
                "January2026",
            ])
            for i in range(1, 12)
        ]
        with TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "sales-book-split-hsn.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fake")
            module = types.SimpleNamespace(open=lambda _: _MuPdfDoc([_TextBlockPage("Sales Book Report", blocks)]))
            with patch.dict("sys.modules", {"pymupdf": module, "fitz": module, "pdfplumber": None}):
                source = prepare_pdf_source(pdf_path, logger=None)

        self.assertEqual(source.row_count, 11)
        self.assertEqual(source.dataframe["product"].tolist()[0], "Supreme - Agri PN-06 50mm Hw Tee")
        self.assertEqual(source.dataframe["hsn_code"].tolist()[0], 39174000)
        self.assertEqual(source.dataframe["gross"].tolist()[0], 84.2)

    def test_prepare_pdf_source_handles_missing_gstin_in_sales_book_blocks(self) -> None:
        blocks = [
            "\n".join([
                f"{i} 01/01/2026",
                f"SIR-{700 + i}",
                "Sriramulu-Warasiguda",
                "MP1A6TEE050L",
                "Supreme - Agri PN-06 50mm Hw Tee",
                "2.00",
                "42.10",
                "50.67 39174000",
                "84.20",
                "41.26",
                "9.00",
                "3.86",
                "9.00",
                "3.86",
                "January2026",
            ])
            for i in range(1, 12)
        ]
        with TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "sales-book-missing-gstin.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fake")
            module = types.SimpleNamespace(open=lambda _: _MuPdfDoc([_TextBlockPage("Sales Book Report", blocks)]))
            with patch.dict("sys.modules", {"pymupdf": module, "fitz": module, "pdfplumber": None}):
                source = prepare_pdf_source(pdf_path, logger=None)

        self.assertEqual(source.row_count, 11)
        self.assertEqual(source.dataframe["gstin"].tolist()[0], "")
        self.assertEqual(source.dataframe["supplier_part_code"].tolist()[0], "MP1A6TEE050L")
        self.assertEqual(source.dataframe["product"].tolist()[0], "Supreme - Agri PN-06 50mm Hw Tee")

    def test_prepare_pdf_source_handles_igst_sales_book_blocks(self) -> None:
        blocks = [
            "\n".join([
                f"{i} 02/01/2026",
                f"SIT-{10880 + i}",
                "Cre8ive Aqua Designers",
                "37DFLPP7078J2ZJ",
                "MP1ASTEE063D",
                "Supreme - Agri PN-16 63mm Tee",
                "5.00",
                "101.60",
                "293.73 39174000",
                "508.00",
                "259.08",
                "18.00 44.81 January2026",
            ])
            for i in range(1, 12)
        ]
        with TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "sales-book-igst.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fake")
            module = types.SimpleNamespace(open=lambda _: _MuPdfDoc([_TextBlockPage("Sales Book Report", blocks)]))
            with patch.dict("sys.modules", {"pymupdf": module, "fitz": module, "pdfplumber": None}):
                source = prepare_pdf_source(pdf_path, logger=None)

        self.assertEqual(source.row_count, 11)
        self.assertEqual(source.dataframe["date"].tolist()[0], pd.Timestamp("2026-01-02"))
        self.assertEqual(source.dataframe["igst_rate"].tolist()[0], 18.0)
        self.assertEqual(source.dataframe["igst"].tolist()[0], 44.81)
        self.assertEqual(source.dataframe["cgst"].tolist()[0], "")

    def test_prepare_pdf_source_extracts_tabular_data(self) -> None:
        with TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "printed-sheet.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fake")
            module = types.SimpleNamespace(
                open=lambda _: _PdfDoc([
                    _PdfPage([
                        [
                            ["Region", "Revenue", "Orders"],
                            ["North", "1200", "12"],
                            ["South", "900", "9"],
                        ],
                    ]),
                ]),
            )
            with patch.dict("sys.modules", {"pdfplumber": module}):
                source = prepare_pdf_source(pdf_path, logger=None)

        self.assertEqual(source.source_kind, "PDF table")
        self.assertEqual(source.display_name, "printed-sheet.pdf")
        self.assertEqual(source.row_count, 2)
        self.assertIsNotNone(source.dataframe)
        assert source.dataframe is not None
        self.assertEqual(source.dataframe.columns.tolist(), ["region", "revenue", "orders"])
        self.assertEqual(source.dataframe["revenue"].tolist(), [1200, 900])

    def test_prepare_pdf_source_rejects_pdf_without_tables(self) -> None:
        with TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "scan.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fake")
            module = types.SimpleNamespace(open=lambda _: _PdfDoc([_PdfPage([])]))
            with patch.dict("sys.modules", {"pdfplumber": module}):
                with self.assertRaisesRegex(ValueError, "No tables found"):
                    prepare_pdf_source(pdf_path, logger=None)

    def test_prepare_pdf_source_deduplicates_repeated_headers(self) -> None:
        with TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "duplicate-headers.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fake")
            module = types.SimpleNamespace(
                open=lambda _: _PdfDoc([
                    _PdfPage([
                        [
                            ["Region", "Amount", "Amount"],
                            ["North", "1200", "12"],
                            ["South", "900", "9"],
                        ],
                    ]),
                ]),
            )
            with patch.dict("sys.modules", {"pdfplumber": module}):
                source = prepare_pdf_source(pdf_path, logger=None)

        self.assertEqual(source.dataframe.columns.tolist(), ["region", "amount", "amount_2"])


if __name__ == "__main__":
    unittest.main()
