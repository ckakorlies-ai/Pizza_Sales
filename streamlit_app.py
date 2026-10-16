"""Streamlit UI for asking natural-language questions of the Pizza Sales API."""

import os
from typing import Any, Optional, Tuple

import requests
import streamlit as st
from dotenv import load_dotenv


load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT_SECONDS = 60

st.set_page_config(
    page_title="Pizza Sales Analytics",
    page_icon="🍕",
    layout="wide",
)

st.markdown(
    """
    <style>
      .block-container {max-width: 1180px; padding-top: 2rem; padding-bottom: 3rem;}
      [data-testid="stMetric"] {
        background: #fff;
        border: 1px solid #eceee8;
        padding: 1rem 1.1rem;
        border-radius: 12px;
      }
      [data-testid="stMetricLabel"] {color: #687064;}
      div.stButton > button[kind="primary"] {
        background: #e96b48;
        border-color: #e96b48;
      }
      div.stButton > button[kind="primary"]:hover {
        background: #d95837;
        border-color: #d95837;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def api_get(path: str, auth: Optional[Tuple[str, str]] = None) -> Any:
    response = requests.get(
        f"{API_BASE_URL}{path}",
        timeout=REQUEST_TIMEOUT_SECONDS,
        auth=auth,
    )
    response.raise_for_status()
    return response.json()


def api_post(
    path: str,
    payload: dict[str, str],
    auth: Optional[Tuple[str, str]] = None,
) -> Any:
    response = requests.post(
        f"{API_BASE_URL}{path}",
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
        auth=auth,
    )
    response.raise_for_status()
    return response.json()


def display_api_error(error: Exception) -> None:
    response = getattr(error, "response", None)
    if response is not None:
        try:
            body = response.json()
            detail = body.get("detail") or body.get("message")
            if detail:
                st.error(f"API request failed: {detail}")
                return
        except (ValueError, AttributeError):
            pass
    st.error(f"Could not reach the analytics API at {API_BASE_URL}: {error}")


def display_metric(label: str, metrics: dict[str, Any], key: str, format_string: str = "%s") -> None:
    value = metrics.get(key)
    if value is None:
        st.metric(label, "—")
        return
    try:
        formatted = format_string % float(value)
        if format_string == "%s":
            formatted = str(value)
    except (TypeError, ValueError):
        formatted = str(value)
    st.metric(label, formatted)


def apply_suggested_question() -> None:
    suggestion = st.session_state.get("suggested_question")
    if suggestion:
        st.session_state["question_input"] = suggestion


def render_analytics_tab() -> None:
    st.caption("Explore your sales performance and ask questions in plain language.")

    with st.sidebar:
        st.subheader("Connection")
        st.code(API_BASE_URL, language=None)
        if st.button("Refresh metrics", use_container_width=True):
            st.rerun()
        st.caption("The Streamlit app uses the FastAPI backend for all database and AI operations.")

    st.subheader("Performance snapshot")
    try:
        metrics = api_get("/api/kpis")
    except requests.exceptions.JSONDecodeError as error:
        st.error(f"The KPI endpoint returned invalid JSON: {error}")
        metrics = None
    except requests.RequestException as error:
        display_api_error(error)
        metrics = None

    if metrics is not None:
        metric_columns = st.columns(5)
        definitions = [
            ("Revenue", "total_revenue", "$%.2f"),
            ("Orders", "total_orders", "%.0f"),
            ("Pizzas sold", "total_pizzas_sold", "%.0f"),
            ("Average order value", "average_order_value", "$%.2f"),
            ("Pizzas per order", "average_pizzas_per_order", "%.2f"),
        ]
        for column, (label, key, formatter) in zip(metric_columns, definitions):
            with column:
                display_metric(label, metrics, key, formatter)

    st.divider()
    st.subheader("Ask your sales data")

    suggestions = [
        "What was total revenue?",
        "Which pizza generated the most revenue?",
        "Which category generated the most revenue?",
        "What is the average order value?",
    ]
    st.pills(
        "Try a question",
        suggestions,
        selection_mode="single",
        label_visibility="collapsed",
        key="suggested_question",
        on_change=apply_suggested_question,
    )

    with st.form("question_form"):
        question = st.text_input(
            "Your question",
            placeholder="For example: Which pizza sold the most?",
            max_chars=1000,
            key="question_input",
        )
        submitted = st.form_submit_button(
            "Ask question",
            type="primary",
            disabled=not question.strip(),
        )

    if submitted:
        st.session_state.pop("last_answer", None)
        try:
            with st.spinner("Generating and running a read-only sales query…"):
                answer = api_post("/api/query", {"question": question.strip()})
            st.session_state["last_answer"] = answer
        except requests.exceptions.JSONDecodeError as error:
            st.error(f"The query endpoint returned invalid JSON: {error}")
        except requests.RequestException as error:
            display_api_error(error)

    answer = st.session_state.get("last_answer")
    if answer:
        st.markdown("### Answer")
        if answer.get("status") == "pending_approval":
            st.warning(answer.get("summary", "This query is waiting for admin approval."))
            st.caption(f"Escalation case: {answer.get('escalation_id')}")
            st.caption(f"Confidence: {answer.get('confidence', 0):.0%}")
            if answer.get("sql"):
                st.code(answer["sql"], language="sql")
            return

        st.write(answer.get("summary", "Query completed."))
        result = answer.get("result") or {}
        rows = result.get("rows") or []
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("The query returned no rows.")

        if answer.get("sql"):
            with st.expander("View generated SQL"):
                st.code(answer["sql"], language="sql")

        if result.get("db_type"):
            st.caption(f"Executed using {result['db_type']}.")


def render_admin_tab() -> None:
    st.subheader("Human review queue")
    st.caption(
        "Low-confidence questions are held here and are not executed until an admin approves them."
    )

    credentials = st.session_state.get("admin_credentials")
    if credentials is None:
        with st.form("admin_login_form"):
            username = st.text_input("Admin username")
            password = st.text_input("Admin password", type="password")
            login_submitted = st.form_submit_button("Sign in")
        if login_submitted:
            if username and password:
                st.session_state["admin_credentials"] = (username, password)
                st.rerun()
            st.error("Enter both the admin username and password.")
        return

    header_left, header_right = st.columns([5, 1])
    with header_left:
        status = st.selectbox(
            "Cases",
            ["pending", "approved", "rejected"],
            key="admin_case_status",
        )
    with header_right:
        if st.button("Sign out", use_container_width=True):
            st.session_state.pop("admin_credentials", None)
            st.rerun()

    try:
        cases = api_get(f"/api/admin/escalations?status={status}", auth=credentials)
    except requests.exceptions.HTTPError as error:
        if error.response is not None and error.response.status_code == 401:
            st.session_state.pop("admin_credentials", None)
            st.error("Admin sign-in failed. Check the configured admin credentials and try again.")
            return
        display_api_error(error)
        return
    except requests.RequestException as error:
        display_api_error(error)
        return

    if not cases:
        st.info(f"No {status} escalation cases.")
        return

    for case in cases:
        with st.container(border=True):
            st.markdown(f"**Question:** {case['question']}")
            st.caption(
                f"Confidence: {case['confidence']:.0%} · "
                f"Created: {case['created_at']} · Case: {case['id']}"
            )
            if case.get("reason"):
                st.info(case["reason"])
            with st.expander("Review proposed SQL", expanded=status == "pending"):
                st.code(case["sql"], language="sql")

            if status == "pending":
                approve_column, reject_column = st.columns(2)
                with approve_column:
                    approve = st.button(
                        "Approve and run",
                        type="primary",
                        key=f"approve_{case['id']}",
                        use_container_width=True,
                    )
                with reject_column:
                    reject = st.button(
                        "Reject",
                        key=f"reject_{case['id']}",
                        use_container_width=True,
                    )

                decision = "approve" if approve else "reject" if reject else None
                if decision:
                    try:
                        api_post(
                            f"/api/admin/escalations/{case['id']}/decision",
                            {"decision": decision},
                            auth=credentials,
                        )
                        st.toast("Case approved." if decision == "approve" else "Case rejected.")
                        st.rerun()
                    except requests.RequestException as error:
                        display_api_error(error)
            elif case.get("result"):
                rows = (case["result"].get("rows") or [])
                if rows:
                    st.dataframe(rows, use_container_width=True, hide_index=True)


st.title("🍕 Pizza Sales Analytics")
analytics_tab, admin_tab = st.tabs(["Analytics", "Admin"])
with analytics_tab:
    render_analytics_tab()
with admin_tab:
    render_admin_tab()
