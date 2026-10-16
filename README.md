# Pizza Sales AI Analytics Agent

This project is a starter implementation for a pizza sales analytics system powered by AI. Users can ask natural-language business questions about pizza sales, the backend turns those prompts into SQL, runs them against the data, and the frontend displays KPI cards, charts, and summaries.

## Overview

The system is designed to:
- accept natural-language sales questions,
- translate them into SQL using schema-aware prompts,
- validate generated SQL before execution,
- calculate key KPI metrics,
- visualize business results in a dashboard,
- support filters for date range, category, pizza size, and product.

## Core KPI Metrics

- Total Revenue
- Total Orders
- Total Pizzas Sold
- Average Order Value
- Average Pizzas Per Order
- Category performance
- Pizza performance
- Time-based sales trends

KPI formulas:
- Total Revenue = SUM(total_price)
- Total Orders = COUNT(DISTINCT order_id)
- Total Pizzas Sold = SUM(quantity)
- Average Order Value = Total Revenue / Total Orders
- Average Pizzas Per Order = Total Pizzas Sold / Total Orders

## Local Development Stack

- Frontend: React + Vite + TypeScript
- Backend: Python + FastAPI
- Database: PostgreSQL
- AI: LLM-backed SQL generation with validation
- Local orchestration: Docker Compose

## Project Structure

The repository is organized as follows:

- backend/ - FastAPI application and analytics logic
- frontend/ - React frontend application
- data/ - raw data, schema, and import scripts
- tests/ - backend and frontend tests
- docs/ - architecture and deployment notes
- docker-compose.yml - local orchestration for Postgres, backend, frontend, and pgAdmin
- .env.example - example environment variables

## Prerequisites

- Docker Desktop or Docker Engine
- Docker Compose
- Node.js 18+
- Python 3.11+
- A valid OpenAI-compatible API key (optional for mock mode)

## Setup

1. Copy the environment file:
   ```bash
   cp .env.example .env
   ```

2. Update the values in `.env` for your environment.

3. Start all services:
   ```bash
   docker compose up --build
   ```

4. Access the app:
   - Frontend: http://localhost:5173
   - Backend API docs: http://localhost:8000/docs
   - pgAdmin: http://localhost:5050

## Example Questions

- What was total revenue last month?
- Which pizza generated the most revenue?
- What is the average order value?
- Which category sold the most pizzas?
- Compare monthly sales trends

## Dashboard API connection

The React dashboard reads KPI values from `GET /api/kpis` and submits natural-language
questions to `POST /api/query`. Set `VITE_API_URL` in the frontend environment to the
FastAPI base URL; it defaults to `http://localhost:8000`. The dashboard displays API
connection or query errors, and shows the generated SQL and returned rows after a
successful query.

## Streamlit question interface

The Streamlit UI is an alternative user interface that uses the same FastAPI routes,
so database access and SQL generation remain in the backend.

1. Install its dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
2. Start the FastAPI backend, then start Streamlit:
   ```bash
   streamlit run streamlit_app.py
   ```
3. Open the URL Streamlit prints (usually `http://localhost:8501`).

The UI uses `API_BASE_URL` for the backend and defaults to `http://localhost:8000`.
For another backend address, set `API_BASE_URL` in the Streamlit process environment.

### Admin human review

Queries whose AI-reported confidence is below `CONFIDENCE_THRESHOLD` (default `0.75`)
are held for review and are not executed. Use the **Admin** tab to inspect the
proposed SQL and approve it for execution or reject it. Cases are stored in
`CHECKPOINT_DB` (default `agent_checkpoints.sqlite`).

Admin API access uses HTTP Basic authentication with `ADMIN_USERNAME` and
`ADMIN_PASSWORD_HASH`. The password hash must use this format:
`pbkdf2_sha256$iterations$salt_hex$digest_hex`. Generate a 600,000-iteration hash
with Python, then place the printed value in `.env`:

```bash
python -c "import getpass,hashlib,secrets; p=getpass.getpass(); s=secrets.token_bytes(16); i=600000; d=hashlib.pbkdf2_hmac('sha256',p.encode(),s,i).hex(); print(f'pbkdf2_sha256${i}${s.hex()}${d}')"
```

Use HTTPS when the Streamlit app and API communicate across a network. If AI
credentials or a valid model confidence response are unavailable, the fallback
query is sent to the review queue rather than run automatically.

## Notes

- This is a starter implementation designed to match the project requirements.
- The backend should validate generated SQL before execution.
- For a real deployment, restrict DB access and use secure key management.
- Admin approval does not replace database-level read-only permissions or SQL validation.

## Next Steps

- Add the real pizza sales CSV dataset to the `data/raw` folder.
- Build the React dashboard for KPI cards and charts.
- Add strict SQL validation and rate limiting.
- Add automated tests for KPI checks, SQL generation, and escalation review.
