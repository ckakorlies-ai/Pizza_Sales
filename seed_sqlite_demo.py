#!/usr/bin/env python3
"""Create a SQLite demo database for local pizza sales testing."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("local_dev.db")


def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pizza_sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                order_date TEXT NOT NULL,
                pizza_id TEXT,
                pizza_name TEXT,
                pizza_category TEXT,
                pizza_size TEXT,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                total_price REAL NOT NULL,
                pizza_ingredients TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        rows = [
            (1, "2024-01-01", "P1", "Pepperoni", "Classic", "M", 2, 12.50, 25.00, "Pepperoni, cheese"),
            (2, "2024-01-02", "P2", "Veggie", "Veg", "L", 1, 15.00, 15.00, "Mushroom, onion"),
            (3, "2024-01-03", "P3", "Pepperoni", "Classic", "M", 3, 10.00, 30.00, "Pepperoni, cheese"),
            (4, "2024-01-04", "P4", "BBQ Chicken", "Specialty", "L", 2, 18.00, 36.00, "Chicken, BBQ sauce"),
            (5, "2024-01-05", "P5", "Margherita", "Classic", "S", 4, 9.50, 38.00, "Tomato, basil"),
            (6, "2024-01-06", "P6", "Hawaiian", "Classic", "M", 2, 14.00, 28.00, "Ham, pineapple"),
        ]

        conn.executemany(
            """
            INSERT INTO pizza_sales (
                order_id, order_date, pizza_id, pizza_name, pizza_category,
                pizza_size, quantity, unit_price, total_price, pizza_ingredients
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        print(f"Demo database created at {DB_PATH}")
        print("Sample pizza_sales rows inserted: 6")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
