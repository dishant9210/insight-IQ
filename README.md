<div align="center">
  <img src="https://cdn-icons-png.flaticon.com/512/2103/2103633.png" alt="InsightIQ Logo" width="120">
  <h1>InsightIQ</h1>
  <p><b>Talk to your data. Get instant answers.</b></p>
  <p><a href="https://insightiq-web.fly.dev"><b>Live demo</b></a> · <a href="https://insightiq-api.fly.dev/health">API</a></p>

  ![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
  ![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
  ![DuckDB](https://img.shields.io/badge/DuckDB-FFF000?style=for-the-badge&logo=duckdb&logoColor=black)
  ![Groq](https://img.shields.io/badge/Groq-f55036?style=for-the-badge)
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

### ⚡ **Fast**
Groq inference plus DuckDB's columnar engine means most questions come back in a second or two, even on a few hundred thousand rows.

### 🔒 **Safe by construction**
LLM output is treated as untrusted input. See [Security](#-security).

---

## 🔁 How it works

```
upload ──▶ loader (csv / excel / json / parquet) ──▶ one .duckdb file per dataset
                                                              │
question ──▶ schema + sample rows ──▶ LLM (Groq) ──▶ SQL ──▶ guard ──▶ DuckDB (read-only) ──▶ result
                                                                                        │
                                                                        LLM (Groq) ──▶ insight
```

1. **Upload** — the file is streamed to disk (size-capped), parsed by the matching loader, and written into its own DuckDB database. Metadata (columns, detected types, preview) is saved alongside it, so datasets survive a restart.
2. **Query** — the schema and a few sample rows go to the model with the question. The returned SQL is cleaned and validated, then run with a row limit and a timeout.
3. **Insight** — the first few result rows go back to the model for a short written summary. If the query returned nothing, this step is skipped.

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

---

## 🛠 Tech Stack

| Layer | Technology |
| :--- | :--- |
| **Frontend** | React 19, Vite, Tailwind CSS |
| **Backend** | FastAPI, Pydantic, LangChain |
| **Database** | DuckDB, pandas, pyarrow |
| **AI/LLM** | Groq (GPT-OSS 120B by default, any Groq model via `GROQ_MODEL`) |
| **Infrastructure** | Docker, Docker Compose |

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
| `UPLOAD_DIR` | `uploads` | datasets + metadata live here |
| `MAX_UPLOAD_MB` | `50` | |
| `MAX_RESULT_ROWS` | `1000` | |
| `QUERY_TIMEOUT_SECONDS` | `20` | |
| `VITE_API_URL` (frontend) | `http://localhost:8000` | |

### 3. Run with Docker
```bash
docker compose up --build
```

### …or run locally
```bash
# backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# frontend (new terminal)
cd frontend
npm install
npm run dev
```

Local dev: http://localhost:5173 · API docs: http://localhost:8000/docs · Docker Compose: http://localhost:8080

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
`docker compose up --build` builds both images — the frontend as an nginx-served static bundle, the backend with a named volume for data — and serves the app on http://localhost:8080.

---

## 🔌 API

| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/api/upload` | multipart file → `dataset_id`, columns, detected types, preview, warnings |
| `GET` | `/api/datasets/{id}` | metadata for an uploaded dataset |
| `POST` | `/api/query` | `{ dataset_id, question }` → `sql`, `result`, `insight`, `chart_type`, `truncated` |
| `GET` | `/health` | liveness |

---

## 🗺 Roadmap
- [ ] Charts in the UI (`chart_type` is already returned)
- [ ] Follow-up questions that remember the previous query
- [ ] Rate limiting
- [ ] Tests + CI
- [x] Hosted demo
