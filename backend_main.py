import hashlib
import json
import os
import re
import secrets
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypedDict

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

try:
    import psycopg2
except Exception:  # pragma: no cover
    psycopg2 = None

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv() -> None:
        return None

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

    if re.search(r"\bpizzas\s+(?:were\s+)?sold\b", q) or "total pizzas" in q or "quantity sold" in q:
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


try:
    CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.75"))
except ValueError as error:
    raise RuntimeError("CONFIDENCE_THRESHOLD must be a number between 0 and 1") from error
if not 0 <= CONFIDENCE_THRESHOLD <= 1:
    raise RuntimeError("CONFIDENCE_THRESHOLD must be between 0 and 1")


def adapt_sql_for_database(sql: str, db_type: str) -> str:
    if db_type == "sqlite":
        return sql.replace("DATE_TRUNC('month', order_date)", "strftime('%Y-%m-01', order_date)")
    return sql


def generate_sql_with_confidence(question: str) -> tuple[str, float, str | None]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("CHAT_MODEL", os.getenv("LLM_MODEL", "gpt-4o-mini")).strip()
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    if not api_key or OpenAI is None:
        return (
            fallback_sql_for_question(question),
            0.0,
            "AI confidence is unavailable; approve the fallback query before it runs.",
        )

    try:
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
- Return a JSON object with exactly two keys: "sql" (the read-only SQL query)
  and "confidence" (a number from 0 to 1). Estimate confidence in the query's
  semantic correctness; use a low score for ambiguous or unsupported requests.
- Return only JSON, with no markdown fences or explanation.

Question: {question}
""".strip()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=400,
        )
        content = response.choices[0].message.content or ""
        generated = json.loads(content)
        if (
            not isinstance(generated, dict)
            or set(generated) != {"sql", "confidence"}
            or not isinstance(generated["sql"], str)
            or isinstance(generated["confidence"], bool)
            or not isinstance(generated["confidence"], (int, float))
        ):
            raise ValueError("Model response must include SQL and a numeric confidence")
        sql = clean_sql_response(generated["sql"])
        confidence = float(generated["confidence"])
        if not 0 <= confidence <= 1:
            raise ValueError("Model confidence must be between 0 and 1")
        if not validate_sql(sql):
            raise ValueError("Generated SQL failed validation")
        return sql, confidence, None
    except Exception:
        return (
            fallback_sql_for_question(question),
            0.0,
            "AI query generation or confidence validation failed; approve the fallback query before it runs.",
        )


def generate_sql_for_question(question: str) -> str:
    sql, _, _ = generate_sql_with_confidence(question)
    return sql


def get_db_connection():
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is not installed, cannot connect to PostgreSQL")
        return "postgresql", psycopg2.connect(database_url)

    sqlite_path = os.getenv("SQLITE_DB_PATH", str(Path(__file__).with_name("local_dev.db")))
    sqlite_path = Path(sqlite_path)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return "sqlite", __import__("sqlite3").connect(str(sqlite_path))


def execute_sql(sql: str):
    db_type, conn = get_db_connection()
    query = adapt_sql_for_database(sql, db_type)
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        payload = [dict(zip(columns, row)) for row in rows]
        return {"db_type": db_type, "columns": columns, "rows": payload}
    finally:
        conn.close()


class QueryRequest(BaseModel):
    question: str


class EscalationDecision(BaseModel):
    decision: Literal["approve", "reject"]


class QueryState(TypedDict, total=False):
    question: str
    sql: str
    confidence: float
    escalation_reason: str | None
    response: dict[str, object]


app = FastAPI(title="Pizza Sales AI Analytics Agent")
admin_security = HTTPBasic(auto_error=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def escalation_connection() -> sqlite3.Connection:
    configured_path = os.getenv("CHECKPOINT_DB", "agent_checkpoints.sqlite")
    database_path = Path(configured_path)
    if not database_path.is_absolute():
        database_path = Path(__file__).parent / database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_path), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS escalations (
            id TEXT PRIMARY KEY,
            question TEXT NOT NULL,
            sql TEXT NOT NULL,
            confidence REAL NOT NULL,
            status TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            result_json TEXT
        )
        """
    )
    connection.commit()
    return connection


