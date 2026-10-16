import sqlite3

import backend_main


def setup_test_db():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE pizza_sales (
            id INTEGER PRIMARY KEY,
            order_id INTEGER,
            order_date TEXT,
            quantity INTEGER,
            unit_price REAL,
            total_price REAL,
            pizza_name TEXT,
            pizza_category TEXT,
            pizza_size TEXT,
            pizza_ingredients TEXT
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO pizza_sales (
            order_id, order_date, quantity, unit_price, total_price,
            pizza_name, pizza_category, pizza_size, pizza_ingredients
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, "2024-01-01", 2, 12.50, 25.00, "Pepperoni", "Classic", "M", "Pepperoni, cheese"),
            (2, "2024-01-02", 1, 15.00, 15.00, "Veggie", "Veg", "L", "Mushroom, onion"),
            (3, "2024-01-03", 3, 10.00, 30.00, "Pepperoni", "Classic", "M", "Pepperoni, cheese"),
            (4, "2024-01-04", 2, 18.00, 36.00, "BBQ Chicken", "Specialty", "L", "Chicken, BBQ sauce"),
        ],
    )
    conn.commit()
    return conn


def test_validate_sql_rejects_dangerous_queries():
    assert backend_main.validate_sql("SELECT SUM(total_price) AS total_revenue FROM pizza_sales") is True
    assert backend_main.validate_sql("DELETE FROM pizza_sales") is False
    assert backend_main.validate_sql("DROP TABLE pizza_sales") is False


def test_fallback_sql_questions_use_expected_aliases():
    cases = {
        "What was total revenue?": ["total_revenue"],
        "What were the total orders?": ["total_orders"],
        "How many pizzas were sold in total?": ["total_pizzas_sold"],
        "What is the average order value?": ["average_order_value"],
        "What is the average pizzas per order?": ["average_pizzas_per_order"],
    }

    for question, aliases in cases.items():
        sql = backend_main.fallback_sql_for_question(question)
        assert backend_main.validate_sql(sql) is True
        assert all(alias in sql.lower() for alias in aliases)


def test_execute_sql_against_sqlite_sample_data(monkeypatch):
    conn = setup_test_db()
    monkeypatch.setattr(backend_main, "get_db_connection", lambda: ("sqlite", conn))

    result = backend_main.execute_sql("SELECT SUM(total_price) AS total_revenue FROM pizza_sales")
    assert result["db_type"] == "sqlite"
    assert result["rows"][0]["total_revenue"] == 106.0


def test_query_graph_executes_high_confidence_sql(monkeypatch):
    result = {"db_type": "sqlite", "columns": ["total_revenue"], "rows": [{"total_revenue": 106.0}]}
    monkeypatch.setattr(
        backend_main,
        "generate_sql_with_confidence",
        lambda question: ("SELECT SUM(total_price) AS total_revenue FROM pizza_sales", 0.9, None),
    )
    monkeypatch.setattr(backend_main, "execute_sql", lambda sql: result)

    state = backend_main.query_graph.invoke({"question": "What was total revenue?"})

    assert state["response"]["status"] == "completed"
    assert state["response"]["result"] == result


def test_query_graph_persists_low_confidence_sql_for_approval(monkeypatch, tmp_path):
    checkpoint_path = tmp_path / "escalations.sqlite"
    monkeypatch.setenv("CHECKPOINT_DB", str(checkpoint_path))
    monkeypatch.setattr(
        backend_main,
        "generate_sql_with_confidence",
        lambda question: (
            "SELECT SUM(total_price) AS total_revenue FROM pizza_sales",
            0.2,
            "Confidence is below threshold.",
        ),
    )

    state = backend_main.query_graph.invoke({"question": "What was total revenue?"})

    assert state["response"]["status"] == "pending_approval"
    with sqlite3.connect(checkpoint_path) as connection:
        escalation = connection.execute(
            "SELECT status, reason FROM escalations WHERE id = ?",
            (state["response"]["escalation_id"],),
        ).fetchone()
    assert escalation == ("pending", "Confidence is below threshold.")
