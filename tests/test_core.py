from __future__ import annotations

import unittest
import types
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from src.data_sources import prepare_pdf_source
from src.prompting import build_intent_prompt, xml_escape
from src.project_intelligence import (
    apply_instruction_rules,
    build_instruction_context,
    default_source_instructions,
)
from src.query_engine import build_query_plan, heuristic_intent
from src.visualization import choose_visualization


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


class QueryPlanTests(unittest.TestCase):
    def test_top_three_prefers_table(self) -> None:
        intent = heuristic_intent("give me top 3 categories by revenue", ALLOWED)
        plan = build_query_plan(intent, "give me top 3 categories by revenue", ALLOWED)
        self.assertIn("LIMIT 3", plan.sql)
        df = pd.DataFrame({"prod_category": ["A", "B", "C"], "revenue": [3, 2, 1]})
        self.assertEqual(choose_visualization("give me top 3 categories by revenue", intent, df), "table")

    def test_trend_prefers_line(self) -> None:
        intent = heuristic_intent("monthly revenue trend", ALLOWED)
        plan = build_query_plan(intent, "monthly revenue trend", ALLOWED)
        self.assertIn("date_trunc('month'", plan.sql)
        df = pd.DataFrame({"period": pd.to_datetime(["2024-01-01", "2024-02-01"]), "revenue": [1, 2]})
        self.assertEqual(choose_visualization("monthly revenue trend", intent, df), "line")

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
        self.assertIn('SUM(TRY_CAST("revenue" AS DOUBLE))', plan.sql)
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

        self.assertIn('SUM(TRY_CAST("quantity" AS DOUBLE)) AS "items_sold"', plan.sql)
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
