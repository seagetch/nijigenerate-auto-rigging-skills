#!/usr/bin/env python3
import argparse
from pathlib import Path

import yaml


def main():
    parser = argparse.ArgumentParser(description="Summarize nijigenerate checklist self-review YAML.")
    parser.add_argument("path", help="Path to self-review.yaml")
    args = parser.parse_args()

    path = Path(args.path)
    data = yaml.safe_load(path.read_text())
    results = data.get("results", [])
    retakes = [item for item in results if str(item.get("result", "")).lower() != "ok"]

    print(f"path: {path.name}")
    print(f"createdAt: {data.get('createdAt')}")
    print(f"total: {len(results)}")
    print(f"ok: {len(results) - len(retakes)}")
    print(f"retake: {len(retakes)}")
    for item in retakes:
        reason = str(item.get("reason", "")).replace("\n", " ")
        print(f"- {item.get('id')}: {item.get('result')} - {reason[:240]}")


if __name__ == "__main__":
    main()
