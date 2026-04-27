from __future__ import annotations

import unittest

import pandas as pd

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


class PromptTests(unittest.TestCase):
    def test_xml_escape_dynamic_content(self) -> None:
        self.assertEqual(xml_escape('<hello attr="x">&'), "&lt;hello attr=&quot;x&quot;&gt;&amp;")

    def test_prompt_contains_escaped_question(self) -> None:
        prompt = build_intent_prompt(
            schema_context={"columns": [{"name": "prod_category"}]},
            conversation_summary="",
            user_question='top <3 "products"',
            char_budget=5000,
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


if __name__ == "__main__":
    unittest.main()
