#!/usr/bin/env python3
"""
Generate a Valhalla sources_to_targets request with random points within a place boundary.
"""

import argparse
import hashlib
import json
import random
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

import numpy as np

try:
    from shapely.geometry import shape, Point
except ImportError:
    print(
        "Error: shapely is required. Install with: pip install shapely", file=sys.stderr
    )
    sys.exit(1)


def fetch_polygon(place_name: str, cache_dir: Path | None = None) -> dict:
    if cache_dir:
        cache_key = hashlib.sha256(place_name.encode()).hexdigest()[:16]
        cache_file = cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            print(f"Using cached polygon for '{place_name}'", file=sys.stderr)
            return json.loads(cache_file.read_text())

    params = {
        "q": place_name,
        "format": "jsonv2",
        "polygon_geojson": "1",
        "limit": "1",
    }

    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"User-Agent": "matrix-locations-generator/1.0"}
    )

    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())

    if not data:
        print(f"Error: no results found for place '{place_name}'", file=sys.stderr)
        sys.exit(1)

    result = data[0]
    if "geojson" not in result:
        print(
            f"Error: no polygon returned for '{place_name}'. Got type: {result.get('type')}",
            file=sys.stderr,
        )
        sys.exit(1)

    geojson = result["geojson"]
    if geojson["type"] not in ("Polygon", "MultiPolygon"):
        print(
            f"Error: expected Polygon/MultiPolygon, got {geojson['type']}. "
            f"Try being more specific.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Found: {result.get('display_name', place_name)}", file=sys.stderr)

    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(geojson))
        print(f"Cached polygon to {cache_file}", file=sys.stderr)

    return geojson


def random_points_in_polygon(geojson: dict, n: int) -> list[tuple[float, float]]:
    polygon = shape(geojson)
    minx, miny, maxx, maxy = polygon.bounds
    points = []
    attempts = 0
    max_attempts = n * 100

    while len(points) < n and attempts < max_attempts:
        p = Point(random.uniform(minx, maxx), random.uniform(miny, maxy))
        attempts += 1
        if polygon.contains(p):
            points.append((p.y, p.x))  # lat, lon

    if len(points) < n:
        print(
            f"Warning: only generated {len(points)}/{n} points after {max_attempts} attempts. "
            f"Place polygon may be very irregular.",
            file=sys.stderr,
        )

    return points


def pick_points_from_csv(
    csv_path: str, geojson: dict, n: int
) -> list[tuple[float, float]]:
    polygon = shape(geojson)

    print(f"Loading points from {csv_path}...", file=sys.stderr)
    coords = np.loadtxt(csv_path, delimiter=",", skiprows=1)
    print(f"Loaded {len(coords)} points", file=sys.stderr)

    # bbox pre-filter to narrow candidates cheaply
    minx, miny, maxx, maxy = polygon.bounds
    mask = (
        (coords[:, 0] >= minx)
        & (coords[:, 0] <= maxx)
        & (coords[:, 1] >= miny)
        & (coords[:, 1] <= maxy)
    )
    candidates = coords[mask]
    print(f"{len(candidates)} points within bounding box", file=sys.stderr)

    if len(candidates) == 0:
        print(
            "Error: no points from CSV fall within the polygon bounding box.",
            file=sys.stderr,
        )
        sys.exit(1)

    # precise PIP using vectorized contains
    from shapely import contains_xy

    hits_mask = contains_xy(polygon, candidates[:, 0], candidates[:, 1])
    hits_idx = np.where(hits_mask)[0]
    print(f"{len(hits_idx)} points within polygon", file=sys.stderr)

    if len(hits_idx) == 0:
        print("Error: no points from CSV fall within the polygon.", file=sys.stderr)
        sys.exit(1)

    if len(hits_idx) < n:
        print(
            f"Warning: only {len(hits_idx)} points available in polygon, requested {n}. "
            f"Using all of them.",
            file=sys.stderr,
        )
        selected = candidates[hits_idx]
    else:
        selected_idx = np.random.choice(hits_idx, size=n, replace=False)
        selected = candidates[selected_idx]

    # coords are X,Y (lon,lat) in CSV, return as (lat, lon)
    return [(row[1], row[0]) for row in selected]


def build_request(
    points: list[tuple[float, float]], partial: dict | None = None
) -> dict:
    locations = [{"lat": lat, "lon": lon} for lat, lon in points]

    request = {"sources": locations, "targets": locations}

    if partial:
        request.update(partial)

    return request


def main():
    parser = argparse.ArgumentParser(
        description="Generate a Valhalla sources_to_targets request with random points inside a place."
    )
    parser.add_argument("place", help="Place name (e.g. 'San Francisco', 'Köln')")
    parser.add_argument("n", type=int, help="Number of random points to generate")
    parser.add_argument(
        "--partial", type=str, help="Path to partial Valhalla request JSON to merge in"
    )
    parser.add_argument(
        "--points-csv",
        type=str,
        help="CSV with X,Y columns (lon,lat) to sample from instead of random generation",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=".polygon_cache",
        help="Directory to cache Nominatim polygon responses (default: .polygon_cache)",
    )
    args = parser.parse_args()

    if args.n < 1:
        print("Error: n must be at least 1", file=sys.stderr)
        sys.exit(1)

    partial = None
    if args.partial:
        try:
            with open(args.partial) as f:
                partial = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error reading partial JSON: {e}", file=sys.stderr)
            sys.exit(1)

    cache_dir = Path(args.cache_dir)
    print(f"Fetching boundary for '{args.place}'...", file=sys.stderr)
    geojson = fetch_polygon(args.place, cache_dir)

    if args.points_csv:
        print(f"Picking {args.n} points from CSV...", file=sys.stderr)
        points = pick_points_from_csv(args.points_csv, geojson, args.n)
    else:
        print(f"Generating {args.n} random points...", file=sys.stderr)
        points = random_points_in_polygon(geojson, args.n)

    request = build_request(points, partial)
    json.dump(request, sys.stdout, indent=2)
    print()  # trailing newline


if __name__ == "__main__":
    main()
