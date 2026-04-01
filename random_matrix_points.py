#!/usr/bin/env python3
"""
Generate a Valhalla sources_to_targets request with random points within a place boundary.
"""

import argparse
import json
import random
import sys
import time
import urllib.request
import urllib.parse

try:
    from shapely.geometry import shape, Point
except ImportError:
    print(
        "Error: shapely is required. Install with: pip install shapely", file=sys.stderr
    )
    sys.exit(1)


def fetch_polygon(place_name: str) -> dict:
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
            f"Try being more specific with --country.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Found: {result.get('display_name', place_name)}", file=sys.stderr)
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

    print(f"Fetching boundary for '{args.place}'...", file=sys.stderr)
    geojson = fetch_polygon(args.place)

    print(f"Generating {args.n} random points...", file=sys.stderr)
    points = random_points_in_polygon(geojson, args.n)

    request = build_request(points, partial)
    json.dump(request, sys.stdout, indent=2)
    print()  # trailing newline


if __name__ == "__main__":
    main()
