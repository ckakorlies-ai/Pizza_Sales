#!/usr/bin/env python3
"""Inspect the live pizza_sales table and print schema details.

Use this to verify the real database already created and connected matches the expected project schema.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

try:
    import psycopg2
except Exception:  # pragma: no cover
    psycopg2 = None

load_dotenv(Path(__file__).with_name(".env"))


def main():
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set. Add it to .env first.")
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is not installed in this environment")

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'pizza_sales'
                ORDER BY ordinal_position
                """
            )
            rows = cursor.fetchall()

        if not rows:
            print("Table 'pizza_sales' was not found in the configured database.")
            return 1

        print("pizza_sales schema:")
        for name, data_type, nullable in rows:
            print(f"- {name}: {data_type} (nullable={nullable})")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
