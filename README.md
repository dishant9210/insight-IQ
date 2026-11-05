<div align="center">
  <img src="https://cdn-icons-png.flaticon.com/512/2103/2103633.png" alt="InsightIQ Logo" width="120">
  <h1>InsightIQ</h1>
  <p><b>Talk to your data. Get instant answers.</b></p>
  <p><a href="https://insightiq-web.fly.dev"><b>Live demo</b></a> · <a href="https://insightiq-api.fly.dev/health">API</a></p>

  [![CI](https://github.com/dishant9210/insight-IQ/actions/workflows/ci.yml/badge.svg)](https://github.com/dishant9210/insight-IQ/actions/workflows/ci.yml)

  ![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
  ![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
  ![DuckDB](https://img.shields.io/badge/DuckDB-FFF000?style=for-the-badge&logo=duckdb&logoColor=black)
  ![Groq](https://img.shields.io/badge/Groq-f55036?style=for-the-badge)
  ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)
  ![Redis](https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white)
  ![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)

  <p>
    <a href="#-key-features">Features</a> •
    <a href="#-getting-started">Installation</a> •
    <a href="#-how-it-works">How it works</a> •
    <a href="#-security">Security</a> •
    <a href="#-tech-stack">Stack</a>
  </p>
</div>

---

## 📖 About InsightIQ
InsightIQ is a conversational analytics tool. Upload a CSV, Excel, JSON or Parquet file and ask questions about it in plain English — no SQL needed.

Under the hood, an open-weight model on **Groq** (GPT-OSS 120B by default) turns the question into a DuckDB query, **DuckDB** runs it against your file, and the model writes a short insight on the result. The generated SQL is always shown, so you can check what was actually asked.

---

## 🚀 Key Features

### 🧠 **Conversational Intelligence**
Ask questions like *"Who are my top 10 customers by revenue?"* or *"Show me the monthly trend of sales"* and get back a result table, a two-sentence insight, and the SQL that produced it.

### 📂 **Any tabular file**
CSV, Excel (`.xlsx`/`.xls`), JSON and Parquet. Column names are normalised, dates are detected, nested JSON is flattened one level, and non-UTF-8 CSVs fall back to latin-1 — with a warning so you know what happened.

### 📑 **Multi-sheet workbooks**
Every non-empty sheet in an Excel file becomes its own table (`Customer List` → `customer_list`), and the model sees all of them, so a question like *"revenue by customer city"* can JOIN the orders sheet to the customers sheet. `data` always points at the first sheet; empty sheets are skipped with a warning.

### ⚡ **Fast**
Groq inference plus DuckDB's columnar engine means most questions come back in a second or two, even on a few hundred thousand rows.

### 🧭 **Learns from past answers (RAG)**
Every answered question is embedded and stored. When a new question comes in, the closest past questions **on data with the same columns** are retrieved (pgvector, cosine distance) and put in the prompt as worked examples. Thumbs-up / thumbs-down on each answer decides what stays in that pool. You can also write a short note per column (*"discount — fraction off list price, 0–1"*) and the model sees it next to the schema. Workbooks with many sheets only send the sheets closest to the question.

### ♻️ **Cached and rate-limited**
Asking the same question about the same file again returns the stored answer with no model call (and a *Cached* badge in the UI). Each client gets a per-minute and per-day budget of questions and uploads, so one visitor can't burn through the Groq quota.

### 🔒 **Safe by construction**
LLM output is treated as untrusted input. See [Security](#-security).

---

## 🔁 How it works

```
             ┌──────────┐  202 + dataset_id   ┌──────────┐
 upload ───▶ │   api    │ ──── enqueue ─────▶ │  Redis   │
             └────┬─────┘                     └────┬─────┘
                  │ poll status                    ▼
                  │                          ┌──────────┐  loader (csv / excel / json / parquet)
                  │                          │  worker  │ ─▶ one .duckdb file per dataset
                  ▼                          └────┬─────┘
             ┌──────────┐ ◀── status, schema ─────┘
             │ Postgres │      datasets + query_log
             └──────────┘

 question ──▶ rate limit ──▶ answer cache ──hit──▶ result
                               │ miss
                               ▼
     embed question ──▶ pgvector: similar past Q→SQL (same schema, not 👎)
                    └─▶ closest tables (big workbooks) + column notes
                               ▼
              api ──▶ schema + notes + examples ──▶ LLM (Groq) ──▶ SQL ──▶ guard ──▶ DuckDB (read-only) ──▶ result
                                                                                              │
                                                                               LLM (Groq) ──▶ insight
```

| Service | Role |
| :--- | :--- |
| **api** | FastAPI. Accepts uploads, answers questions, serves dataset status. Runs migrations on start. |
| **worker** | Same image, `python -m app.worker`. Parses uploads off the request path, so a big workbook never holds a request open. |
| **Postgres + pgvector** | Dataset metadata, status and column notes, plus a log of every question with its SQL, outcome, latency, feedback and embedding (HNSW index for nearest-neighbour search). |
| **Redis** | The ingest queue ([RQ](https://python-rq.org)), the answer cache and the rate-limit counters — shared by every api replica. |
| **frontend** | React build behind nginx. |

Without `REDIS_URL` the api parses uploads itself and keeps the cache and rate-limit counters in memory, and without `DATABASE_URL` it uses a SQLite file, so a single container still runs the whole app.

1. **Upload** — the file is streamed to disk (size-capped) and the api answers `202` straight away. The worker parses it with the matching loader and writes it into its own DuckDB database; the dataset row in Postgres goes `pending → processing → ready` (or `failed` with the reason). The frontend polls until it's ready.
2. **Retrieve** — the question is embedded; past questions with the same table/column layout that ran fine and weren't thumbed down are pulled in as examples if they're close enough. Re-uploading the same spreadsheet next month reuses everything learned on the last one.
3. **Query** — the schema (with any column notes), a few sample rows and the examples go to the model with the question. The returned SQL is cleaned and validated, then run with a row limit and a timeout.
4. **Insight** — the first few result rows go back to the model for a short written summary. If the query returned nothing, this step is skipped.
5. **Cache** — the answer is stored under the dataset id and the normalised question (case, spacing and a trailing `?` don't matter) for `ANSWER_CACHE_TTL_SECONDS`. Datasets never change after upload, so a cached answer can't go stale. Failed questions aren't cached, a thumbs-down evicts the answer, and editing the column notes changes the key.

---

## 🔒 Security

The SQL that runs comes from a language model, and a user can try to steer it. So the query never gets to decide what it's allowed to do:

| Layer | What it does |
| :--- | :--- |
| **Parser check** | `duckdb.extract_statements` must return exactly one statement, and it must be a `SELECT`. CTEs are fine; `COPY`, `PRAGMA`, `ATTACH`, multi-statement strings are not. |
| **Keyword check** | A second, cheaper filter for `INSERT` / `DROP` / `COPY` / `LOAD` etc. Belt and braces. |
| **Read-only connection** | Each query opens the dataset's `.duckdb` file with `read_only=True`. |
| **No external access** | `SET enable_external_access = false` — so `SELECT * FROM read_csv_auto('/etc/passwd')` is a permission error, not a data leak. `lock_configuration = true` stops the query flipping it back. |
| **Limits** | Results are capped (`MAX_RESULT_ROWS`), queries are interrupted after `QUERY_TIMEOUT_SECONDS`, uploads are rejected above `MAX_UPLOAD_MB`. |
| **Rate limits** | Fixed windows per client IP (`RATE_LIMIT_QUERY`, `RATE_LIMIT_UPLOAD`). Over the limit is a `429` with `Retry-After`; every response carries `X-RateLimit-Limit` / `-Remaining` / `-Reset`. If Redis is unreachable the limiter fails open rather than taking the api down. |

---

## 🛠 Tech Stack

| Layer | Technology |
| :--- | :--- |
| **Frontend** | React 19, Vite, Tailwind CSS |
| **Backend** | FastAPI, Pydantic, LangChain, SQLAlchemy, Alembic |
| **Data** | PostgreSQL + pgvector (metadata, query log, embeddings), DuckDB (queries), pandas, pyarrow |
| **Queue / cache** | Redis — RQ worker, answer cache, rate limits |
| **AI/LLM** | Groq (GPT-OSS 120B by default, any Groq model via `GROQ_MODEL`), fastembed (bge-small-en-v1.5) for retrieval |
| **Infrastructure** | Docker, Docker Compose, GitHub Actions, Fly.io |

---

## 🚦 Getting Started

### 1. Clone the repo
```bash
git clone https://github.com/dishant9210/insight-IQ.git
cd insight-IQ
```

### 2. Set up environment variables
Copy the examples and add your Groq key (free at [console.groq.com](https://console.groq.com)):

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

| Variable | Default | Notes |
| :--- | :--- | :--- |
| `GROQ_API_KEY` | — | required |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | any model your Groq key can use |
| `ALLOWED_ORIGINS` | `http://localhost:5173,...` | comma separated |
| `UPLOAD_DIR` | `uploads` | DuckDB files live here |
| `DATABASE_URL` | SQLite in `UPLOAD_DIR` | `postgresql://...` in compose |
| `REDIS_URL` | — | set it to parse uploads on the worker |
| `MAX_UPLOAD_MB` | `50` | |
| `MAX_RESULT_ROWS` | `1000` | |
| `QUERY_TIMEOUT_SECONDS` | `20` | |
| `ANSWER_CACHE_TTL_SECONDS` | `3600` | `0` turns the cache off |
| `RATE_LIMIT_QUERY` | `20/minute,200/day` | per client; `second` / `minute` / `hour` / `day`, empty = off |
| `RATE_LIMIT_UPLOAD` | `10/minute,100/day` | |
| `EMBEDDER` | `hash` | `fastembed` (bge-small, ONNX, ~300 MB RAM, understands paraphrases) or `hash` (no model, matches shared wording) |
| `FEW_SHOT_K` | `3` | past answers per prompt, `0` = off |
| `SCHEMA_MAX_TABLES` | `6` | above this, only the closest sheets are sent |
| `CLIENT_IP_HEADER` | — | header a trusted proxy sets with the real client IP (`Fly-Client-IP` on Fly) |
| `VITE_API_URL` (frontend) | `http://localhost:8000` | |

### 3. Run with Docker
```bash
docker compose up --build
```
Starts Postgres, Redis, the api, the worker and the frontend.

### …or run locally
```bash
# backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head          # SQLite by default, or set DATABASE_URL
uvicorn app.main:app --reload

# frontend (new terminal)
cd frontend
npm install
npm run dev
```

Local dev: http://localhost:5173 · API docs: http://localhost:8000/docs · Docker Compose: http://localhost:8080

### Tests
```bash
cd backend
pip install -r requirements-dev.txt
pytest
```
The suite runs the real Alembic migrations, uses fakeredis for the queue, and stubs the LLM, so it needs no API key. CI runs it against both SQLite and Postgres, lints and builds the frontend, then boots the full compose stack and pushes an upload through the worker.

---

## 🚀 Deployment

Both halves run on [Fly.io](https://fly.io): the API with a persistent volume for the DuckDB files, and the frontend as a static Vite build served by nginx. Live at https://insightiq-web.fly.dev (machines stop when idle, so the first request can take a few seconds).

### Backend
```bash
cd backend
fly launch --no-deploy        # picks up fly.toml; change the app name if it's taken
fly volumes create insightiq_data --size 1 --region sin
fly secrets set GROQ_API_KEY=gsk_...
fly deploy
```
`fly.toml` sets `UPLOAD_DIR=/data/uploads` on the mounted volume, a `/health` check, and lets the machine stop when idle so a free-tier app costs nothing between visits. Datasets older than `DATASET_TTL_HOURS` are deleted on the next upload.

### Frontend
`VITE_API_URL` is baked in at build time from `frontend/fly.toml`, so change it there if your API app has a different name.
```bash
cd frontend
fly apps create insightiq-web
fly deploy
```
Then point the backend's CORS at it:
```bash
fly secrets set ALLOWED_ORIGINS=https://insightiq-web.fly.dev -a insightiq-api
```
Any static host works too (Vercel, Netlify): build root `frontend`, env `VITE_API_URL`.

### Docker Compose (self-hosted)
`docker compose up --build` runs the full stack (Postgres, Redis, api, worker, frontend) and serves the app on http://localhost:8080. Any VM with Docker can host it this way.

---

## 🔌 API

| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/api/upload` | multipart file → `202` with `dataset_id` and `status` when a worker is running, else `200` with the parsed dataset |
| `GET` | `/api/datasets/{id}` | status (`pending` / `processing` / `ready` / `failed`), columns, tables, preview, warnings |
| `POST` | `/api/query` | `{ dataset_id, question }` → `query_id`, `sql`, `result`, `insight`, `chart_type`, `truncated`, `cached`, `examples_used`, `tables_used` |
| `PUT` | `/api/datasets/{id}/dictionary` | `{ tables: { table: { column: note } } }` — column notes for the prompt |
| `POST` | `/api/queries/{query_id}/feedback` | `{ helpful: bool }` — 👍 keeps it as an example, 👎 removes it and evicts the cached answer |
| `GET` | `/health` | liveness |
| `GET` | `/ready` | readiness — database, queue and cache reachable |

---

## 🗺 Roadmap
- [ ] Charts in the UI (`chart_type` is already returned)
- [ ] Follow-up questions that remember the previous query
- [x] Postgres + Redis queue + ingestion worker
- [x] Tests + CI
- [x] Rate limiting and answer caching (Redis)
- [x] Few-shot retrieval from past queries, column notes, schema selection (pgvector)
- [ ] Text-to-SQL eval set in CI
- [ ] Metrics and dashboards (Prometheus, Grafana)
- [x] Hosted demo
