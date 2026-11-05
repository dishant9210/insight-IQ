"""LOG_FORMAT=json writes one JSON object per line with the trace id on it, so
a log line in any aggregator links straight to its trace. Default is plain
text for local runs."""
import json
import logging
import os
from contextvars import ContextVar
from datetime import datetime, timezone

LOG_FORMAT = os.getenv("LOG_FORMAT", "text")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# set per request from X-Request-ID (the gateway mints one), so a log line can
# be matched to the gateway's access log as well as to its trace
request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        from app.tracing import ids
        out = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if (current := ids()) is not None:
            out["trace_id"], out["span_id"] = current
        if (rid := request_id.get()) is not None:
            out["request_id"] = rid
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)

def setup():
    handler = logging.StreamHandler()
    if LOG_FORMAT == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(LOG_LEVEL)
    # uvicorn and rq bring their own handlers; route them through ours
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "rq.worker"):
        lg = logging.getLogger(name)
        lg.handlers[:] = []
        lg.propagate = True
