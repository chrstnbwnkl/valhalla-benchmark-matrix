#!/usr/bin/env python3
"""
load simulator for valhalla's matrix endpoint with weighted bucket selection.

given a directory tree of json request files organized into buckets
(e.g. 0_0, 1_1, 2_2) and a config defining relative weights per bucket,
replays requests in a deterministic pattern across multiple threads.

same inputs + same config + same seed = same pattern.
"""

import argparse
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests


def load_buckets(directory: str) -> dict[str, list[dict]]:
    """load all json request files, grouped by bucket subdirectory."""
    base = Path(directory)
    buckets = {}

    for subdir in sorted(base.iterdir()):
        if not subdir.is_dir():
            continue
        files = sorted(subdir.glob("*.json"))
        if not files:
            continue

        reqs = []
        for f in files:
            with open(f) as fh:
                req = json.load(fh)
                req["_name"] = f.stem
                req["_bucket"] = subdir.name
                reqs.append(req)

        buckets[subdir.name] = reqs

    if not buckets:
        print(f"error: no buckets with .json files found in {directory}", file=sys.stderr)
        sys.exit(1)

    for name, reqs in sorted(buckets.items()):
        print(f"  {name}: {len(reqs)} templates")

    return buckets


def load_config(path: str) -> dict:
    """load and validate a weight config file."""
    with open(path) as f:
        config = json.load(f)

    if "weights" not in config:
        print("error: config must have a 'weights' key", file=sys.stderr)
        sys.exit(1)

    return config


def build_schedule(
    buckets: dict[str, list[dict]], config: dict, total: int, seed: int
) -> list[dict]:
    """build a deterministic sequence of requests using weighted bucket selection."""
    rng = random.Random(seed)
    weights = config["weights"]

    # filter to buckets that exist and have nonzero weight
    active = [(name, w) for name, w in weights.items() if w > 0 and name in buckets]

    if not active:
        print("error: no overlap between config weights and available buckets", file=sys.stderr)
        sys.exit(1)

    missing = [name for name in weights if name not in buckets and weights[name] > 0]
    if missing:
        print(f"warning: buckets in config but not on disk: {', '.join(missing)}", file=sys.stderr)

    unused = [name for name in buckets if name not in weights]
    if unused:
        print(f"warning: buckets on disk but not in config (weight=0): {', '.join(unused)}", file=sys.stderr)

    bucket_names = [name for name, _ in active]
    bucket_weights = [w for _, w in active]

    schedule = []
    for _ in range(total):
        name = rng.choices(bucket_names, weights=bucket_weights, k=1)[0]
        req = rng.choice(buckets[name])
        schedule.append(req)

    # print distribution
    counts = {}
    for req in schedule:
        b = req["_bucket"]
        counts[b] = counts.get(b, 0) + 1

    print("\nscheduled distribution:")
    for name in sorted(counts):
        pct = counts[name] / total * 100
        bar = "#" * int(pct / 2)
        print(f"  {name}: {counts[name]:4d} ({pct:5.1f}%) {bar}")

    return schedule


def send_request(url: str, payload: dict, index: int) -> dict:
    """fire a single matrix request and return timing info."""
    name = payload.get("_name", "?")
    bucket = payload.get("_bucket", "?")

    # strip internal keys before sending
    body = {k: v for k, v in payload.items() if not k.startswith("_")}

    start = time.monotonic()
    try:
        r = requests.post(url, json=body, timeout=300)
        elapsed = time.monotonic() - start
        nsrc = len(body.get("sources", []))
        ntgt = len(body.get("targets", []))
        print(f"  [{bucket}] {name}: {r.status_code} in {elapsed:.3f}s ({nsrc}x{ntgt})")
        return {
            "index": index,
            "bucket": bucket,
            "name": name,
            "status": r.status_code,
            "elapsed": elapsed,
            "error": None,
        }
    except Exception as e:
        elapsed = time.monotonic() - start
        print(f"  [{bucket}] {name}: error in {elapsed:.3f}s ({e})")
        return {
            "index": index,
            "bucket": bucket,
            "name": name,
            "status": None,
            "elapsed": elapsed,
            "error": str(e),
        }


def print_summary(results: list[dict], wall: float, config: dict, args):
    """print overall and per-bucket statistics."""
    ok = [r for r in results if r["error"] is None]
    errors = len(results) - len(ok)

    print()
    print("=" * 60)
    print(f"config:       {config.get('name', args.config)}")
    print(f"wall time:    {wall:.2f}s")
    print(f"requests:     {len(results)} ({errors} errors)")

    if ok:
        times = sorted(r["elapsed"] for r in ok)
        print(f"latency min:  {times[0]:.3f}s")
        print(f"latency p50:  {times[len(times) // 2]:.3f}s")
        print(f"latency p95:  {times[int(len(times) * 0.95)]:.3f}s")
        print(f"latency max:  {times[-1]:.3f}s")
        print(f"throughput:   {len(times) / wall:.2f} req/s")

    # per-bucket breakdown
    by_bucket = {}
    for r in results:
        by_bucket.setdefault(r["bucket"], []).append(r)

    print()
    print("per-bucket breakdown:")
    print(f"  {'bucket':<8} {'count':>6} {'errors':>6} {'p50':>8} {'p95':>8} {'max':>8}")
    print(f"  {'-'*8} {'-'*6} {'-'*6} {'-'*8} {'-'*8} {'-'*8}")

    for name in sorted(by_bucket):
        br = by_bucket[name]
        bt = sorted(r["elapsed"] for r in br if r["error"] is None)
        berr = sum(1 for r in br if r["error"] is not None)
        if bt:
            p50 = bt[len(bt) // 2]
            p95 = bt[int(len(bt) * 0.95)]
            mx = bt[-1]
            print(f"  {name:<8} {len(br):>6} {berr:>6} {p50:>7.3f}s {p95:>7.3f}s {mx:>7.3f}s")
        else:
            print(f"  {name:<8} {len(br):>6} {berr:>6} {'n/a':>8} {'n/a':>8} {'n/a':>8}")

    print("=" * 60)


def run(args):
    config = load_config(args.config)
    print(f"config: {config.get('name', args.config)}")
    print(f"loading buckets from {args.directory}...")
    buckets = load_buckets(args.directory)

    schedule = build_schedule(buckets, config, args.total, args.seed)
    url = f"{args.url.rstrip('/')}/sources_to_targets"

    print(f"\ntarget:  {url}")
    print(f"total:   {args.total} requests")
    print(f"threads: {args.threads}")
    print(f"seed:    {args.seed}")
    print()

    results = []
    t0 = time.monotonic()

    with ThreadPoolExecutor(max_workers=args.threads) as pool:
        futures = {
            pool.submit(send_request, url, payload, i): i
            for i, payload in enumerate(schedule)
        }
        for fut in as_completed(futures):
            results.append(fut.result())

    wall = time.monotonic() - t0
    print_summary(results, wall, config, args)


def main():
    p = argparse.ArgumentParser(description="valhalla matrix load simulator (weighted buckets)")
    p.add_argument("directory", help="directory containing bucket subdirs with .json request files")
    p.add_argument("config", help="JSON config file with bucket weights")
    p.add_argument("-n", "--total", type=int, default=100, help="total requests (default: 100)")
    p.add_argument("-t", "--threads", type=int, default=4, help="concurrent threads (default: 4)")
    p.add_argument("-u", "--url", default="http://localhost:8002", help="valhalla base url")
    p.add_argument("-s", "--seed", type=int, default=42, help="rng seed (default: 42)")
    args = p.parse_args()
    run(args)


if __name__ == "__main__":
    main()