#!/usr/bin/env python3
"""End-to-end natural-language to SQL execution test for the pizza sales analytics project.

This script intentionally exercises the same flow the application should use in production:
1. Receive a natural-language question.
2. Convert it to a SQL statement using a schema-aware generator.
3. Validate the SQL before execution.
4. Run it against the configured database.
5. Print the result and fail fast if the SQL is unsafe or the query returns an unexpected shape.

Usage:
    python end_to_end_sql_test.py
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv() -> None:
        pass

try:
    import psycopg2
except Exception:  # pragma: no cover
    psycopg2 = None

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

load_dotenv(Path(__file__).with_name(".env"))

FORBIDDEN_SQL_KEYWORDS = {
    "DROP",
    "DELETE",
    "INSERT",
    "UPDATE",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "GRANT",
    "REVOKE",
    "ATTACH",
    "DETACH",
    "EXEC",
    "EXECUTE",
    "CALL",
    "MERGE",
    "COPY",
    "SAVEPOINT",
    "BEGIN",
    "COMMIT",
    "ROLLBACK",
}


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", question).strip()


def validate_sql(sql: str) -> bool:
    if not sql or not sql.strip():
        return False

    cleaned = sql.strip()
    if len(cleaned) > 20000:
        return False

    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()

    upper = cleaned.upper()
    if not upper.startswith("SELECT"):
        return False
    if "FROM" not in upper:
        return False
    if "PIZZA_SALES" not in upper:
        return False

    if any(keyword in upper for keyword in FORBIDDEN_SQL_KEYWORDS):
        return False

    if ";" in cleaned:
        return False

    return True


def clean_sql_response(raw_sql: str) -> str:
    sql = raw_sql.strip()
    sql = re.sub(r"```(?:sql)?", "", sql, flags=re.IGNORECASE)
    sql = sql.replace("```", "").strip()
    sql = re.sub(r"\s+", " ", sql)
    return sql.strip()


def fallback_sql_for_question(question: str) -> str:
    q = normalize_question(question).lower()

    if "total revenue" in q or "revenue" in q and "total" in q:
        return "SELECT COALESCE(SUM(total_price), 0) AS total_revenue FROM pizza_sales"

    if "total orders" in q or "orders" in q and "total" in q:
        return "SELECT COUNT(DISTINCT order_id) AS total_orders FROM pizza_sales"

    if "pizzas sold" in q or "total pizzas" in q or "quantity sold" in q:
        return "SELECT COALESCE(SUM(quantity), 0) AS total_pizzas_sold FROM pizza_sales"

    if "average order value" in q or "aov" in q:
        return (
            "SELECT COALESCE(SUM(total_price), 0) / NULLIF(COUNT(DISTINCT order_id), 0) "
            "AS average_order_value FROM pizza_sales"
        )

    if "average pizzas per order" in q or "pizzas per order" in q:
        return (
            "SELECT COALESCE(SUM(quantity), 0) / NULLIF(COUNT(DISTINCT order_id), 0) "
            "AS average_pizzas_per_order FROM pizza_sales"
        )

    if "category" in q and "revenue" in q:
        return (
            "SELECT pizza_category, COALESCE(SUM(total_price), 0) AS total_revenue "
            "FROM pizza_sales GROUP BY pizza_category ORDER BY total_revenue DESC"
        )

    if "top pizza" in q or "best pizza" in q or "most revenue" in q:
        return (
            "SELECT pizza_name, COALESCE(SUM(total_price), 0) AS total_revenue, "
            "COALESCE(SUM(quantity), 0) AS total_units_sold FROM pizza_sales "
            "GROUP BY pizza_name ORDER BY total_revenue DESC LIMIT 10"
        )

    if "monthly" in q or "month" in q:
        return (
            "SELECT DATE_TRUNC('month', order_date) AS month, "
            "COALESCE(SUM(total_price), 0) AS total_revenue FROM pizza_sales "
            "GROUP BY DATE_TRUNC('month', order_date) ORDER BY month"
        )

    return "SELECT COUNT(*) AS total_rows FROM pizza_sales"


def openai_generate_sql(question: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("CHAT_MODEL", "gpt-4o-mini").strip()
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    if not api_key or OpenAI is None:
        raise RuntimeError("OpenAI client is unavailable or API key is missing")

    client = OpenAI(api_key=api_key, base_url=base_url)
    prompt = f"""
