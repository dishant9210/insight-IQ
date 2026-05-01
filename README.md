<div align="center">
  <img src="https://cdn-icons-png.flaticon.com/512/2103/2103633.png" alt="InsightIQ Logo" width="120">
  <h1>InsightIQ</h1>
  <p><b>Talk to your data. Get instant answers.</b></p>

  ![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
  ![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
  ![DuckDB](https://img.shields.io/badge/DuckDB-FFF000?style=for-the-badge&logo=duckdb&logoColor=black)
  ![Groq](https://img.shields.io/badge/Groq-f55036?style=for-the-badge)
  ![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)

  <p>
    <a href="#-key-features">Features</a> •
    <a href="#-getting-started">Installation</a> •
    <a href="#-roadmap">Roadmap</a> •
    <a href="#-tech-stack">Stack</a>
  </p>
</div>

---

## 📖 About InsightIQ
InsightIQ is an AI-powered conversational analytics platform. It bridges the gap between raw data and decision-making by allowing users to query CSV/Excel files using plain English. No SQL knowledge? No problem. 

Our engine uses **Llama 3 (via Groq)** for lightning-fast SQL generation and **DuckDB** for analytical processing directly within your browser's reach.

---

## 🚀 Key Features

### 🧠 **Conversational Intelligence**
Ask questions like *"Who are my top 10 customers by revenue?"* or *"Show me the monthly trend of sales,"* and watch the AI generate precise SQL.

### ⚡ **Extreme Performance**
By leveraging **Groq LPU™ inference** and **DuckDB**, InsightIQ provides sub-second responses even on complex analytical queries.

### 🐳 **Developer First**
Fully containerized with Docker. One command and your entire full-stack environment is ready to go.

---

## 🛠 Tech Stack

| Layer | Technology |
| :--- | :--- |
| **Frontend** | React 18, Vite, Tailwind CSS, Axios |
| **Backend** | FastAPI, LangChain, Pydantic |
| **Database** | DuckDB (OLAP), Pandas |
| **AI/LLM** | Groq (Llama 3), OpenAI |
| **Infrastructure** | Docker, Docker Compose |

---

## 🚦 Getting Started

### 1. Clone the repo
```bash
git clone [https://github.com/yourusername/insight-iq.git](https://github.com/yourusername/insight-iq.git)
cd insight-iq
```

2. Set up Environment Variables
Create a .env file in the root folder:

ENV

```bash
GROQ_API_KEY=gsk_your_key_here
OPENAI_API_KEY=sk_your_key_here
```

3. Spin up the containers
```Bash
docker-compose up --build```

Frontend: http://localhost:5173

API Docs: http://localhost:8000/docs