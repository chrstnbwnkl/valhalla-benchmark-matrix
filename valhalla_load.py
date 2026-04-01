#!/usr/bin/env python3
"""
simple load simulator for valhalla's matrix endpoint.

given a directory of json request files, replays them in a deterministic
pattern across multiple threads. same inputs = same pattern, so you can
compare builds.
"""

import argparse
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests


def load_requests(directory: str) -> list[dict]:
    """load and sort all json files from the directory. sorting ensures
    determinism regardless of filesystem ordering."""
    files = sorted(Path(directory).glob("*.json"))
    if not files:
        print(f"error: no .json files found in {directory}", file=sys.stderr)
        sys.exit(1)

    reqs = []
    for f in files:
        with open(f) as fh:
            req = json.load(fh)
            req["name"] = f.stem
            reqs.append(req)

    print(f"loaded {len(reqs)} request template(s) from {directory}")
    return reqs


def build_schedule(templates: list[dict], total: int, seed: int) -> list[dict]:
    """build a deterministic sequence of requests by seeding an rng.
    same templates + same total + same seed = same sequence."""
    rng = random.Random(seed)
    return [rng.choice(templates) for _ in range(total)]


def send_request(url: str, payload: dict, index: int) -> dict:
    """fire a single matrix request and return timing info."""
    start = time.monotonic()
    try:
        r = requests.post(url, json=payload, timeout=300)
        elapsed = time.monotonic() - start
        print(
            f"successful: {payload.get('name', 'no name')}, {elapsed:.3f}s | ({len(payload['sources'])} sources, {len(payload['targets'])} targets)"
        )
        return {
            "index": index,
            "status": r.status_code,
            "elapsed": elapsed,
            "error": None,
        }
    except Exception as e:
        elapsed = time.monotonic() - start
        print(f"error: {payload.get('name', 'no name')}, {elapsed:.3f}s")
        return {
            "index": index,
            "status": None,
            "elapsed": elapsed,
            "error": str(e),
        }


def run(args):
    templates = load_requests(args.directory)
    schedule = build_schedule(templates, args.total, args.seed)
    url = f"{args.url.rstrip('/')}/sources_to_targets"

    print(f"target:  {url}")
    print(f"total:   {args.total} requests")
    print(f"threads: {args.threads}")
    print(f"seed:    {args.seed}")
    print()

    results = []
    errors = 0
    t0 = time.monotonic()

    with ThreadPoolExecutor(max_workers=args.threads) as pool:
        futures = {
            pool.submit(send_request, url, payload, i): i
            for i, payload in enumerate(schedule)
        }

        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)

            if res["error"]:
                errors += 1

    wall = time.monotonic() - t0
    times = [r["elapsed"] for r in results if r["error"] is None]

    print()
    print("--- summary ---")
    print(f"wall time:    {wall:.2f}s")
    print(f"requests:     {args.total} ({errors} errors)")
    if times:
        times.sort()
        print(f"latency min:  {times[0]:.3f}s")
        print(f"latency p50:  {times[len(times) // 2]:.3f}s")
        print(f"latency p95:  {times[int(len(times) * 0.95)]:.3f}s")
        print(f"latency max:  {times[-1]:.3f}s")
        print(f"throughput:   {len(times) / wall:.2f} req/s")


def main():
    p = argparse.ArgumentParser(description="valhalla matrix load simulator")
    p.add_argument("directory", help="directory containing .json request files")
    p.add_argument(
        "-n",
        "--total",
        type=int,
        default=100,
        help="total requests to make (default: 100)",
    )
    p.add_argument(
        "-t",
        "--threads",
        type=int,
        default=4,
        help="number of concurrent threads (default: 4)",
    )
    p.add_argument(
        "-u",
        "--url",
        default="http://localhost:8002",
        help="valhalla base url (default: http://localhost:8002)",
    )
    p.add_argument(
        "-s",
        "--seed",
        type=int,
        default=42,
        help="rng seed for reproducibility (default: 42)",
    )
    args = p.parse_args()

    run(args)


if __name__ == "__main__":
    main()
