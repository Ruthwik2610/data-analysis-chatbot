from __future__ import annotations

import unittest
import types
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from src.data_sources import prepare_pdf_source
from src.prompting import build_intent_prompt, xml_escape
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


class PdfSourceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