def parse_admin_password_hash(encoded_hash: str) -> tuple[int, bytes, bytes] | None:
    try:
        algorithm, iteration_text, salt_text, digest_text = encoded_hash.split("$", 3)
        iterations = int(iteration_text)
        salt = bytes.fromhex(salt_text)
        digest = bytes.fromhex(digest_text)
    except (ValueError, TypeError):
        return None
    if (
        algorithm != "pbkdf2_sha256"
        or not 100_000 <= iterations <= 2_000_000
        or len(salt) < 16
        or len(digest) != 32
    ):
        return None
    return iterations, salt, digest


def require_admin(
    credentials: HTTPBasicCredentials | None = Depends(admin_security),
) -> None:
    configured_username = os.getenv("ADMIN_USERNAME", "")
    encoded_hash = os.getenv("ADMIN_PASSWORD_HASH", "")
    parsed_hash = parse_admin_password_hash(encoded_hash)
    if not configured_username or parsed_hash is None:
        raise HTTPException(
            status_code=503,
            detail="Admin access is not configured with a PBKDF2-SHA256 password hash.",
        )
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Admin authentication required.",
            headers={"WWW-Authenticate": "Basic"},
        )

    iterations, salt, expected_digest = parsed_hash
    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        credentials.password.encode("utf-8"),
        salt,
        iterations,
    )
    if not (
        secrets.compare_digest(credentials.username, configured_username)
        and secrets.compare_digest(actual_digest, expected_digest)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid admin credentials.",
            headers={"WWW-Authenticate": "Basic"},
        )


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"message": "Pizza Sales AI Analytics Agent is running"}


@app.get("/api/kpis")
def get_kpis():
    lookup = {
        "total_revenue": "SELECT COALESCE(SUM(total_price), 0) AS total_revenue FROM pizza_sales",
        "total_orders": "SELECT COUNT(DISTINCT order_id) AS total_orders FROM pizza_sales",
        "total_pizzas_sold": "SELECT COALESCE(SUM(quantity), 0) AS total_pizzas_sold FROM pizza_sales",
        "average_order_value": (
            "SELECT COALESCE(SUM(total_price), 0) / NULLIF(COUNT(DISTINCT order_id), 0) "
            "AS average_order_value FROM pizza_sales"
        ),
        "average_pizzas_per_order": (
            "SELECT COALESCE(SUM(quantity), 0) / NULLIF(COUNT(DISTINCT order_id), 0) "
            "AS average_pizzas_per_order FROM pizza_sales"
        ),
    }

    metrics = {}
    for key, sql in lookup.items():
        result = execute_sql(sql)
        row = result["rows"][0] if result["rows"] else {key: 0}
        metrics[key] = row.get(key, 0)

    metrics["top_pizzas"] = []
    metrics["category_revenue"] = []
    return metrics


def generate_query_node(state: QueryState) -> dict[str, object]:
    sql, confidence, escalation_reason = generate_sql_with_confidence(state["question"])
    return {
        "sql": sql,
        "confidence": confidence,
        "escalation_reason": escalation_reason,
    }


def validate_query_node(state: QueryState) -> dict[str, object]:
    if not validate_sql(state["sql"]):
        raise HTTPException(status_code=400, detail="Generated SQL failed validation")
    return {}


def route_query(state: QueryState) -> Literal["escalate", "execute"]:
    return "escalate" if state["confidence"] < CONFIDENCE_THRESHOLD else "execute"


