"""Ingestion worker. Run with: python -m app.worker"""
import glob
import os
from dotenv import load_dotenv

load_dotenv()

# Jobs run in forks, so metrics go through files in this dir. It has to exist
# (and be cleared of the last run's files) before prometheus_client creates
# any metric, i.e. before app.metrics is imported.
if mp_dir := os.getenv("PROMETHEUS_MULTIPROC_DIR"):
    os.makedirs(mp_dir, exist_ok=True)
    for f in glob.glob(os.path.join(mp_dir, "*.db")):
        os.remove(f)

from rq import Worker
from app import logging_setup, metrics, tracing
from app.queue import QUEUE_NAME
from app.store import get_redis

def main():
    redis = get_redis()
    if redis is None:
        raise SystemExit("REDIS_URL is not set — the worker has nothing to listen to")
    logging_setup.setup()
    tracing.setup("insightiq-worker")
    metrics.serve()
    Worker([QUEUE_NAME], connection=redis).work()

if __name__ == "__main__":
    main()
