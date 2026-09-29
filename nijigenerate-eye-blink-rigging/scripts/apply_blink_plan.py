#!/usr/bin/env python3
"""Apply an explicit delta-only Blink plan through njc; dry-run by default."""

from __future__ import annotations

import argparse
import hashlib
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


def tool(njc: str, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return run_json([njc, "tools", "call", name, "--json", json.dumps(payload)])


def read_uri(njc: str, uri: str) -> dict[str, Any]:
    outer = run_json([njc, "resources", "read", uri])
    return json.loads(outer["result"]["contents"][0]["text"])


def find(njc: str, selector: str) -> dict[str, Any]:
    outer = run_json([njc, "find", selector])
    return json.loads(outer["result"]["contents"][0]["text"])


def binding_key(row: dict[str, Any]) -> tuple[int, int, str]:
    return row["parameter"]["uuid"], row["target"]["uuid"], row["bindingName"]


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def binding_hashes(njc: str) -> dict[tuple[int, int, str], str]:
    result = {}
    for row in find(njc, "Binding")["items"]:
        item = read_uri(njc, row["uri"])["item"]
        result[binding_key(row)] = canonical_hash(item)
    return result


def validate(plan: dict[str, Any]) -> dict[str, Any]:
    iris_targets = {int(value) for value in plan.get("irisTargets", [])}
    white_targets = {int(value) for value in plan.get("whiteTargets", [])}
    allowed_rows: set[tuple[int, int, str]] = set()

    for edit in plan.get("deformEdits", []):
        parameter = int(edit["parameter"])
        target = int(edit["target"])
        values = [float(value) for value in edit["values"]]
        if target in iris_targets:
            raise ValueError(f"Iris deform is prohibited: {target}")
        if len(values) % 2:
            raise ValueError("deform values must contain X/Y pairs")
        if target in white_targets and any(
            not math.isclose(values[index], 0.0, abs_tol=1e-9)
            for index in range(0, len(values), 2)
        ):
            raise ValueError(f"Eyewhite X deformation is prohibited: {target}")
        allowed_rows.add((parameter, target, "deform"))

    for removal in plan.get("removeBindings", []):
        allowed_rows.add(
            (int(removal["parameter"]), int(removal["target"]), str(removal["bindingName"]))
        )

    for edit in plan.get("staticZSort", []):
        if set(edit) != {"target", "value"}:
            raise ValueError("staticZSort entries may contain only target and value")

    return {
        "allowedRows": sorted(allowed_rows),
        "deformEditCount": len(plan.get("deformEdits", [])),
        "removeBindingCount": len(plan.get("removeBindings", [])),
        "staticZSortCount": len(plan.get("staticZSort", [])),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--njc", required=True, help="Resolved njc executable")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, help="Optional report JSON")
    parser.add_argument("--apply", action="store_true", help="Apply the validated plan")
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    summary = validate(plan)
    report: dict[str, Any] = {
        "schema": "nijigenerate-eye-blink-delta-plan-v1",
        "applied": False,
        "plan": args.plan.name,
        "summary": summary,
        "fileCommandOpenFileAvoided": True,
        "fileCommandSaveFileCalled": False,
    }

    if args.apply:
        before_hashes = binding_hashes(args.njc)
        before_rows = set(before_hashes)
        allowed_rows = {tuple(row) for row in summary["allowedRows"]}
        protected_before = {
            key: value for key, value in before_hashes.items() if key not in allowed_rows
        }

        for removal in plan.get("removeBindings", []):
            key = (
                int(removal["parameter"]),
                int(removal["target"]),
                str(removal["bindingName"]),
            )
            if key not in before_rows:
                continue
            tool(
                args.njc,
                "BindingCommand_RemoveBinding",
                {
                    "context": {
                        "parameters": [key[0]],
                        "bindings": [{"target": key[1], "name": key[2]}],
                    }
                },
            )

        for edit in plan.get("deformEdits", []):
            tool(
                args.njc,
                "ModelCommand_SetDeformBinding",
                {
                    "context": {
                        "parameters": [int(edit["parameter"])],
                        "nodes": [int(edit["target"])],
                        "parameterValue": edit["parameterValue"],
                    },
                    "bindingName": "deform",
                    "values": edit["values"],
                },
            )

        static_readback = []
        for edit in plan.get("staticZSort", []):
            target = int(edit["target"])
            tool(
                args.njc,
                "Inspector_Apply_ZSort",
                {"context": {"nodes": [target]}, "value": float(edit["value"])},
            )
            item = read_uri(args.njc, f"resource://nijigenerate/resources/{target}")["item"]
            static_readback.append({"target": target, "zsort": item["data"].get("zsort")})

        after_hashes = binding_hashes(args.njc)
        protected_after = {
            key: value for key, value in after_hashes.items() if key not in allowed_rows
        }
        if protected_before != protected_after:
            raise RuntimeError("unplanned binding-row or binding-resource change detected")
        report.update(
            {
                "applied": True,
                "saved": False,
                "protectedBindingRowsUnchanged": True,
                "protectedBindingResourcesUnchanged": True,
                "staticZSortReadback": static_readback,
            }
        )

    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
