#!/usr/bin/env python3
"""Read-only Blink binding and static eye-part property audit through njc."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path
from typing import Any


def run_json(argv: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        argv, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    result = json.loads(completed.stdout)
    if result.get("result", {}).get("isError"):
        raise RuntimeError(json.dumps(result, ensure_ascii=False))
    return result


def read_uri(njc: str, uri: str) -> dict[str, Any]:
    outer = run_json([njc, "resources", "read", uri])
    return json.loads(outer["result"]["contents"][0]["text"])


def find(njc: str, selector: str) -> dict[str, Any]:
    outer = run_json([njc, "find", selector])
    return json.loads(outer["result"]["contents"][0]["text"])


def resource(njc: str, uuid: int) -> dict[str, Any]:
    return read_uri(njc, f"resource://nijigenerate/resources/{uuid}")["item"]


def binding(njc: str, parameter: int, target: int, name: str) -> dict[str, Any]:
    return read_uri(
        njc,
        f"resource://nijigenerate/bindings/get?parameter={parameter}&target={target}&name={name}",
    )["item"]


def rows_for(rows: list[dict[str, Any]], parameter: int, target: int) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row["parameter"]["uuid"] == parameter and row["target"]["uuid"] == target
    ]


def all_set_white_x_deltas_zero(item: dict[str, Any]) -> tuple[bool, float]:
    data = item["data"]
    maximum = 0.0
    for x_index, row in enumerate(data["values"]):
        for y_index, vertices in enumerate(row):
            if not data["isSet"][x_index][y_index]:
                continue
            for pair in vertices:
                maximum = max(maximum, abs(float(pair[0])))
    return math.isclose(maximum, 0.0, abs_tol=1e-9), maximum


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--njc", required=True, help="Resolved njc executable")
    parser.add_argument("--spec", type=Path, required=True, help="JSON with an eyes array")
    parser.add_argument("--out", type=Path, help="Optional audit JSON output")
    args = parser.parse_args()

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    rows = find(args.njc, "Binding")["items"]
    reports = []
    all_ok = True

    for eye in spec["eyes"]:
        parameter = int(eye["parameter"])
        lash = int(eye["lash"])
        white = int(eye["white"])
        iris = int(eye["iris"])
        lash_item = resource(args.njc, lash)
        white_item = resource(args.njc, white)
        iris_item = resource(args.njc, iris)
        lash_rows = rows_for(rows, parameter, lash)
        white_rows = rows_for(rows, parameter, white)
        iris_rows = rows_for(rows, parameter, iris)
        white_deform_rows = [row for row in white_rows if row["bindingName"] == "deform"]
        if len(white_deform_rows) == 1:
            white_binding = binding(args.njc, parameter, white, "deform")
            white_x_zero, white_x_max = all_set_white_x_deltas_zero(white_binding)
        else:
            white_x_zero, white_x_max = False, None

        prohibited_white = [
            row for row in white_rows if row["bindingName"].lower() in {"opacity", "zsort"}
        ]
        prohibited_lash = [
            row for row in lash_rows if row["bindingName"].lower() == "zsort"
        ]
        checks = {
            "irisHasNoBlinkBindings": not iris_rows,
            "eyewhiteHasExactlyOneDeformBinding": len(white_deform_rows) == 1,
            "eyewhiteHasNoOpacityOrZSortBinding": not prohibited_white,
            "eyelashHasNoZSortBinding": not prohibited_lash,
            "eyewhiteAllSetXDeformDeltasZero": white_x_zero,
            "staticPartPropertiesReadable": all(
                "zsort" in item["data"] and "opacity" in item["data"]
                for item in (lash_item, white_item, iris_item)
            ),
        }
        eye_ok = all(checks.values())
        all_ok = all_ok and eye_ok
        reports.append(
            {
                "side": eye.get("side"),
                "parameter": parameter,
                "parts": {"lash": lash, "white": white, "iris": iris},
                "static": {
                    "lash": {"zsort": lash_item["data"].get("zsort"), "opacity": lash_item["data"].get("opacity")},
                    "white": {"zsort": white_item["data"].get("zsort"), "opacity": white_item["data"].get("opacity")},
                    "iris": {"zsort": iris_item["data"].get("zsort"), "opacity": iris_item["data"].get("opacity")},
                },
                "bindingNames": {
                    "lash": [row["bindingName"] for row in lash_rows],
                    "white": [row["bindingName"] for row in white_rows],
                    "iris": [row["bindingName"] for row in iris_rows],
                },
                "eyewhiteMaxAbsXDelta": white_x_max,
                "checks": checks,
                "ok": eye_ok,
            }
        )

    audit = {
        "schema": "nijigenerate-eye-blink-binding-audit-v1",
        "readOnly": True,
        "eyes": reports,
        "ok": all_ok,
        "fileCommandOpenFileAvoided": True,
        "fileCommandSaveFileCalled": False,
    }
    rendered = json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    raise SystemExit(0 if all_ok else 2)


if __name__ == "__main__":
    main()
