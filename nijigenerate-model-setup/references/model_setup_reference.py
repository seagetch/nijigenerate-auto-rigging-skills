#!/usr/bin/env python3
"""Reference command patterns for nijigenerate model setup.

This script is intentionally a scaffold. Replace UUIDs, names, and tool payloads
after inspecting the active model with the resolved `njc` executable.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(os.environ.get("NIJIGENERATE_REPO", ".")).resolve()


def resolve_njc():
    explicit = os.environ.get("NJC_PATH")
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if path.is_file():
            return str(path)
        raise RuntimeError(f"NJC_PATH does not point to a file: {path}")
    found = shutil.which("njc")
    if found:
        return found
    raise RuntimeError("njc was not found. Set NJC_PATH or add njc to PATH.")


def call(tool, payload=None):
    cmd = [resolve_njc(), "tools", "call", tool]
    if payload is not None:
        cmd += ["--json", json.dumps(payload, ensure_ascii=False)]
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=True).stdout


def set_grid_automesh(node_uuid, x_segments, y_segments, margin=0.1, mask_threshold=0.5):
    """GridDeformer AutoMesh pattern. Read back actual axes after applying."""
    context = {"nodes": [node_uuid]}
    call("AutoMesh_SetSimple_grid_nijigenerate_commands_base_Command", {
        "context": context,
        "mask_threshold": mask_threshold,
        "x_segments": x_segments,
        "y_segments": y_segments,
        "margin": margin,
    })
    call("AutoMesh_Apply_grid", {"context": context})


def set_parameter_keypoint(param_uuid, value):
    call("ParameditCommand_SetParameterKeypoint", {
        "context": {
            "parameters": [param_uuid],
            "armedParameters": [param_uuid],
            "parameterValue": value,
        }
    })


def set_deform_binding(param_uuid, node_uuid, value, deform_values):
    call("ModelCommand_SetDeformBinding", {
        "context": {
            "parameters": [param_uuid],
            "armedParameters": [param_uuid],
            "parameterValue": value,
            "nodes": [node_uuid],
        },
        "bindingName": "deform",
        "values": deform_values,
    })


def capture_after_keypoint(param_uuid, value, filename):
    set_parameter_keypoint(param_uuid, value)
    call("ViewCommand_SaveScreenshot", {"filename": filename})


def verify_symmetric_axis(axis, center=0.0, tolerance=1e-4):
    """Return pairs whose x coordinates are not mirrored around center."""
    bad = []
    for i in range(len(axis) // 2):
        left = axis[i]
        right = axis[-1 - i]
        if abs((left + right) / 2.0 - center) > tolerance:
            bad.append((i, left, len(axis) - 1 - i, right))
    if len(axis) % 2:
        mid = axis[len(axis) // 2]
        if abs(mid - center) > tolerance:
            bad.append(("center", mid))
    return bad


def main():
    raise SystemExit(
        "Reference only. Inspect the active model, replace UUIDs/payloads, "
        "then call the needed helpers explicitly."
    )


if __name__ == "__main__":
    main()
