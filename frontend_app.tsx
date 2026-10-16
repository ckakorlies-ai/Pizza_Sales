import { FormEvent, useCallback, useEffect, useState } from "react";

type Kpis = {
  total_revenue: number | string | null;
  total_orders: number | string | null;
  total_pizzas_sold: number | string | null;
  average_order_value: number | string | null;
  average_pizzas_per_order: number | string | null;
};

type QueryResult = {
  db_type: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
};

type QueryResponse = {
  question: string;
  sql: string;
  summary: string;
  result: QueryResult;
};

const API_BASE_URL = (
  import.meta as ImportMeta & { env?: { VITE_API_URL?: string } }
).env?.VITE_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

const SUGGESTED_QUESTIONS = [
  "What was total revenue?",
  "Which pizza generated the most revenue?",
  "Which category generated the most revenue?",
  "What is the average order value?",
];

const KPI_DEFINITIONS: Array<{
  key: keyof Kpis;
  label: string;
  description: string;
  format: (value: Kpis[keyof Kpis]) => string;
}> = [
  {
    key: "total_revenue",
    label: "Total revenue",
    description: "Sales across all orders",
    format: (value) => formatCurrency(value),
  },
  {
    key: "total_orders",
    label: "Total orders",
    description: "Distinct customer orders",
    format: (value) => formatCount(value),
  },
  {
    key: "total_pizzas_sold",
    label: "Pizzas sold",
    description: "Total units sold",
    format: (value) => formatCount(value),
  },
  {
    key: "average_order_value",
    label: "Average order value",
    description: "Revenue per order",
    format: (value) => formatCurrency(value),
  },
  {
    key: "average_pizzas_per_order",
    label: "Pizzas per order",
    description: "Average units per order",
    format: (value) => formatDecimal(value),
  },
];

function numericValue(value: unknown): number {
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function formatCurrency(value: unknown): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(numericValue(value));
}

function formatCount(value: unknown): string {
  return new Intl.NumberFormat().format(numericValue(value));
}

function formatDecimal(value: unknown): string {
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 2,
  }).format(numericValue(value));
}

async function readApiError(response: Response): Promise<string> {
  const body = (await response.json().catch(() => null)) as
    | { detail?: unknown; message?: unknown }
    | null;
  if (typeof body?.detail === "string") return body.detail;
  if (typeof body?.message === "string") return body.message;
  return `Request failed (${response.status} ${response.statusText})`;
}

async function fetchKpis(): Promise<Kpis> {
  const response = await fetch(`${API_BASE_URL}/api/kpis`);
  if (!response.ok) throw new Error(await readApiError(response));
  return (await response.json()) as Kpis;
}

