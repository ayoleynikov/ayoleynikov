#!/usr/bin/env python3
"""Runnable smoke / light load scenario for Pulse API (Phase 9).

Usage (API already running on localhost:8000)::

    python scripts/smoke_load.py
    python scripts/smoke_load.py --base-url http://127.0.0.1:8000 --requests 50

This is intentionally simple (stdlib + httpx). For heavier load, see the k6 stub
in docs/production-readiness.md.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx


def _one(client: httpx.Client, path: str) -> tuple[str, int, float]:
    start = time.perf_counter()
    response = client.get(path)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return path, response.status_code, elapsed_ms


def main() -> int:
    parser = argparse.ArgumentParser(description="Pulse smoke/load scenario")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=20, help="Total GETs across paths")
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    paths = ["/health", "/ready", "/metrics", "/api/v1/connectors", "/api/v1/workers/queues"]
    jobs = [paths[i % len(paths)] for i in range(args.requests)]

    latencies: list[float] = []
    failures = 0
    with httpx.Client(base_url=args.base_url, timeout=10.0) as client:
        # Warmup / liveness
        probe = client.get("/health")
        if probe.status_code != 200:
            print(f"FAIL: /health returned {probe.status_code}", file=sys.stderr)
            return 1
        print(f"OK /health → {probe.json().get('status')}")

        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [pool.submit(_one, client, path) for path in jobs]
            for fut in as_completed(futures):
                path, status, ms = fut.result()
                latencies.append(ms)
                if status >= 400:
                    failures += 1
                    print(f"  fail {path} → {status} ({ms:.1f}ms)")
                else:
                    print(f"  ok   {path} → {status} ({ms:.1f}ms)")

    if not latencies:
        print("FAIL: no samples", file=sys.stderr)
        return 1

    print(
        "summary: "
        f"n={len(latencies)} failures={failures} "
        f"p50={statistics.median(latencies):.1f}ms "
        f"mean={statistics.mean(latencies):.1f}ms "
        f"max={max(latencies):.1f}ms"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
