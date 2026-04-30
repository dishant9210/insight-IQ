InsightIQ: Conversational Data Analysis
InsightIQ is an AI-powered platform designed to democratize data analysis. It allows users to upload datasets and ask complex questions in plain English. The system translates natural language into optimized SQL, executes it in real-time, and provides AI-driven insights.

Key Features (Week 1 Milestone)
Natural Language to SQL: Powered by Groq (Llama 3) and OpenAI for sub-second, accurate query generation.

High-Performance Execution: Uses DuckDB and Pandas to query CSV/Excel files directly without the overhead of a traditional database.

Interactive UI: A modern React dashboard with dynamic results tables and SQL transparency (view the code the AI wrote).

Containerized Architecture: Fully Dockerized services for both frontend and backend to ensure environment consistency.

Tech Stack
Backend
FastAPI: High-performance Python web framework.

LangChain: Framework for developing applications powered by language models.

DuckDB: In-process SQL OLAP database management system.

Pydantic: Data validation and settings management.

Frontend
React (Vite): Modern frontend framework for a fast development experience.

Tailwind CSS: Utility-first CSS framework for clean, responsive design.

DevOps & Tools
Docker / Docker Compose: For microservices orchestration.

Groq LPU™: Used for high-speed LLM inference.

Getting Started
Prerequisites
Docker and Docker Compose installed.

API Keys for OpenAI and Groq.

Installation
Clone the Repository

Bash
git clone https://github.com/your-username/insight-iq.git
cd insight-iq
Configure Environment Variables
Create a .env file in the root directory:

Code snippet
OPENAI_API_KEY=your_openai_key
GROQ_API_KEY=your_groq_key
Launch the Application

Bash
docker-compose up --build
Access the Platform

Frontend: http://localhost:5173

Backend API: http://localhost:8000

git commit -m "add README"
git branch -M main