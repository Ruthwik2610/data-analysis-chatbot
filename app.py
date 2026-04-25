from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from src.config import AppConfig
from src.data_sources import prepare_connector_source, prepare_local_file_source, prepare_uploaded_source
from src.logging_config import log_event, setup_loggers
from src.model_router import GeminiRouter, LLMUnavailable, ModelChoice
from src.query_engine import build_query_plan, heuristic_intent, validate_readonly_sql
from src.visualization import choose_visualization, deterministic_summary


st.set_page_config(page_title="CSV Intelligence Chat", page_icon="◦", layout="wide")


def apply_css() -> None:
    st.markdown(
        """
        <style>
        :root {
          --paper: #faf7f0;
          --panel: #ffffff;
          --panel-2: #fffdf8;
          --ink: #2b2926;
          --muted: #706a62;
          --line: #e8ded1;
          --accent: #c15f3c;
          --accent-soft: #f4dfd3;
        }
        .stApp { background: var(--paper); color: var(--ink); }
        [data-testid="stSidebar"] { background: #f4eee4; border-right: 1px solid var(--line); }
        .main .block-container { max-width: 960px; padding-top: 1.25rem; padding-bottom: 7rem; }
        h1, h2, h3 { letter-spacing: 0; color: var(--ink); }
        .hero {
          text-align: center;
          padding: 1.6rem 0 1.1rem 0;
          margin-bottom: .6rem;
        }
        .hero h1 {
          font-size: clamp(2rem, 4vw, 3.4rem);
          margin: 0;
          font-weight: 680;
        }
        .hero p { color: var(--muted); margin: .55rem auto 0; max-width: 680px; font-size: 1.02rem; }
        .context-pill {
          display: inline-flex;
          align-items: center;
          gap: .45rem;
          padding: .45rem .7rem;
          border-radius: 999px;
          background: #f7efe4;
          border: 1px solid var(--line);
          color: var(--ink);
          font-size: .92rem;
          margin: .15rem .25rem .35rem 0;
        }
        .context-row {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          justify-content: space-between;
          gap: .65rem;
          margin-bottom: .45rem;
        }
        .result-card {
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 20px;
          padding: 1rem 1.1rem;
          box-shadow: 0 10px 30px rgba(69, 48, 25, .045);
          margin: .75rem 0 1rem;
        }
        .metric-card {
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 16px;
          padding: 1rem;
          height: 100%;
        }
        .small-muted { color: var(--muted); font-size: .9rem; }
        div[data-testid="stChatMessage"] {
          background: transparent;
          border: 0;
          padding: .3rem 0;
        }
        div[data-testid="stChatMessageContent"] {
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 20px;
          padding: 1rem 1.05rem;
          box-shadow: 0 8px 24px rgba(69, 48, 25, .04);
        }
        div[data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) div[data-testid="stChatMessageContent"] {
          background: #f6eadc;
        }
        .stButton > button {
          border-radius: 999px;
          border: 1px solid var(--line);
          background: var(--panel);
          color: var(--ink);
        }
        .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
          border-radius: 14px;
          border-color: var(--line);
        }
        [data-testid="stFileUploader"] section {
          border-radius: 18px;
          border: 1px dashed #d7c5b3;
          background: #fffaf3;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
          border-color: var(--line);
          border-radius: 22px;
          box-shadow: 0 12px 35px rgba(63, 45, 28, .05);
          background: var(--panel);
        }
        [data-testid="stDataFrame"] {
          border-radius: 14px;
          overflow: hidden;
          border: 1px solid var(--line);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource(show_spinner=False)
def get_connection(db_path: str):
    import duckdb

    return duckdb.connect(db_path, read_only=True)


@st.cache_data(show_spinner=False, ttl=3600)
def run_db_query_cached(db_path: str, table_name: str, sql: str, params_key: str) -> pd.DataFrame:
    import json
    import duckdb

    params = json.loads(params_key)
    con = duckdb.connect(db_path, read_only=True)
    try:
        if table_name != "orders":
            safe_table = '"' + table_name.replace('"', '""') + '"'
            con.execute(f"CREATE TEMP VIEW orders AS SELECT * FROM {safe_table}")
        return con.execute(sql, params).fetchdf()
    finally:
        con.close()


def run_memory_query(df: pd.DataFrame, sql: str, params_key: str) -> pd.DataFrame:
    import json
    import duckdb

    params = json.loads(params_key)
    con = duckdb.connect(":memory:")
    try:
        con.register("orders", df)
        return con.execute(sql, params).fetchdf()
    finally:
        con.close()


def schema_allowed_columns(schema: dict[str, Any]) -> set[str]:
    return {col["name"] for col in schema["columns"]}


def conversation_summary(messages: list[dict[str, Any]]) -> str:
    recent = messages[-6:]
    return "\n".join(f"{msg['role']}: {str(msg.get('content', ''))[:500]}" for msg in recent)


def params_key(params: list[Any]) -> str:
    import json

    return json.dumps(params, default=str, ensure_ascii=False)


def render_chart(df: pd.DataFrame, viz: str, title: str) -> None:
    numeric_cols = list(df.select_dtypes(include="number").columns)
    non_numeric = [col for col in df.columns if col not in numeric_cols]
    if viz == "card" and not df.empty:
        cols = st.columns(min(len(df.columns), 3))
        for index, col_name in enumerate(df.columns[:3]):
            with cols[index % len(cols)]:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.caption(col_name.replace("_", " ").title())
                st.metric(label="", value=str(df.iloc[0][col_name]))
                st.markdown("</div>", unsafe_allow_html=True)
        return
    if viz == "line" and "period" in df.columns and numeric_cols:
        chart = alt.Chart(df).mark_line(point=True).encode(
            x=alt.X("period:T", title="Period"),
            y=alt.Y(f"{numeric_cols[-1]}:Q", title=numeric_cols[-1].replace("_", " ").title()),
            tooltip=list(df.columns),
        ).properties(height=330, title=title)
        st.altair_chart(chart, use_container_width=True)
        return
    if viz == "pie" and non_numeric and numeric_cols:
        chart = alt.Chart(df).mark_arc(innerRadius=48).encode(
            theta=alt.Theta(f"{numeric_cols[-1]}:Q"),
            color=alt.Color(f"{non_numeric[0]}:N", legend=alt.Legend(title=non_numeric[0].replace("_", " ").title())),
            tooltip=list(df.columns),
        ).properties(height=340, title=title)
        st.altair_chart(chart, use_container_width=True)
        return
    if viz == "bar" and non_numeric and numeric_cols:
        chart = alt.Chart(df).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
            x=alt.X(f"{non_numeric[0]}:N", sort="-y", title=non_numeric[0].replace("_", " ").title()),
            y=alt.Y(f"{numeric_cols[-1]}:Q", title=numeric_cols[-1].replace("_", " ").title()),
            color=alt.value("#8b5e34"),
            tooltip=list(df.columns),
        ).properties(height=330, title=title)
        st.altair_chart(chart, use_container_width=True)
        return
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_result(message: dict[str, Any], show_sql: bool = False) -> None:
    st.markdown(message["content"])
    df = message.get("dataframe")
    if isinstance(df, pd.DataFrame):
        st.markdown('<div class="result-card">', unsafe_allow_html=True)
        st.subheader(message.get("title", "Result"))
        st.caption(f"{message.get('row_count', len(df)):,} verified result row(s)")
        viz = message.get("viz", "table")
        render_chart(df, viz, message.get("title", "Result"))
        if viz != "table":
            st.markdown("#### Table")
            st.dataframe(df.head(100), use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
    how = message.get("how")
    if how:
        with st.expander("How I answered"):
            st.write(how)
            if show_sql and message.get("sql"):
                st.code(message["sql"], language="sql")


def main() -> None:
    apply_css()
    config = AppConfig.from_env()
    loggers = setup_loggers(Path("logs"))
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Upload or connect a data source, then ask for tables, charts, trends, or lookups.",
            }
        ]
    if "chat_titles" not in st.session_state:
        st.session_state.chat_titles = ["Current analysis"]
    if "connector_payload" not in st.session_state:
        st.session_state.connector_payload = None
    if "local_payload" not in st.session_state:
        st.session_state.local_payload = None

    with st.sidebar:
        st.title("Chats")
        if st.button("+ New chat", use_container_width=True):
            st.session_state.messages = [
                {"role": "assistant", "content": "New chat ready. Add a data source and ask a question."}
            ]
            st.session_state.connector_payload = None
            st.session_state.local_payload = None
        st.markdown("#### Recent")
        for title in st.session_state.chat_titles:
            st.button(title, use_container_width=True, disabled=True)

    st.markdown(
        """
        <div class="hero">
          <h1>What would you like to know?</h1>
          <p>Attach a file or connect a source. I’ll keep the data in context, query it safely, and show tables or charts only when they help.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    source = None
    source_error = None
    uploaded_file = None
    route = "Upload"
    ingest_label = "Analyze directly"

    with st.container(border=True):
        st.caption("Data context")
        route = st.radio("Data source", ["Upload", "Connector", "Local path"], horizontal=True, label_visibility="collapsed")
        ingest_label = st.radio("Ingest method", ["Analyze directly", "Convert to SQL cache"], horizontal=True)
        ingest_method = "sql" if ingest_label == "Convert to SQL cache" else "direct"
        sheet_name = ""
        table_name = "orders"
        connector_kind = "auto"
        connector_input = ""
        local_path = None

        if route == "Upload":
            uploaded_file = st.file_uploader("📎 Add file to context", type=["csv", "xlsx", "xls", "json", "duckdb", "db"])
            if uploaded_file is not None:
                st.caption(f"Ready: {uploaded_file.name}")
            with st.expander("Advanced ingest options"):
                sheet_name = st.text_input("Sheet name for Excel files", value="", placeholder="Optional")
                table_name = st.text_input("Table name for DuckDB uploads", value="orders")
        elif route == "Connector":
            connector_kind = st.radio("Connector type", ["API endpoint", "MCP/export path", "Terminal command"], horizontal=True)
            if connector_kind == "Terminal command":
                connector_input = st.text_area("Terminal command returning JSON or CSV", placeholder="curl https://api.example.com/orders")
            else:
                connector_input = st.text_input("Connector path or API URL", placeholder="https://... or /path/from/connector/export.json")
            if st.button("Connect source", use_container_width=True):
                st.session_state.connector_payload = {
                    "kind": connector_kind,
                    "input": connector_input,
                    "ingest_method": ingest_method,
                }
        else:
            local_text = st.text_input("Local file path", value=str(config.data_path), placeholder="/path/to/file.csv")
            local_path = Path(local_text).expanduser() if local_text.strip() else None
            with st.expander("Advanced ingest options"):
                sheet_name = st.text_input("Sheet name for Excel files", value="", placeholder="Optional")
                table_name = st.text_input("Table name for DuckDB files", value="orders")
            if st.button("Use local file", use_container_width=True):
                st.session_state.local_payload = {
                    "path": str(local_path) if local_path else "",
                    "sheet_name": sheet_name,
                    "table_name": table_name,
                    "ingest_method": ingest_method,
                }

    try:
        with st.spinner("Preparing data source..."):
            if route == "Upload":
                if uploaded_file is None:
                    source = None
                else:
                    source = prepare_uploaded_source(
                        uploaded_file,
                        config.cache_dir,
                        logger=loggers["cache"],
                        sheet_name=sheet_name or None,
                        table_name=table_name,
                        ingest_method=ingest_method,
                    )
            elif route == "Connector":
                payload = st.session_state.connector_payload
                if payload:
                    kind = "terminal" if payload["kind"] == "Terminal command" else "auto"
                    source = prepare_connector_source(
                        payload["input"],
                        config.cache_dir,
                        logger=loggers["cache"],
                        ingest_method=payload["ingest_method"],
                        connector_kind=kind,
                    )
            else:
                payload = st.session_state.local_payload
                if payload and payload.get("path"):
                    source = prepare_local_file_source(
                        Path(payload["path"]).expanduser(),
                        config.cache_dir,
                        logger=loggers["cache"],
                        table_name=payload["table_name"],
                        sheet_name=payload["sheet_name"] or None,
                        force=False,
                        ingest_method=payload["ingest_method"],
                    )
    except Exception as exc:
        log_event(loggers["errors"], "source_error", source=route, error=str(exc))
        source_error = "I couldn't prepare that data source. Please check the logs for details."

    if source_error:
        st.error(source_error)

    if source:
        schema = source.schema
        allowed_columns = schema_allowed_columns(schema)
        st.markdown(
            f"""
            <div class="context-row">
              <span class="context-pill">📄 1 file in context: <strong>{source.display_name}</strong></span>
              <span class="context-pill">{source.source_kind} · {schema.get("row_count", 0):,} rows · {len(schema.get("columns", []))} columns</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        schema = {}
        allowed_columns = set()
        st.info("Add a file or connector above to start the analysis.")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                render_result(message, False)
            else:
                st.markdown(message["content"])

    question = st.chat_input("Ask about the data in context", disabled=source is None)
    if not question:
        return

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    request_id = uuid.uuid4().hex[:12]
    with st.chat_message("assistant"):
        try:
            router = GeminiRouter(
                api_key=config.gemini_api_key,
                models=ModelChoice(config.default_model, config.escalation_model, config.fallback_model),
                logger=loggers["llm"],
                char_budget=config.prompt_char_budget,
            )

            if router.available:
                intent, model_used = router.classify_intent(
                    request_id=request_id,
                    user_question=question,
                    schema_context=schema,
                    conversation_summary=conversation_summary(st.session_state.messages),
                )
            else:
                intent, model_used = heuristic_intent(question, allowed_columns), "offline-heuristic"

            if intent.get("intent_type") == "clarification":
                content = intent.get("clarifying_question") or "Can you clarify the metric or grouping you want?"
                response = {"role": "assistant", "content": content, "how": f"Model: {model_used}; asked for missing context."}
                st.markdown(content)
                st.session_state.messages.append(response)
                return

            plan = build_query_plan(intent, question, allowed_columns)
            validate_readonly_sql(plan.sql)
            start = time.perf_counter()
            if source.db_path:
                df = run_db_query_cached(source.db_path, source.table_name, plan.sql, params_key(plan.params))
            elif source.dataframe is not None:
                df = run_memory_query(source.dataframe, plan.sql, params_key(plan.params))
            else:
                raise RuntimeError("No executable data source is available.")
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            log_event(
                loggers["query"],
                "query_executed",
                request_id=request_id,
                source=source.source_kind,
                sql_hash=plan.cache_key,
                rows=len(df),
                elapsed_ms=elapsed_ms,
            )

            viz = choose_visualization(question, intent, df)
            sample = df.head(50).to_dict(orient="records")
            try:
                content = router.summarize_answer(
                    request_id=request_id,
                    user_question=question,
                    intent=intent,
                    result_sample=sample,
                    row_count=len(df),
                ) if router.available else deterministic_summary(question, df, len(df))
            except LLMUnavailable:
                content = deterministic_summary(question, df, len(df))

            how = f"Source: {source.source_kind}. Model: {model_used}. {plan.how} Display: {viz}. Query ID: {plan.cache_key}."
            response = {
                "role": "assistant",
                "content": content,
                "dataframe": df,
                "viz": viz,
                "title": plan.title,
                "row_count": len(df),
                "how": how,
                "sql": plan.sql,
            }
            render_result(response, False)
            if len(st.session_state.messages) <= 2:
                st.session_state.chat_titles = [question[:42] + ("..." if len(question) > 42 else "")]
            st.session_state.messages.append(response)
        except Exception as exc:
            log_event(loggers["errors"], "chat_error", request_id=request_id, error=str(exc))
            content = "I couldn't answer that safely from the available data. Please try a more specific question."
            st.markdown(content)
            st.session_state.messages.append({"role": "assistant", "content": content})


if __name__ == "__main__":
    main()
