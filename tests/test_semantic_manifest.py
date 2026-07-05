from __future__ import annotations

from src.semantic_manifest import build_wren_mdl_from_schema, compact_semantic_context


SALES_SCHEMA = {
    "columns": [
        {"name": "order_id", "type": "INTEGER"},
        {"name": "order_date", "type": "DATE"},
        {"name": "customer_id", "type": "VARCHAR"},
        {"name": "total_price", "type": "DOUBLE"},
    ],
    "row_count": 25,
}


def test_build_wren_mdl_from_schema_preserves_model_columns_and_datasource() -> None:
    mdl = build_wren_mdl_from_schema(
        SALES_SCHEMA,
        model_name="orders",
        table_name="orders",
        data_source="duckdb",
    )

    assert mdl["catalog"] == "wren"
    assert mdl["schema"] == "main"
    assert mdl["dataSource"] == "duckdb"
    assert mdl["relationships"] == []
    assert mdl["models"] == [
        {
            "name": "orders",
            "tableReference": {"catalog": "", "schema": "main", "table": "orders"},
            "columns": [
                {"name": "order_id", "type": "INTEGER", "isCalculated": False},
                {"name": "order_date", "type": "DATE", "isCalculated": False},
                {"name": "customer_id", "type": "VARCHAR", "isCalculated": False},
                {"name": "total_price", "type": "DOUBLE", "isCalculated": False},
            ],
        }
    ]


def test_compact_semantic_context_promotes_metrics_entities_and_relationships() -> None:
    context = compact_semantic_context(
        {
            "row_grain": "line_item",
            "semantic_profile": {
                "columns": {
                    "total_price": {
                        "role": "metric",
                        "business_name": "revenue",
                        "synonyms": ["sales"],
                        "default_aggregation": "sum",
                        "meaning": "Gross sales amount",
                    }
                },
                "data_quality": {
                    "placeholder_tokens": ["unknown"],
                    "notes": ["Check placeholders"],
                },
            },
            "entities": {"order": "order_id", "customer": "customer_id"},
            "metrics": {
                "revenue": {
                    "column": "total_price",
                    "aggregation": "sum",
                    "synonyms": ["sales", "gross revenue"],
                }
            },
            "relationships": [
                {
                    "from_model": "orders",
                    "from_column": "customer_id",
                    "to_model": "customers",
                    "to_column": "id",
                    "cardinality": "many_to_one",
                    "approved": True,
                }
            ],
            "routing": {"good_for": ["sales"], "not_for": ["payroll"]},
        },
        allowed_columns={"order_id", "customer_id", "total_price"},
    )

    assert context["row_grain"] == "line_item"
    assert context["columns"]["total_price"]["role"] == "metric"
    assert context["columns"]["total_price"]["synonyms"] == ["sales"]
    assert context["metrics"]["revenue"]["expression"] == "sum(total_price)"
    assert context["metrics"]["revenue"]["synonyms"] == ["sales", "gross revenue"]
    assert context["entities"] == {"customer": "customer_id", "order": "order_id"}
    assert context["relationships"] == [
        "orders.customer_id -> customers.id (many_to_one, approved)"
    ]
    assert context["routing"] == {"good_for": ["sales"], "not_for": ["payroll"]}
    assert context["data_quality"]["placeholder_tokens"] == ["unknown"]


def test_compact_semantic_context_drops_invalid_metric_columns() -> None:
    context = compact_semantic_context(
        {
            "metrics": {
                "revenue": {"column": "missing_column", "aggregation": "sum"},
                "orders": {"column": "order_id", "aggregation": "count_distinct"},
            }
        },
        allowed_columns={"order_id"},
    )

    assert "revenue" not in context["metrics"]
    assert context["metrics"]["orders"]["expression"] == "count_distinct(order_id)"
