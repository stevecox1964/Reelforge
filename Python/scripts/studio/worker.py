"""Durable SQLite-backed worker for FAL studio stage jobs."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from Python.scripts.studio.server import (  # noqa: E402
    DB_PATH, claim_next_job, job_worker_loop,
    mark_interrupted_jobs, run_claimed_job,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="FAL studio durable worker.")
    parser.add_argument("--once", action="store_true", help="Run one job then exit.")
    args = parser.parse_args()

    mark_interrupted_jobs()
    print(f"Worker using SQLite queue: {DB_PATH}", flush=True)

    if args.once:
        job = claim_next_job()
        if job is None:
            print("No queued jobs.")
            return 0
        run_claimed_job(job)
        return 0

    try:
        job_worker_loop()
    except KeyboardInterrupt:
        print("\nWorker stopped.")
        time.sleep(0.1)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
