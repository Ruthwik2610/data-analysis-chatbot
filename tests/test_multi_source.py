from __future__ import annotations

import unittest

from backend.server import _detect_join_candidates, _safe_upload_filename, _workspace_table_name
from src.mcp_pool import parse_tool_result_to_dataframe
from src.query_engine import validate_readonly_sql


class LocalHardeningTests(unittest.TestCase):
    def test_rejects_duckdb_file_reader_functions(self) -> None:
        with self.assertRaises(ValueError):
            validate_readonly_sql("SELECT * FROM read_csv_auto('/etc/passwd')")

    def test_sanitizes_uploaded_filename_to_basename(self) -> None:
        self.assertEqual(_safe_upload_filename("../../orders.csv"), "orders.csv")
        self.assertEqual(_safe_upload_filename("/tmp/report.xlsx"), "report.xlsx")

    def test_rejects_empty_uploaded_filename(self) -> None:
        with self.assertRaises(ValueError):
            _safe_upload_filename("../")


class WorkspaceTests(unittest.TestCase):
    def test_workspace_table_names_are_stable_and_safe(self) -> None:
        self.assertEqual(_workspace_table_name("src_abc123", "Sales Orders.csv"), "src_sales_orders")
        self.assertEqual(_workspace_table_name("src_abc123", "123.csv"), "src_123")
        self.assertEqual(_workspace_table_name("src_abc123", "!!!"), "src_abc123")

    def test_detects_likely_join_key_between_sources(self) -> None:
        sources = [
            {
                "id": "customers",
                "name": "customers.csv",
                "table": "src_customers",
                "columns": [
                    {"name": "customer_id", "type": "BIGINT"},
                    {"name": "customer_name", "type": "VARCHAR"},
                ],
            },
            {
                "id": "orders",
                "name": "orders.csv",
                "table": "src_orders",
                "columns": [
                    {"name": "customer_id", "type": "BIGINT"},
                    {"name": "revenue", "type": "DOUBLE"},
                ],
            },
        ]
        candidates = _detect_join_candidates(sources)
        self.assertEqual(candidates[0]["left_table"], "src_customers")
        self.assertEqual(candidates[0]["right_table"], "src_orders")
        self.assertEqual(candidates[0]["left_column"], "customer_id")
        self.assertEqual(candidates[0]["right_column"], "customer_id")

    def test_mcp_parser_accepts_one_row_tabular_results(self) -> None:
        df = parse_tool_result_to_dataframe('[{"month":"Jan","revenue":100}]')
        self.assertIsNotNone(df)
        self.assertEqual(df.shape, (1, 2))


if __name__ == "__main__":
    unittest.main()
