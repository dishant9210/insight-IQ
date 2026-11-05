"""Small key-value store for the answer cache and rate limits.

Redis when REDIS_URL is set, so every api replica shares one cache and one
set of counters. Without it, an in-process dict does the same job for a
single machine (the Fly deploy).
"""
import os
import threading
import time
from redis import Redis

REDIS_URL = os.getenv("REDIS_URL", "")
PREFIX = "iq:"

_redis: Redis | None = None

def get_redis() -> Redis | None:
    global _redis
    if _redis is None and REDIS_URL:
        _redis = Redis.from_url(REDIS_URL)
    return _redis

class RedisStore:
    name = "redis"

    def __init__(self, client: Redis):
        self.r = client

    def get(self, key: str) -> str | None:
        v = self.r.get(PREFIX + key)
        return v.decode() if isinstance(v, bytes) else v

    def set(self, key: str, value: str, ttl: int):
        self.r.set(PREFIX + key, value, ex=ttl)

    def delete(self, key: str):
        self.r.delete(PREFIX + key)

    def hit(self, key: str, window: int) -> tuple[int, int]:
        """Count one request in a fixed window. Returns (count, seconds until reset)."""
        k = PREFIX + key
        pipe = self.r.pipeline()
        pipe.incr(k)
        pipe.expire(k, window, nx=True)
        pipe.ttl(k)
        count, _, ttl = pipe.execute()
        return count, ttl if ttl > 0 else window

    def ping(self):
        self.r.ping()

class MemoryStore:
    name = "memory"
    MAX_KEYS = 10_000

    def __init__(self):
        self._data: dict[str, tuple[object, float]] = {}
        self._lock = threading.Lock()

    def _live(self, key: str, now: float):
        item = self._data.get(key)
        if item and item[1] <= now:
            del self._data[key]
            return None
        return item

    def _make_room(self, now: float):
        if len(self._data) < self.MAX_KEYS:
            return
        for k in [k for k, (_, exp) in self._data.items() if exp <= now]:
            del self._data[k]
        # still full — drop the oldest entries (dicts keep insertion order)
        while len(self._data) >= self.MAX_KEYS:
            del self._data[next(iter(self._data))]

    def get(self, key: str) -> str | None:
        with self._lock:
            item = self._live(key, time.monotonic())
            return item[0] if item else None

    def set(self, key: str, value: str, ttl: int):
        with self._lock:
            now = time.monotonic()
            self._make_room(now)
            self._data[key] = (value, now + ttl)

    def delete(self, key: str):
        with self._lock:
            self._data.pop(key, None)

    def hit(self, key: str, window: int) -> tuple[int, int]:
        with self._lock:
            now = time.monotonic()
            item = self._live(key, now)
            if item is None:
                self._make_room(now)
                item = (0, now + window)
            count = item[0] + 1
            self._data[key] = (count, item[1])
            return count, max(1, int(item[1] - now + 0.999))

    def ping(self):
        pass

    def clear(self):
        with self._lock:
            self._data.clear()

_store = None

def get_store():
    global _store
    if _store is None:
        client = get_redis()
        _store = RedisStore(client) if client else MemoryStore()
    return _store
