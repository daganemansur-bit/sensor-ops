"""Replay a deterministic fixture, or import the firmware simulator CSV."""
import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


def samples(path: Path):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            seq = int(row["sequence"])
            yield {
                "device": "bench-1",
                "sequence": seq,
                "observed_at": (base + timedelta(seconds=seq)).isoformat(),
                "millivolts": int(row["millivolts"]) if row["millivolts"] else None,
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="?", type=Path, default=Path("samples.csv"))
    args = parser.parse_args()
    try:
        for sample in samples(args.csv):
            req = Request("http://127.0.0.1:8000/samples", json.dumps(sample).encode(),
                          {"Content-Type": "application/json"}, method="POST")
            with urlopen(req, timeout=3) as response:
                print(sample["sequence"], response.read().decode())
    except (OSError, URLError, ValueError, KeyError) as exc:
        print(f"Replay stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
