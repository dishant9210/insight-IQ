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

COPY alembic.ini start.sh ./
COPY migrations ./migrations
COPY app ./app

RUN mkdir -p /data/uploads

EXPOSE 8000

# migrate, then serve (plus the worker when RUN_WORKER=true, see start.sh).
# Compose runs the worker as its own service: `python -m app.worker`
CMD ["./start.sh"]