export default function App() {
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [kpiLoading, setKpiLoading] = useState(true);
  const [kpiError, setKpiError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [queryLoading, setQueryLoading] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [queryResponse, setQueryResponse] = useState<QueryResponse | null>(null);

  const loadKpis = useCallback(async () => {
    setKpiLoading(true);
    setKpiError(null);
    try {
      setKpis(await fetchKpis());
    } catch (error) {
      setKpiError(
        error instanceof Error ? error.message : "Could not load dashboard metrics.",
      );
    } finally {
      setKpiLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadKpis();
  }, [loadKpis]);

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submittedQuestion = question.trim();
    if (!submittedQuestion || queryLoading) return;

    setQueryLoading(true);
    setQueryError(null);
    setQueryResponse(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: submittedQuestion }),
      });
      if (!response.ok) throw new Error(await readApiError(response));
      setQueryResponse((await response.json()) as QueryResponse);
    } catch (error) {
      setQueryError(
        error instanceof Error ? error.message : "The question could not be processed.",
      );
    } finally {
      setQueryLoading(false);
    }
  }

  return (
    <main className="dashboard">
      <style>{styles}</style>
      <header className="topbar">
        <a className="brand" href="/" aria-label="Pizza Sales Analytics home">
          <span className="brand-mark" aria-hidden="true">
            P
          </span>
          <span>Slice<span className="brand-light">wise</span></span>
        </a>
        <div className="topbar-right">
          <span className="live-indicator"><i /> Sales analytics</span>
          <button
            className="refresh-button"
            type="button"
            onClick={() => void loadKpis()}
            disabled={kpiLoading}
          >
            <span aria-hidden="true">↻</span> Refresh
          </button>
        </div>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">YOUR BUSINESS AT A GLANCE</p>
          <h1>Pizza sales, <span>made clear.</span></h1>
          <p className="hero-subtitle">
            Track performance and ask questions about your sales in plain language.
          </p>
        </div>
        <div className="hero-art" aria-hidden="true">
          <span className="hero-circle">✦</span>
          <span className="hero-pizza">🍕</span>
          <span className="hero-spark spark-one">✳</span>
          <span className="hero-spark spark-two">·</span>
        </div>
      </section>

      <section className="metrics-section" aria-labelledby="metrics-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">PERFORMANCE SNAPSHOT</p>
            <h2 id="metrics-heading">Key metrics</h2>
          </div>
          <span className="data-caption">All available sales data</span>
        </div>

        {kpiError && (
          <div className="notice error-notice" role="alert">
            <strong>Couldn’t load sales metrics.</strong> {kpiError}
            <span> Check that the API and database are available.</span>
          </div>
        )}

        <div className="metrics-grid">
          {KPI_DEFINITIONS.map((metric, index) => (
            <article className={`metric-card metric-${index}`} key={metric.key}>
              <div className="metric-top">
                <span className="metric-label">{metric.label}</span>
                <span className="metric-icon" aria-hidden="true">
                  {["$", "↗", "▧", "◉", "⌁"][index]}
                </span>
              </div>
              <div className="metric-value" aria-live="polite">
                {kpiLoading
                  ? <span className="skeleton" aria-label="Loading" />
                  : kpis
                    ? metric.format(kpis[metric.key])
                    : "—"}
              </div>
              <p className="metric-description">{metric.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="ask-section" aria-labelledby="ask-heading">
        <div className="section-heading ask-heading">
          <div>
            <p className="eyebrow">ASK YOUR DATA</p>
            <h2 id="ask-heading">What would you like to know?</h2>
          </div>
          <span className="ai-badge"><span>✦</span> AI-powered</span>
        </div>

        <form className="question-form" onSubmit={submitQuestion}>
          <label className="sr-only" htmlFor="sales-question">Ask a sales question</label>
          <span className="question-icon" aria-hidden="true">⌕</span>
          <input
            id="sales-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="e.g. Which pizza sold the most last month?"
            maxLength={1000}
          />
          <button type="submit" disabled={queryLoading || !question.trim()}>
            {queryLoading ? "Thinking…" : "Ask"}
            {!queryLoading && <span aria-hidden="true">→</span>}
          </button>
        </form>

        <div className="suggestions" aria-label="Suggested questions">
          <span>Try asking</span>
          {SUGGESTED_QUESTIONS.map((suggestion) => (
            <button
              type="button"
              key={suggestion}
              onClick={() => setQuestion(suggestion)}
            >
              {suggestion}
            </button>
          ))}
        </div>

        {queryError && (
          <div className="notice error-notice query-notice" role="alert">
            <strong>That question couldn’t be answered.</strong> {queryError}
          </div>
        )}

        {queryResponse && (
          <article className="answer-card" aria-live="polite">
            <div className="answer-heading">
              <div>
                <p className="eyebrow">ANSWER</p>
                <h3>{queryResponse.question}</h3>
              </div>
              <span className="db-badge">{queryResponse.result.db_type}</span>
            </div>
            <p className="answer-summary">{queryResponse.summary}</p>

            {queryResponse.result.rows.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      {queryResponse.result.columns.map((column) => (
                        <th scope="col" key={column}>{column.replaceAll("_", " ")}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {queryResponse.result.rows.map((row, rowIndex) => (
                      <tr key={rowIndex}>
                        {queryResponse.result.columns.map((column) => (
                          <td key={column}>{formatCell(row[column])}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="empty-result">The query returned no rows.</p>
            )}

            <details className="sql-details">
              <summary>View generated SQL</summary>
              <pre><code>{queryResponse.sql}</code></pre>
            </details>
          </article>
        )}
      </section>

      <footer className="footer">
        <span>Slice<span className="brand-light">wise</span> · Pizza sales analytics</span>
        <span>Metrics reflect the data currently available in your database.</span>
      </footer>
    </main>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

const styles = `
  :root { font-family: Arial, sans-serif; color: #20251f; background: #f7f8f5; font-synthesis: none; }
  * { box-sizing: border-box; }
  body { margin: 0; min-width: 320px; }
  button, input { font: inherit; }
  button { cursor: pointer; }
  .dashboard { max-width: 1240px; min-height: 100vh; margin: auto; padding: 0 56px; }
  .topbar { height: 82px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e9ebe5; }
  .brand { display: inline-flex; align-items: center; gap: 10px; color: #212820; font-family: Arial, sans-serif; font-size: 20px; font-weight: 800; text-decoration: none; letter-spacing: -1px; }
  .brand-mark { display: grid; place-items: center; width: 32px; height: 32px; border-radius: 11px; background: #ee6541; color: white; font-size: 18px; letter-spacing: 0; }
  .brand-light { color: #ed6848; }
  .topbar-right { display: flex; align-items: center; gap: 22px; }
  .live-indicator { display: flex; align-items: center; gap: 8px; color: #5e665d; font-size: 13px; }
  .live-indicator i { width: 8px; height: 8px; border-radius: 50%; background: #63a779; box-shadow: 0 0 0 3px #e2f0e5; }
  .refresh-button { border: 1px solid #e1e5dc; border-radius: 9px; padding: 9px 13px; color: #444d43; background: white; font-size: 13px; font-weight: 600; }
  .refresh-button:hover:not(:disabled) { background: #f1f4ed; }
  .refresh-button:disabled { opacity: .6; cursor: wait; }
  .hero { position: relative; display: flex; align-items: center; min-height: 230px; overflow: hidden; margin-top: 30px; padding: 32px 42px; border-radius: 18px; background: #f4e9d8; }
  .hero-copy { position: relative; z-index: 1; max-width: 650px; }
  .eyebrow { margin: 0 0 9px; color: #8b7961; font-size: 10px; font-weight: 700; letter-spacing: 1.45px; }
  h1, h2, h3, p { margin-top: 0; }
  h1 { margin-bottom: 11px; color: #262b22; font-family: Arial, sans-serif; font-size: clamp(30px, 4vw, 43px); font-weight: 800; letter-spacing: -2px; line-height: 1.14; }
  h1 span { color: #e36743; }
  .hero-subtitle { max-width: 450px; margin-bottom: 0; color: #6d6b5e; font-size: 15px; line-height: 1.6; }
  .hero-art { position: absolute; right: 67px; top: 50%; width: 154px; height: 154px; transform: translateY(-50%); }
  .hero-circle { position: absolute; inset: 4px; display: grid; place-items: center; border: 1px dashed #dbb993; border-radius: 50%; color: #e38b58; font-size: 18px; }
  .hero-pizza { position: absolute; inset: 0; display: grid; place-items: center; font-size: 76px; transform: rotate(-10deg); filter: drop-shadow(0 10px 8px #b98b6340); }
  .hero-spark { position: absolute; color: #e07850; font-size: 26px; }
  .spark-one { right: -9px; top: 9px; }
  .spark-two { left: -14px; bottom: 15px; font-size: 40px; }
  .metrics-section, .ask-section { margin-top: 39px; }
  .section-heading { display: flex; align-items: end; justify-content: space-between; margin-bottom: 17px; }
  .section-heading .eyebrow { margin-bottom: 6px; }
  h2 { margin-bottom: 0; font-family: Arial, sans-serif; font-size: 22px; letter-spacing: -.6px; }
  .data-caption { padding-bottom: 3px; color: #82887d; font-size: 12px; }
  .metrics-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 13px; }
  .metric-card { min-height: 140px; padding: 17px 17px 15px; border: 1px solid #eaede6; border-radius: 13px; background: #fff; box-shadow: 0 3px 12px #28341b06; }
  .metric-top { display: flex; align-items: center; justify-content: space-between; gap: 4px; }
  .metric-label { color: #71796e; font-size: 12px; font-weight: 600; }
  .metric-icon { display: grid; place-items: center; width: 27px; height: 27px; border-radius: 8px; background: #fff0e9; color: #e86e49; font-size: 15px; font-weight: 700; }
  .metric-1 .metric-icon { color: #688a63; background: #eaf2e7; }
  .metric-2 .metric-icon { color: #c48a37; background: #f8f0df; }
  .metric-3 .metric-icon { color: #7c74a1; background: #efedf8; }
  .metric-4 .metric-icon { color: #498c8a; background: #e6f2f0; }
  .metric-value { min-height: 40px; margin-top: 11px; color: #252b23; font-family: Arial, sans-serif; font-size: clamp(21px, 2.4vw, 29px); font-weight: 800; letter-spacing: -1px; white-space: nowrap; }
  .metric-description { margin: 4px 0 0; color: #999e95; font-size: 11px; }
  .skeleton { display: inline-block; width: 82%; height: 27px; border-radius: 6px; background: linear-gradient(90deg, #f0f1ed 25%, #f8f8f6 50%, #f0f1ed 75%); background-size: 200% 100%; animation: shimmer 1.3s infinite; }
  @keyframes shimmer { to { background-position: -200% 0; } }
  .ask-section { margin-top: 42px; }
  .ask-heading { align-items: center; }
  .ai-badge { display: inline-flex; align-items: center; gap: 6px; padding: 7px 10px; border: 1px solid #f2dfd5; border-radius: 20px; color: #b96043; background: #fff8f4; font-size: 11px; font-weight: 700; }
  .ai-badge span { font-size: 12px; }
  .question-form { display: flex; align-items: center; gap: 12px; min-height: 62px; padding: 8px 9px 8px 17px; border: 1px solid #e7eae3; border-radius: 13px; background: white; box-shadow: 0 5px 18px #28341b08; }
  .question-icon { color: #899083; font-size: 28px; line-height: 1; transform: rotate(-20deg); }
  .question-form input { flex: 1; min-width: 0; border: 0; outline: 0; color: #333a31; background: transparent; font-size: 14px; }
  .question-form input::placeholder { color: #a4a99f; }
  .question-form:focus-within { border-color: #df947a; box-shadow: 0 0 0 3px #ed79501a; }
  .question-form button { display: inline-flex; align-items: center; justify-content: center; gap: 16px; min-width: 92px; padding: 12px 16px; border: 0; border-radius: 9px; color: white; background: #e96b48; font-size: 13px; font-weight: 700; transition: background .15s ease; }
  .question-form button:hover:not(:disabled) { background: #d95837; }
  .question-form button:disabled { opacity: .55; cursor: not-allowed; }
  .suggestions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 13px; }
  .suggestions > span { margin-right: 3px; color: #8d9389; font-size: 11px; }
  .suggestions button { padding: 7px 10px; border: 1px solid #e8ebe5; border-radius: 20px; color: #656d61; background: #fff; font-size: 11px; }
  .suggestions button:hover { border-color: #e6ae9b; color: #b85c41; background: #fffaf7; }
  .notice { margin: 15px 0; padding: 12px 14px; border-radius: 9px; font-size: 13px; line-height: 1.5; }
  .error-notice { border: 1px solid #f2d4ce; color: #8b4033; background: #fff5f3; }
  .query-notice { margin-top: 19px; }
  .answer-card { margin-top: 22px; padding: 21px; border: 1px solid #e8ebe4; border-radius: 14px; background: white; box-shadow: 0 5px 18px #28341b08; }
  .answer-heading { display: flex; justify-content: space-between; align-items: start; gap: 16px; }
  .answer-heading .eyebrow { color: #df714f; }
  h3 { margin-bottom: 0; font-family: Arial, sans-serif; font-size: 17px; line-height: 1.4; }
  .db-badge { padding: 5px 9px; border-radius: 14px; color: #547c59; background: #edf5ec; font-size: 10px; font-weight: 700; text-transform: uppercase; }
  .answer-summary { margin: 11px 0 15px; color: #687064; font-size: 13px; }
  .table-wrap { overflow-x: auto; border: 1px solid #edf0e9; border-radius: 9px; }
  table { width: 100%; border-collapse: collapse; text-align: left; }
  th, td { padding: 11px 13px; border-bottom: 1px solid #edf0e9; font-size: 12px; white-space: nowrap; }
  th { color: #747d70; background: #f8f9f6; font-size: 10px; font-weight: 700; text-transform: capitalize; }
  td { color: #353d33; }
  tbody tr:last-child td { border-bottom: 0; }
  .empty-result { color: #82887d; font-size: 13px; }
  .sql-details { margin-top: 15px; color: #737b70; font-size: 12px; }
  .sql-details summary { width: fit-content; cursor: pointer; font-weight: 600; }
  .sql-details pre { overflow-x: auto; margin: 10px 0 0; padding: 13px; border-radius: 8px; color: #e5ebdf; background: #263128; font-size: 12px; line-height: 1.6; white-space: pre-wrap; }
  .footer { display: flex; justify-content: space-between; gap: 16px; margin-top: 50px; padding: 19px 0 25px; border-top: 1px solid #e9ebe5; color: #92978e; font-size: 11px; }
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
  @media (max-width: 900px) {
    .dashboard { padding: 0 28px; }
    .metrics-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .hero-art { right: 35px; opacity: .8; }
  }
  @media (max-width: 600px) {
    .dashboard { padding: 0 18px; }
    .topbar { height: 68px; }
    .topbar-right { gap: 11px; }
    .live-indicator { font-size: 11px; }
    .refresh-button { padding: 8px 9px; font-size: 11px; }
    .hero { min-height: 205px; margin-top: 20px; padding: 26px 22px; }
    .hero-art { right: -27px; opacity: .24; }
    .hero-copy { max-width: 100%; }
    .hero-subtitle { max-width: 310px; font-size: 13px; }
    .metrics-section, .ask-section { margin-top: 31px; }
    .metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .metric-card { min-height: 128px; padding: 14px; }
    .metric-label { font-size: 11px; }
    .metric-value { font-size: 23px; }
    .section-heading { align-items: start; }
    .data-caption { max-width: 95px; text-align: right; font-size: 10px; }
    .suggestions { gap: 7px; }
    .suggestions > span { width: 100%; }
    .suggestions button { font-size: 10px; }
    .question-form { gap: 8px; padding-left: 11px; }
    .question-form input { font-size: 12px; }
    .question-form button { min-width: auto; gap: 8px; padding: 11px 12px; }
    .footer { flex-direction: column; margin-top: 36px; }
  }
`;
