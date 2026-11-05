FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UPLOAD_DIR=/data/uploads \
    FASTEMBED_CACHE_PATH=/opt/fastembed

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image when EMBEDDER=fastembed will be used,
# so the first question doesn't wait on a download. Empty = skip (EMBEDDER=hash).
ARG EMBEDDING_MODEL=""
RUN if [ -n "$EMBEDDING_MODEL" ]; then \
      python -c "from fastembed import TextEmbedding; TextEmbedding('$EMBEDDING_MODEL')"; \
    fi

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

RUN mkdir -p /data/uploads

EXPOSE 8000

# migrate, then serve. The worker uses the same image: `python -m app.worker`
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
