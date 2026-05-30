"""Launch the FAL Video Studio: FastAPI server + worker as a child process."""

from __future__ import annotations

import atexit
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKER = PROJECT_ROOT / "Python" / "scripts" / "studio" / "worker.py"

HOST = "127.0.0.1"
PORT = 8765


def main() -> int:
    print(f"Starting worker subprocess: {WORKER}", flush=True)
    worker = subprocess.Popen(
        [sys.executable, str(WORKER)],
        cwd=PROJECT_ROOT,
    )

    def _kill_worker() -> None:
        if worker.poll() is None:
            try:
                worker.terminate()
                worker.wait(timeout=3)
            except subprocess.TimeoutExpired:
                worker.kill()
    atexit.register(_kill_worker)
    signal.signal(signal.SIGINT, lambda *_: (_kill_worker(), sys.exit(0)))

    print(f"Starting studio on http://{HOST}:{PORT}/", flush=True)
    print("Open the URL above in your browser.", flush=True)
    print("Press Ctrl+C to stop both server and worker.\n", flush=True)
    time.sleep(0.5)

    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: uv sync", file=sys.stderr)
        return 1

    uvicorn.run(
        "Python.scripts.studio.server:app",
        host=HOST, port=PORT, log_level="info",
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