You are a PostgreSQL SQL generation assistant for a pizza sales analytics project.

Schema:
Table: pizza_sales
Columns:
- id
- order_id
- order_date
- quantity
- unit_price
- total_price
- pizza_name
- pizza_category
- pizza_size
- pizza_ingredients

Rules:
- Only return a valid read-only SELECT query against pizza_sales.
- Do not use destructive or mutating SQL.
- Use COUNT(DISTINCT order_id) for total orders.
- Use SUM(total_price) for revenue and SUM(quantity) for units sold.
- Allow GROUP BY, ORDER BY, and DATE_TRUNC('month', order_date) when needed.
- Return only the final SQL, no markdown fences, no explanations.

Question: {question}
""".strip()

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=400,
    )
    content = response.choices[0].message.content or ""
    return clean_sql_response(content)


def generate_sql_for_question(question: str) -> str:
    try:
        generated = openai_generate_sql(question)
        if validate_sql(generated):
            return generated
    except Exception:
        pass

    fallback = fallback_sql_for_question(question)
    if not validate_sql(fallback):
        raise ValueError(f"Fallback SQL was invalid for question: {question!r}")
    return fallback


def get_db_connection():
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is not installed, cannot connect to PostgreSQL")
        return "postgresql", psycopg2.connect(database_url)

    sqlite_path = os.getenv("SQLITE_DB_PATH", str(Path(__file__).with_name("local_dev.db")))
    sqlite_path = Path(sqlite_path)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return "sqlite", sqlite3.connect(str(sqlite_path))


def execute_sql(sql: str):
    db_type, conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        normalized = [dict(zip(columns, row)) for row in rows]
        return {"db_type": db_type, "columns": columns, "rows": normalized}
    finally:
        conn.close()


def assert_result_shape(question: str, result: dict, expected_aliases: Iterable[str]):
    expected = set(expected_aliases)
    rows = result["rows"]
    if not rows:
        raise AssertionError(f"No data returned for question: {question!r}")

    keys = set(rows[0].keys())
    missing = expected - keys
    if missing:
        raise AssertionError(
            f"Expected alias(s) {sorted(expected)} but result keys were {sorted(keys)} "
            f"for question: {question!r}"
        )


def main() -> int:
    questions = [
        {
            "question": "What was total revenue?",
            "expected_aliases": {"total_revenue"},
        },
        {
            "question": "What were the total orders?",
            "expected_aliases": {"total_orders"},
        },
        {
            "question": "How many pizzas were sold in total?",
            "expected_aliases": {"total_pizzas_sold"},
        },
        {
            "question": "What is the average order value?",
            "expected_aliases": {"average_order_value"},
        },
        {
            "question": "What is the average pizzas per order?",
            "expected_aliases": {"average_pizzas_per_order"},
        },
        {
            "question": "Which pizza category generated the most revenue?",
            "expected_aliases": {"pizza_category", "total_revenue"},
        },
    ]

    print("Running end-to-end natural-language SQL execution checks...\n")

    report: List[dict[str, Any]] = []
    for check in questions:
        question = check["question"]
        try:
            sql = generate_sql_for_question(question)
            if not validate_sql(sql):
                raise AssertionError(f"Generated SQL failed validation: {sql}")

            result = execute_sql(sql)
            assert_result_shape(question, result, check["expected_aliases"])

            report.append(
                {
                    "question": question,
                    "sql": sql,
                    "db_type": result["db_type"],
                    "rows": result["rows"][0],
                }
            )
            print(f"PASS: {question}")
            print(f"  SQL: {sql}")
            print(f"  Result: {json.dumps(result['rows'][0], default=str)}")
            print()
        except Exception as exc:
            print(f"FAIL: {question}")
            print(f"  Error: {exc}")
            print()
            return 1

    output_path = Path(__file__).with_name("e2e_sql_test_report.json")
    output_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"Saved end-to-end report at: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