def create_escalation_node(state: QueryState) -> dict[str, object]:
    escalation_id = uuid.uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat()
    with closing(escalation_connection()) as connection, connection:
        connection.execute(
            """
            INSERT INTO escalations
                (id, question, sql, confidence, status, reason, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                escalation_id,
                state["question"],
                state["sql"],
                state["confidence"],
                state.get("escalation_reason"),
                created_at,
            ),
        )
    return {
        "response": {
            "status": "pending_approval",
            "escalation_id": escalation_id,
            "question": state["question"],
            "sql": state["sql"],
            "confidence": state["confidence"],
            "summary": "This query requires admin approval before execution.",
        }
    }


def execute_query_node(state: QueryState) -> dict[str, object]:
    result = execute_sql(state["sql"])
    row = result["rows"][0] if result["rows"] else {}
    return {
        "response": {
            "status": "completed",
            "question": state["question"],
            "sql": state["sql"],
            "confidence": state["confidence"],
            "summary": "Query executed successfully." if row else "No rows returned for this query.",
            "result": result,
        }
    }


def build_query_graph():
    workflow = StateGraph(QueryState)
    workflow.add_node("generate_sql", generate_query_node)
    workflow.add_node("validate_sql", validate_query_node)
    workflow.add_node("create_escalation", create_escalation_node)
    workflow.add_node("execute_query", execute_query_node)
    workflow.add_edge(START, "generate_sql")
    workflow.add_edge("generate_sql", "validate_sql")
    workflow.add_conditional_edges(
        "validate_sql",
        route_query,
        {"escalate": "create_escalation", "execute": "execute_query"},
    )
    workflow.add_edge("create_escalation", END)
    workflow.add_edge("execute_query", END)
    return workflow.compile()


query_graph = build_query_graph()


@app.post("/api/query")
def ask_question(payload: QueryRequest):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    return query_graph.invoke({"question": question})["response"]


@app.get("/api/admin/escalations")
def list_escalations(
    status: str = Query(default="pending"),
    _: None = Depends(require_admin),
):
    if status not in {"pending", "approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Status must be pending, approved, or rejected.")
    with closing(escalation_connection()) as connection, connection:
        rows = connection.execute(
            """
            SELECT id, question, sql, confidence, status, reason, created_at,
                   reviewed_at, result_json
            FROM escalations
            WHERE status = ?
            ORDER BY created_at DESC
            """,
            (status,),
        ).fetchall()
    return [
        {
            **{key: row[key] for key in row.keys() if key != "result_json"},
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
        }
        for row in rows
    ]


@app.post("/api/admin/escalations/{escalation_id}/decision")
def decide_escalation(
    escalation_id: str,
    payload: EscalationDecision,
    _: None = Depends(require_admin),
):
    with closing(escalation_connection()) as connection, connection:
        escalation = connection.execute(
            """
            SELECT question, sql, status
            FROM escalations
            WHERE id = ?
            """,
            (escalation_id,),
        ).fetchone()
    if escalation is None:
        raise HTTPException(status_code=404, detail="Escalation case not found.")
    if escalation["status"] != "pending":
        raise HTTPException(status_code=409, detail="Escalation case has already been reviewed.")

    result = None
    if payload.decision == "approve":
        sql = escalation["sql"]
        if not validate_sql(sql):
            raise HTTPException(status_code=400, detail="Escalated SQL failed validation.")
        result = execute_sql(sql)

    reviewed_at = datetime.now(timezone.utc).isoformat()
    status = "approved" if payload.decision == "approve" else "rejected"
    result_json = json.dumps(jsonable_encoder(result)) if result is not None else None
    with closing(escalation_connection()) as connection, connection:
        updated = connection.execute(
            """
            UPDATE escalations
            SET status = ?, reviewed_at = ?, result_json = ?
            WHERE id = ? AND status = 'pending'
            """,
            (status, reviewed_at, result_json, escalation_id),
        )
        if updated.rowcount != 1:
            raise HTTPException(status_code=409, detail="Escalation case has already been reviewed.")

    return {
        "id": escalation_id,
        "status": status,
        "question": escalation["question"],
        "result": result,
    }
