#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path

import yaml


def load_yaml(path):
    data = yaml.safe_load(path.read_text())
    results = data.get("results", [])
    created_at = data.get("createdAt")
    retakes = [item for item in results if str(item.get("result", "")).lower() != "ok"]
    return created_at, results, retakes


def load_json(path):
    data = json.loads(path.read_text())
    results = data.get("results", [])
    created_at = data.get("createdAt")
    decision = str(data.get("reviewResult", {}).get("decision", "")).lower()
    retakes = [item for item in results if str(item.get("result", "")).lower() != "ok"]
    if decision == "retake" and not retakes:
        retakes = [{"id": "(reviewResult)", "result": "retake", "reason": "reviewResult.decision is retake"}]
    return created_at, results, retakes


def report(kind, path, created_at, results, retakes):
    print(f"{kind}: {path.name}")
    print(f"createdAt: {created_at}")
    print(f"total: {len(results)}")
    print(f"ok: {len(results) - len(retakes)}")
    print(f"retake: {len(retakes)}")
    for item in retakes:
        reason = str(item.get("reason", "")).replace("\n", " ")
        print(f"- {item.get('id')}: {item.get('result')} - {reason[:240]}")


def main():
    parser = argparse.ArgumentParser(description="Watch nijigenerate checklist YAML or JSON review state.")
    parser.add_argument("--yaml", help="Path to self-review.yaml")
    parser.add_argument("--json", help="Path to latest-review.json")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if bool(args.yaml) == bool(args.json):
        parser.error("Specify exactly one of --yaml or --json")

    path = Path(args.yaml or args.json)
    loader = load_yaml if args.yaml else load_json
    kind = "yaml" if args.yaml else "json"
    last_created_at = None

    while True:
        if path.exists():
            created_at, results, retakes = loader(path)
            if created_at != last_created_at:
                report(kind, path, created_at, results, retakes)
                last_created_at = created_at
                if not retakes:
                    raise SystemExit(0)
        elif args.once:
            print(f"missing: {path.name}")
            raise SystemExit(2)

        if args.once:
            raise SystemExit(1)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
