"""Ingestion worker. Run with: python -m app.worker"""
import logging
from dotenv import load_dotenv

load_dotenv()

from rq import Worker
from app.queue import QUEUE_NAME
from app.store import get_redis

def main():
    redis = get_redis()
    if redis is None:
        raise SystemExit("REDIS_URL is not set — the worker has nothing to listen to")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    Worker([QUEUE_NAME], connection=redis).work()

if __name__ == "__main__":
    main()
