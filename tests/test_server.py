import pytest
import pandas as pd
from backend.server import _df_to_payload

def test_df_to_payload_handles_nat():
    # Arrange: Create a DataFrame with a NaT value
    df = pd.DataFrame({
        "timestamp": [pd.Timestamp("2024-01-01"), pd.NaT],
        "value": [10, 20]
    })
    
    # Act
    payload = _df_to_payload(df)
    
    # Assert
    # The first row should have the correct isoformat
    assert payload["rows"][0][0] == "2024-01-01T00:00:00"
    # The second row should have None (null in JSON), NOT "NaT"
    assert payload["rows"][1][0] is None

def test_assert_public_url_is_async():
    import asyncio
    from backend.server import _assert_public_url
    
    # This will fail (TypeError) if _assert_public_url is synchronous,
    # driving us to make it async.
    asyncio.run(_assert_public_url("http://example.com"))

def test_workspace_sql_sync_path_traversal(monkeypatch):
    from backend.server import _run_workspace_sql_sync

    connected_path = None

    class MockDuckDB:
        def connect(self, path, read_only=False):
            nonlocal connected_path
            connected_path = path
            class MockCon:
                def execute(self, sql):
                    return self
                def fetchdf(self):
                    import pandas as pd
                    return pd.DataFrame()
                def close(self):
                    pass
            return MockCon()

    monkeypatch.setattr("duckdb.connect", MockDuckDB().connect)

    chat_id = "../../../tmp/hacked"
    _run_workspace_sql_sync(chat_id, "SELECT 1")

    assert "tmp" not in str(connected_path)
    assert str(connected_path).endswith("hacked.duckdb")

def test_parse_tool_result_handles_large_csv():
    from src.mcp_pool import parse_tool_result_to_dataframe
    large_csv = "a,b,c\n" + "1,2,3\n" * 1000
    df = parse_tool_result_to_dataframe(large_csv)
    assert df is not None
    assert len(df) == 1000
