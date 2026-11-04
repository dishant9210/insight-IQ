"""Ingestion worker. Run with: python -m app.worker"""
import logging
from dotenv import load_dotenv

load_dotenv()

from redis import Redis
from rq import Worker
from app.queue import REDIS_URL, QUEUE_NAME

def main():
    if not REDIS_URL:
        raise SystemExit("REDIS_URL is not set — the worker has nothing to listen to")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    Worker([QUEUE_NAME], connection=Redis.from_url(REDIS_URL)).work()

if __name__ == "__main__":
    main()
