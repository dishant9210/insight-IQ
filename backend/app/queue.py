import os
from rq import Queue
from app.store import get_redis

QUEUE_NAME = "ingest"
JOB_TIMEOUT = int(os.getenv("INGEST_TIMEOUT_SECONDS", "600"))

_queue: Queue | None = None

def get_queue() -> Queue | None:
    """The ingest queue, or None when Redis isn't configured (uploads are then parsed in-process)."""
    global _queue
    if _queue is None and (redis := get_redis()) is not None:
        _queue = Queue(QUEUE_NAME, connection=redis)
    return _queue
