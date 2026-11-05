"""start.sh, with alembic / uvicorn / python swapped for stubs on PATH."""
import os
import signal
import subprocess
import time
import pytest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "start.sh")

def _bash_has_wait_n() -> bool:
    try:
        out = subprocess.run(["bash", "-c", "help wait"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        return False
    return "-n" in out

pytestmark = pytest.mark.skipif(not _bash_has_wait_n(), reason="needs bash >= 4.3 (wait -n)")

def stubs(tmp_path, worker="sleep 30"):
    log = tmp_path / "log"
    for name, body in {
        "alembic": f'echo migrate >> {log}',
        "uvicorn": f'echo api >> {log}; trap "echo api-stopped >> {log}; exit 0" TERM; sleep 30 & wait',
        "python": f'echo "worker $METRICS_PORT $PROMETHEUS_MULTIPROC_DIR" >> {log}; {worker}',
    }.items():
        path = tmp_path / name
        path.write_text(f"#!/usr/bin/env bash\n{body}\n")
        path.chmod(0o755)
    return log

def start(tmp_path, **env):
    full = {"PATH": f"{tmp_path}:{os.environ['PATH']}", **env}
    return subprocess.Popen(["bash", SCRIPT], env=full, cwd=tmp_path)

def lines(log, want, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        got = log.read_text().split("\n") if log.exists() else []
        if all(any(line.startswith(w) for line in got) for w in want):
            return got
        time.sleep(0.05)
    raise AssertionError(f"wanted {want}, log has {log.read_text() if log.exists() else ''!r}")

def test_api_only_without_redis(tmp_path):
    log = stubs(tmp_path)
    p = start(tmp_path, RUN_WORKER="true")          # no REDIS_URL: nothing for a worker to do
    got = lines(log, ["migrate", "api"])
    p.send_signal(signal.SIGTERM)
    assert p.wait(5) == 0
    assert not any(line.startswith("worker") for line in got)

def test_worker_beside_the_api(tmp_path):
    log = stubs(tmp_path)
    p = start(tmp_path, RUN_WORKER="true", REDIS_URL="redis://x")
    got = lines(log, ["migrate", "api", "worker"])
    assert "worker 9092 /tmp/worker-metrics" in got
    p.send_signal(signal.SIGTERM)                    # a normal stop exits cleanly
    assert p.wait(5) == 0
    lines(log, ["api-stopped"])

def test_a_crashed_worker_takes_the_api_down(tmp_path):
    log = stubs(tmp_path, worker="sleep 0.3; exit 3")
    p = start(tmp_path, RUN_WORKER="true", REDIS_URL="redis://x")
    assert p.wait(5) == 1                            # so the platform restarts the machine
    lines(log, ["api-stopped"])
