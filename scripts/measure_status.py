#!/usr/bin/env python3
"""Measure the current /api/status wall-clock baseline without extra dependencies.

Local loopback measurements bypass environment-configured HTTP(S) proxies so
corporate proxy settings cannot distort the baseline.
"""

import argparse
import json
import statistics
import time
import urllib.request


def percentile(values, fraction):
    values = sorted(values)
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, round((len(values) - 1) * fraction)))
    return values[index]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8088/api/status")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    samples_ms = []
    sizes = []
    failures = []

    for i in range(args.runs):
        started = time.perf_counter()
        try:
            with opener.open(args.url, timeout=args.timeout) as response:
                body = response.read()
                elapsed_ms = (time.perf_counter() - started) * 1000
                samples_ms.append(elapsed_ms)
                sizes.append(len(body))
                json.loads(body)
                print(f"run={i + 1} status={response.status} ms={elapsed_ms:.1f} bytes={len(body)}")
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            failures.append({"run": i + 1, "ms": round(elapsed_ms, 1), "error": str(exc)})
            print(f"run={i + 1} FAIL ms={elapsed_ms:.1f} error={exc}")

    result = {
        "url": args.url,
        "requested_runs": args.runs,
        "successful_runs": len(samples_ms),
        "failed_runs": len(failures),
        "latency_ms": {
            "min": round(min(samples_ms), 1) if samples_ms else None,
            "median": round(statistics.median(samples_ms), 1) if samples_ms else None,
            "p95": round(percentile(samples_ms, 0.95), 1) if samples_ms else None,
            "max": round(max(samples_ms), 1) if samples_ms else None,
        },
        "response_bytes": {
            "min": min(sizes) if sizes else None,
            "median": statistics.median(sizes) if sizes else None,
            "max": max(sizes) if sizes else None,
        },
        "failures": failures,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
