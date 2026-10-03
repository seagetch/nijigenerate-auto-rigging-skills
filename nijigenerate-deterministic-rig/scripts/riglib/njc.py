"""Limited deterministic export of sampled carrier depth and deformation arrays.

This module does not provide a live NJC adapter. Its optional generic journal
runner requires an independently implemented backend with complete, settled
state snapshots. NJC has no confirmed CAS/transaction guarantee: pre-read and
readback checks detect conflicts; they cannot make writes atomic or undo them.
File opening, saving, node creation and arbitrary commands are unsupported.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
from typing import Protocol

from .data import json_digest


STATE_SCHEMA = "rig-njc-state/1"
PLAN_SCHEMA = "rig-njc-plan/1"
SAMPLED_SCHEMA = "rig-njc-sampled/1"
DEPTH_TOOL = "DepthMapCommand_SetDepths"
DEFORM_TOOL = "ModelCommand_SetDeformBinding"
_HASH = re.compile(r"^[0-9a-f]{64}$")


class PlanError(ValueError):
    """An input, correspondence or precondition is not explicit/consistent."""


class ExecutionStopped(RuntimeError):
    def __init__(self, message, journal_path=None):
        super().__init__(message)
        self.journal_path = str(journal_path) if journal_path else None


class SnapshotBackend(Protocol):
    """Contract only; there is intentionally no live implementation here.

    snapshot() must return all carriers/parameter keys plus protected model and
    driver state in a consistent, evaluated snapshot. ``complete=True`` is the
    backend author's claim; this module cannot prove an omitted field exists.
    protected_state must cover all topology, hierarchy, bindings, transforms,
    parameter metadata, links, draw state and settings not represented directly.
    Transport timestamps and revision counters belong in adapter provenance,
    not canonical state. No other model or driver state may be omitted.
    call() must await completion or raise; exceptions may still follow mutation.
    """
    def snapshot(self) -> dict: ...
    def call(self, tool_name: str, arguments: dict): ...


def _require(condition, message):
    if not condition:
        raise PlanError(message)


def _number(value, label):
    _require(not isinstance(value, bool) and isinstance(value, (int, float))
             and math.isfinite(value), f"{label} must be finite")
    value = float(value)
    return 0.0 if value == 0 else value


def _uuid(value, label):
    _require(not isinstance(value, bool) and isinstance(value, int)
             and 0 <= value <= 0xffffffff, f"{label} must be a uint32")
    return value


def _hash(value, label):
    _require(isinstance(value, str) and _HASH.fullmatch(value), f"{label} must be SHA-256 hex")
    return value


def _numbers(values, count, label):
    _require(isinstance(values, list) and len(values) == count,
             f"{label} must contain the complete {count}-value array")
    return [_number(value, label) for value in values]


def _vertices(values):
    _require(isinstance(values, list) and len(values) > 0, "carrier vertices must be nonempty")
    return [_numbers(pair, 2, "carrier vertex XY") for pair in values]


def vertices_sha256(vertices):
    """Fingerprint actual ordered carrier XY vertices, not template vertices."""
    return json_digest(_vertices(vertices))


def _calibration(value, parent_hash):
    _require(isinstance(value, dict), "axis_calibration must be an object")
    result = deepcopy(value)
    _require(result.get("status") == "verified", "axis calibration must be verified")
    _require(result.get("frame") == "carrier-local", "axis calibration frame must be carrier-local")
    _require(result.get("parent_state_sha256") == parent_hash,
             "axis calibration does not match carrier parent state")
    for field in ("xy_units", "depth_units"):
        _require(isinstance(result.get(field), str) and result[field].strip(), f"calibration {field} is required")
    matrix = result.get("world_to_local_xy")
    _require(isinstance(matrix, list) and len(matrix) == 3, "world_to_local_xy must be a 3x3 affine matrix")
    matrix = [_numbers(row, 3, "world_to_local_xy row") for row in matrix]
    _require(matrix[2] == [0.0, 0.0, 1.0], "world_to_local_xy must be affine")
    _require(abs(matrix[0][0]*matrix[1][1] - matrix[0][1]*matrix[1][0]) > 1e-15,
             "world_to_local_xy is singular")
    result["world_to_local_xy"] = matrix
    result["depth_scale"] = _number(result.get("depth_scale"), "depth_scale")
    _require(result["depth_scale"] > 0, "depth_scale must be positive")
    _require(type(result.get("depth_sign")) is int and result["depth_sign"] in (-1, 1),
             "depth_sign must be explicit -1 or 1")
    return result


def axis_calibration_sha256(calibration):
    """Hash the normalized verified calibration, including parent identity."""
    parent = _hash(calibration.get("parent_state_sha256"), "parent_state_sha256")
    return json_digest(_calibration(calibration, parent))


def normalize_state(snapshot):
    """Validate the explicit complete-state adapter contract, retaining extras."""
    _require(isinstance(snapshot, dict), "snapshot must be an object")
    state = deepcopy(snapshot)
    _require(state.get("schema_version") == STATE_SCHEMA, f"snapshot schema must be {STATE_SCHEMA}")
    _require(isinstance(state.get("model_id"), str) and state["model_id"].strip(), "model_id is required")
    _require(state.get("complete") is True, "incomplete state cannot guard writes")
    _require(state.get("evaluation_settled") is True, "state evaluation must be settled")
    _require(state.get("drivers_enabled") is False, "drivers must already be disabled")
    _require(isinstance(state.get("protected_state"), dict), "full protected_state is required")
    for field in ("carriers", "parameters", "deform_keys"):
        _require(isinstance(state.get(field), list), f"snapshot {field} must be an array")
    carriers = {}
    for carrier in state["carriers"]:
        _require(isinstance(carrier, dict), "carrier must be an object")
        uuid = _uuid(carrier.get("uuid"), "carrier UUID")
        _require(uuid not in carriers, "duplicate carrier UUID")
        _require(carrier.get("node_type") in ("GridDeformer", "Part"), "unsupported carrier node type")
        _require(type(carrier.get("depth_mapped")) is bool, "depth_mapped capability must be explicit")
        carrier["vertices"] = _vertices(carrier.get("vertices"))
        count = len(carrier["vertices"])
        if carrier["depth_mapped"]:
            carrier["depths"] = _numbers(carrier.get("depths"), count, "existing carrier depths")
        else:
            _require(carrier.get("depths") is None, "non-DepthMapped carrier must have depths=null")
        parent_hash = _hash(carrier.get("parent_state_sha256"), "parent_state_sha256")
        carrier["axis_calibration"] = _calibration(carrier.get("axis_calibration"), parent_hash)
        carriers[uuid] = carrier
    parameters = {}
    for parameter in state["parameters"]:
        _require(isinstance(parameter, dict), "parameter must be an object")
        uuid = _uuid(parameter.get("uuid"), "parameter UUID")
        _require(uuid not in parameters, "duplicate parameter UUID")
        axes = parameter.get("actual_axes")
        _require(isinstance(axes, list) and len(axes) in (1, 2), "actual_axes must contain 1 or 2 axes")
        normalized_axes = []
        for axis in axes:
            _require(isinstance(axis, list) and axis, "actual axis must be nonempty")
            values = [_number(x, "actual axis") for x in axis]
            _require(all(a < b for a, b in zip(values, values[1:])), "actual axis values must increase")
            normalized_axes.append(values)
        parameter["actual_axes"] = normalized_axes
        parameters[uuid] = parameter
    keys = set()
    for binding in state["deform_keys"]:
        _require(isinstance(binding, dict), "deform key must be an object")
        target = _uuid(binding.get("target"), "deform target")
        parameter = _uuid(binding.get("parameter"), "deform parameter")
        _require(target in carriers and parameter in parameters, "deform key references unknown target/parameter")
        axes = parameters[parameter]["actual_axes"]
        value = _numbers(binding.get("actual_parameter_value"), len(axes), "actual_parameter_value")
        _require(all(v in axis for v, axis in zip(value, axes)), "deform key is not an existing actual parameter key")
        binding["actual_parameter_value"] = value
        _require(type(binding.get("is_set")) is bool, "deform key is_set must be explicit")
        binding["values"] = _numbers(binding.get("values"), 2*len(carriers[target]["vertices"]), "existing deform values")
        address = (target, parameter, tuple(value))
        _require(address not in keys, "duplicate deform key address")
        keys.add(address)
    state["carriers"].sort(key=lambda x: x["uuid"])
    state["parameters"].sort(key=lambda x: x["uuid"])
    state["deform_keys"].sort(key=lambda x: (x["target"], x["parameter"], x["actual_parameter_value"]))
    try:
        json_digest(state)
    except (TypeError, ValueError) as error:
        raise PlanError(f"state is not finite JSON: {error}") from error
    return state


def _context(target, parameter=None, value=None):
    return {"nodes": [target], "parameters": [] if parameter is None else [parameter],
            "parameterValue": [] if value is None else value,
            "armedParameters": [], "bindings": [] if parameter is None else
            [{"target": target, "name": "deform"}]}


def _compile_step(state, sampled):
    _require(isinstance(sampled, dict), "sampled target must be an object")
    _require(not (set(sampled) - {"kind", "target", "expected_vertices_sha256", "sampling",
                                  "values", "parameter", "actual_parameter_value", "allowed_vertices",
                                  "expected_changed_vertices", "provenance"}), "unknown sampled-target field")
    kind = sampled.get("kind")
    _require(kind in ("depth", "deform"), "only depth and deform export are supported")
    target = _uuid(sampled.get("target"), "sampled target")
    carriers = {item["uuid"]: item for item in state["carriers"]}
    _require(target in carriers, "sampled target has no existing carrier")
    carrier = carriers[target]
    count = len(carrier["vertices"])
    _require(sampled.get("expected_vertices_sha256") == vertices_sha256(carrier["vertices"]),
             "carrier vertex count/order/coordinates differ from sampled correspondence")
    sampling = sampled.get("sampling")
    _require(isinstance(sampling, dict), "sampling contract is required")
    _require(sampling.get("vertex_order") == "carrier", "values must already be sampled in carrier order")
    _require(sampling.get("frame") == "carrier-local", "sampled values must be carrier-local")
    semantics = "absolute-depth" if kind == "depth" else "deform-offsets"
    _require(sampling.get("value_semantics") == semantics,
             f"sampled value_semantics must explicitly be {semantics}")
    calibration = carrier["axis_calibration"]
    _require(sampling.get("axis_calibration_sha256") == axis_calibration_sha256(calibration),
             "sampling axis calibration differs from current carrier")
    units = calibration["depth_units" if kind == "depth" else "xy_units"]
    _require(sampling.get("units") == units, "sampled value units do not match carrier calibration")
    before_hash = json_digest(state)
    if kind == "depth":
        _require(carrier["depth_mapped"], "depth writes require confirmed DepthMapped capability")
        _require("parameter" not in sampled and "actual_parameter_value" not in sampled,
                 "depth export must not carry an implicit parameter context")
        values = _numbers(sampled.get("values"), count, "sampled depths")
        old = carrier["depths"]
        moved = [i for i in range(count) if old[i] != values[i]]
        arguments = {"context": _context(target), "target": target, "depths": values}
        tool, address = DEPTH_TOOL, (kind, target)
        carrier["depths"] = values
    else:
        parameter = _uuid(sampled.get("parameter"), "parameter")
        parameters = {p["uuid"]: p for p in state["parameters"]}
        _require(parameter in parameters, "deform parameter does not exist")
        axes = parameters[parameter]["actual_axes"]
        actual = _numbers(sampled.get("actual_parameter_value"), len(axes), "actual_parameter_value")
        _require(all(v in axis for v, axis in zip(actual, axes)),
                 "actual_parameter_value must match an existing key, not an index")
        matches = [key for key in state["deform_keys"] if key["target"] == target
                   and key["parameter"] == parameter and key["actual_parameter_value"] == actual]
        _require(len(matches) == 1, "existing deform binding/key state is required; implicit binding creation unsupported")
        binding = matches[0]
        values = _numbers(sampled.get("values"), count*2, "sampled deformation offsets")
        old = binding["values"]
        moved = [i for i in range(count) if old[2*i:2*i+2] != values[2*i:2*i+2]]
        arguments = {"context": _context(target, parameter, actual), "bindingName": "deform", "values": values}
        tool, address = DEFORM_TOOL, (kind, target, parameter, tuple(actual))
        binding["values"], binding["is_set"] = values, True
    allowed = sampled.get("allowed_vertices", list(range(count)))
    _require(isinstance(allowed, list) and all(type(i) is int and 0 <= i < count for i in allowed)
             and len(set(allowed)) == len(allowed), "allowed_vertices must be distinct valid indices")
    _require(set(moved) <= set(allowed), "values change vertices outside the explicit allowed subset")
    if "expected_changed_vertices" in sampled:
        _require(type(sampled["expected_changed_vertices"]) is int
                 and sampled["expected_changed_vertices"] == len(moved), "changed vertex count does not match request")
    return {
        "tool": tool, "arguments": arguments,
        "before_sha256": before_hash, "after_sha256": json_digest(state),
        "carrier_vertex_count": count, "carrier_vertices_sha256": vertices_sha256(carrier["vertices"]),
        "changed_vertices": moved, "changed_vertex_count": len(moved),
    }, address


def export_plan(snapshot, sampled_targets):
    """Compile complete pre-sampled arrays; never resample, infer or call NJC.

    sampled_targets may be a list or {schema_version: rig-njc-sampled/1,
    targets: [...]}. Each target specifies kind, UUID, values, vertex hash and
    sampling {vertex_order: carrier, frame: carrier-local, units,
    value_semantics: absolute-depth|deform-offsets, axis_calibration_sha256}.
    Deform additionally requires a parameter UUID
    and actual_parameter_value, exactly matching an existing key.
    """
    baseline = normalize_state(snapshot)
    if isinstance(sampled_targets, dict):
        _require(sampled_targets.get("schema_version") == SAMPLED_SCHEMA, "invalid sampled-target schema")
        sampled_targets = sampled_targets.get("targets")
    _require(isinstance(sampled_targets, list) and sampled_targets, "sampled targets must be nonempty")
    sampled_targets = deepcopy(sampled_targets)
    expected = deepcopy(baseline)
    commands, addresses = [], set()
    for sampled in sampled_targets:
        command, address = _compile_step(expected, sampled)
        _require(address not in addresses, "duplicate write address in one plan")
        addresses.add(address)
        commands.append(command)
    plan = {
        "schema_version": PLAN_SCHEMA, "model_id": baseline["model_id"],
        "baseline": baseline, "sampled_targets": sampled_targets, "commands": commands,
        "initial_state_sha256": json_digest(baseline), "final_state_sha256": json_digest(expected),
        "guarantees": {"atomic": False, "compare_and_swap": False,
                       "full_pre_read_and_readback_required": True,
                       "blind_retry_allowed": False, "automatic_rollback": False},
        "implementation_boundary": "exporter, validator and generic journal runner only; no live NJC state adapter",
        "supported_tools": [DEPTH_TOOL, DEFORM_TOOL],
    }
    plan["plan_id"] = json_digest(plan)
    return plan


def validate_plan(plan):
    """Regenerate commands from the contract; arbitrary tool/context edits fail."""
    _require(isinstance(plan, dict) and plan.get("schema_version") == PLAN_SCHEMA, "invalid plan schema")
    expected = export_plan(plan.get("baseline"), plan.get("sampled_targets"))
    _require(plan == expected, "plan differs from deterministic compilation or plan hash")
    return {"plan_id": expected["plan_id"], "command_count": len(expected["commands"]),
            "atomic": False, "live_adapter_provided": False}


def _write_journal(path, receipt):
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def execute_plan(plan, backend: SnapshotBackend, journal_dir):
    """Generic backend runner, not a live apply adapter.

    An attempted-write failure freezes this model's cooperative lock and saves
    observed state. No further commands, blind retries or rollback are issued.
    The lock does not prevent GUI edits or writers outside this runner. There
    remains a race between every snapshot and command because NJC has no CAS.
    """
    validate_plan(plan)
    folder = Path(journal_dir).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (plan["plan_id"] + ".json")
    lock = folder / ("model-" + json_digest(plan["model_id"]) + ".lock")
    _require(not path.exists(), "plan already attempted; inspect journal instead of retrying")
    try:
        with lock.open("x", encoding="utf-8") as stream:
            json.dump({"model_id": plan["model_id"], "plan_id": plan["plan_id"]}, stream)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise ExecutionStopped("model runner is active or frozen; inspect its lock/journal", lock) from error
    receipt = {
        "schema_version": "rig-njc-receipt/1", "plan_id": plan["plan_id"],
        "model_id": plan["model_id"], "status": "reserved", "frozen": False,
        "atomic": False, "compare_and_swap": False, "events": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    attempted_write = False
    journal_reserved = False

    def read_state():
        raw = backend.snapshot()
        try:
            return normalize_state(raw)
        except Exception as error:
            receipt["snapshot_validation_error"] = f"{type(error).__name__}: {error}"
            try:
                json_digest(raw)
                receipt["observed_unvalidated_state"] = raw
            except (ValueError, TypeError):
                receipt["observed_unvalidated_state"] = None
                receipt["snapshot_serialization_error"] = "backend state is not finite JSON"
            raise
    try:
        # Exclusive file reservation makes prior partial/failed attempts visible.
        with path.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        journal_reserved = True
        expected = deepcopy(plan["baseline"])
        for index, (sampled, command) in enumerate(zip(plan["sampled_targets"], plan["commands"])):
            current = read_state()
            if json_digest(current) != command["before_sha256"]:
                receipt["observed_state"] = current
                raise PlanError("pre-state changed; foreign or stale state detected")
            receipt["status"] = "before_command"
            receipt["events"].append({"index": index, "stage": "before_command", "state_sha256": json_digest(current)})
            _write_journal(path, receipt)
            attempted_write = True
            call_error = None
            try:
                response = backend.call(command["tool"], deepcopy(command["arguments"]))
                if isinstance(response, dict) and response.get("isError"):
                    call_error = RuntimeError("backend tool returned isError")
            except Exception as error:
                call_error = error
            _compile_step(expected, sampled)
            # Read even when the command reported an error: it may have mutated.
            observed = read_state()
            receipt["events"].append({"index": index, "stage": "after_command", "state_sha256": json_digest(observed)})
            if call_error is not None or json_digest(observed) != command["after_sha256"]:
                receipt["observed_state"] = observed
                if call_error is not None:
                    raise RuntimeError(f"command outcome requires inspection: {call_error}") from call_error
                raise PlanError("readback differs from exact expected state; partial or foreign change")
            _write_journal(path, receipt)
        # A final settled read also detects changes after the last per-call read.
        final = read_state()
        if json_digest(final) != plan["final_state_sha256"]:
            receipt["observed_state"] = final
            raise PlanError("final state changed after readback")
        receipt.update(status="verified", final_state_sha256=json_digest(final),
                       completed_at=datetime.now(timezone.utc).isoformat())
        _write_journal(path, receipt)
        lock.unlink()
        return {**receipt, "journal_path": str(path), "live_adapter_provided": False}
    except Exception as error:
        receipt.update(status="frozen" if attempted_write else "rejected_before_write",
                       frozen=attempted_write, error=f"{type(error).__name__}: {error}",
                       automatic_retry_allowed=False, automatic_rollback_attempted=False)
        try:
            if journal_reserved:
                _write_journal(path, receipt)
        finally:
            if not attempted_write and lock.exists():
                lock.unlink()
        raise ExecutionStopped(str(error), path) from error
