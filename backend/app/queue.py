import os
from redis import Redis
from rq import Queue

REDIS_URL = os.getenv("REDIS_URL", "")
QUEUE_NAME = "ingest"
JOB_TIMEOUT = int(os.getenv("INGEST_TIMEOUT_SECONDS", "600"))

_queue: Queue | None = None

def get_queue() -> Queue | None:
    """The ingest queue, or None when Redis isn't configured (uploads are then parsed in-process)."""
    global _queue
    if _queue is None and REDIS_URL:
        _queue = Queue(QUEUE_NAME, connection=Redis.from_url(REDIS_URL))
    return _queue
