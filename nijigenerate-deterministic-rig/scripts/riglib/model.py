"""Observe the current model through NJC public resources only.

This module never opens, parses, or writes INP/INX files. The pure in-memory
normalizer retains uncertainty about nominal geometry and rendered bounds.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from copy import deepcopy

from .data import json_digest


def _resource_payload(value):
    """Accept decoded NJC payloads or their public JSON-RPC resource envelope."""
    def reject_constant(value):
        raise ValueError(f"non-finite NJC resource JSON: {value}")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate NJC resource JSON key: {key}")
            result[key] = value
        return result

    if not isinstance(value, dict):
        raise ValueError("NJC resource response must be an object")
    if "error" in value or value.get("isError"):
        raise ValueError("NJC resource returned an error")
    if "result" in value:
        return _resource_payload(value["result"])
    if "contents" in value:
        contents = value["contents"]
        if not isinstance(contents, list) or len(contents) != 1:
            raise ValueError("NJC resource must return exactly one JSON content item")
        text = contents[0].get("text")
        if not isinstance(text, str):
            raise ValueError("NJC resource JSON text is missing")
        value = json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique)
        return _resource_payload(value)
    # Also rejects non-finite numbers in an already-decoded transport response.
    json.dumps(value, allow_nan=False)
    return value


def _uuid(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= 0xffffffff:
        raise ValueError(f"{label} must be a nonzero uint32")
    return value


def _discovery(client):
    payload = _resource_payload(client.find("*"))
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("NJC find response must contain an items array")
    nodes, parameters, seen = [], [], set()

    def visit(item, parent):
        if not isinstance(item, dict):
            raise ValueError("NJC discovery item must be an object")
        kind = item.get("typeId")
        if not isinstance(kind, str):
            raise ValueError("NJC discovery item typeId is missing")
        children = item.get("children")
        if children is None:
            children = []
        if not isinstance(children, list):
            raise ValueError("NJC discovery children must be an array")
        if kind == "Binding":
            # Binding IDs are not node IDs. Bindings are not silently summarized.
            return
        uid = _uuid(item.get("uuid"), "NJC discovery UUID")
        if uid in seen:
            raise ValueError(f"duplicate NJC resource UUID: {uid}")
        seen.add(uid)
        if not isinstance(item.get("name"), str):
            raise ValueError("NJC discovery name is missing")
        if kind == "Parameter":
            parameters.append({"uuid": uid, "name": item["name"]})
            # Public Parameter resources do not expose axes or bindings.
            return
        if not isinstance(item.get("data"), dict):
            raise ValueError("NJC discovery item is not a supported Node resource")
        nodes.append({"uuid": uid, "type": kind, "name": item["name"], "parent": parent})
        for child in children:
            visit(child, uid)

    for item in items:
        visit(item, None)
    if not nodes:
        raise ValueError("NJC has no active model nodes; open/import through NJC explicitly")
    if sum(node["parent"] is None for node in nodes) != 1:
        raise ValueError("NJC discovery must expose exactly one model root")
    return nodes, sorted(parameters, key=lambda item: item["uuid"])


def _capture_metadata(client, require_parameters):
    discovered, parameters = _discovery(client)
    if parameters and require_parameters:
        raise ValueError("NJC public Parameter resources omit axes/bindings; complete parameter metadata unavailable")
    resolved = {}
    for record in discovered:
        response = _resource_payload(client.read(record["uuid"]))
        item = response.get("item")
        if (not isinstance(item, dict) or item.get("typeId") != "Node"
                or item.get("uuid") != record["uuid"] or item.get("name") != record["name"]):
            raise ValueError("NJC Node identity changed or resource is unavailable")
        data = deepcopy(item.get("data"))
        if not isinstance(data, dict):
            raise ValueError("NJC Node resource omitted serialized data")
        for key in ("uuid", "name", "type", "enabled", "transform"):
            if key not in data:
                raise ValueError(f"NJC Node resource omitted required {key}")
        if any(data[key] != record[key] for key in ("uuid", "name", "type")):
            raise ValueError("NJC Node data identity differs from discovery")
        transform = data["transform"]
        if not isinstance(transform, dict) or not {"trans", "rot", "scale"} <= transform.keys():
            raise ValueError("NJC Node resource omitted complete base transform")
        if data["type"] == "Part":
            mesh = data.get("mesh")
            if not isinstance(mesh, dict) or not {"verts", "indices", "origin"} <= mesh.keys():
                raise ValueError("NJC Part resource omitted complete base mesh geometry")
        if data["type"] == "GridDeformer":
            if not {"grid_axis_x", "grid_axis_y", "depths"} <= data.keys():
                raise ValueError("NJC Grid resource omitted axes/depth geometry")
        if not isinstance(data["enabled"], bool):
            raise ValueError("NJC node enabled must be boolean")
        _trs(transform)
        _mesh(data, False)
        _grid(data, False)
        # Basics discovery supplies the hierarchy; detail reads do not request
        # the serializer's Children flag. Preserve that declared tree explicitly.
        data["children"] = []
        resolved[record["uuid"]] = data
    for record in discovered:
        if record["parent"] is not None:
            resolved[record["parent"]]["children"].append(resolved[record["uuid"]])
    root = next(record["uuid"] for record in discovered if record["parent"] is None)
    return {"nodes": resolved[root], "param": None if parameters else [],
            "public_parameter_identities": parameters}


def read_model_metadata(path=None, *, client=None, require_parameters=True,
                        expected_metadata_sha256=None):
    """Read the current live model through client.find/read, never a file.

    Two complete reads must match. This detects changes but is not an atomic
    snapshot or a proof of file identity. Parameter details are unavailable in
    the current public resource implementation; node-only callers may explicitly
    opt out of requiring them, receiving param=None and a completeness flag.
    """
    if path is not None:
        raise ValueError("model paths cannot be read here; open via NJC then observe the current model")
    if client is None or not callable(getattr(client, "find", None)) or not callable(getattr(client, "read", None)):
        raise ValueError("an explicit NJC client with find/read is required")
    if not isinstance(require_parameters, bool):
        raise ValueError("require_parameters must be boolean")
    first = _capture_metadata(client, require_parameters)
    second = _capture_metadata(client, require_parameters)
    fingerprint = json_digest(first)
    if json_digest(second) != fingerprint:
        raise ValueError("NJC model changed during snapshot acquisition")
    if expected_metadata_sha256 is not None and expected_metadata_sha256 != fingerprint:
        raise ValueError("NJC snapshot identity does not match expected_metadata_sha256")
    identities = first["public_parameter_identities"]
    return first, {
        "path": None, "transport": "njc", "container": "njc-public-resource-snapshot",
        "metadata_sha256": fingerprint, "hash_scope": "canonical_njc_public_metadata_snapshot",
        "parameter_count_observed": len(identities), "parameters_complete": not identities,
        "serialized_metadata_complete": False, "node_geometry_complete": True,
        "consistency": "two_identical_reads_not_atomic", "file_identity_verified": False,
        "texture_payload_read": False,
    }


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _vector(value, sizes, label):
    if not isinstance(value, list) or len(value) not in sizes:
        raise ValueError(f"{label} must have length {sorted(sizes)}")
    return [_number(v, label) for v in value]


def _identity():
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def _multiply(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4))
             for j in range(4)] for i in range(4)]


def _trs(transform):
    """T @ Rz @ Ry @ Rx @ S; nonzero engine rotation semantics are unverified."""
    if not isinstance(transform, dict):
        raise ValueError("node transform must be an object")
    t = _vector(transform.get("trans", [0, 0, 0]), {3}, "transform.trans")
    r = _vector(transform.get("rot", [0, 0, 0]), {3}, "transform.rot")
    s = _vector(transform.get("scale", [1, 1]), {2, 3}, "transform.scale")
    if len(s) == 2:
        s.append(1.0)
    cx, cy, cz = [math.cos(v) for v in r]
    sx, sy, sz = [math.sin(v) for v in r]
    rx = [[1, 0, 0, 0], [0, cx, -sx, 0], [0, sx, cx, 0], [0, 0, 0, 1]]
    ry = [[cy, 0, sy, 0], [0, 1, 0, 0], [-sy, 0, cy, 0], [0, 0, 0, 1]]
    rz = [[cz, -sz, 0, 0], [sz, cz, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    scale, translate = _identity(), _identity()
    for i in range(3):
        scale[i][i], translate[i][3] = s[i], t[i]
    matrix = _multiply(translate, _multiply(rz, _multiply(ry, _multiply(rx, scale))))
    return matrix, bool(any(r)), {"trans": t, "rot": r, "scale": s}


def _transform_point(matrix, point):
    p = [point[0], point[1], point[2] if len(point) > 2 else 0.0, 1.0]
    return [sum(matrix[i][j] * p[j] for j in range(4)) for i in range(3)]


def _bounds(points):
    if not points:
        return None
    return [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points)]


def _flat_pairs(values, label):
    if not isinstance(values, list) or len(values) % 2:
        raise ValueError(f"{label} must be a flat even-length XY array")
    return [[_number(values[i], label), _number(values[i + 1], label)]
            for i in range(0, len(values), 2)]


def _mesh(node, include_geometry):
    if "mesh" not in node:
        return None, []
    mesh = node["mesh"]
    if not isinstance(mesh, dict):
        raise ValueError("mesh must be an object")
    vertices = _flat_pairs(mesh.get("verts", []), "mesh.verts")
    indices = mesh.get("indices", [])
    if not isinstance(indices, list) or len(indices) % 3:
        raise ValueError("mesh.indices must be triangle indices")
    if any(isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(vertices)
           for i in indices):
        raise ValueError("mesh index is outside the vertex array")
    origin = _vector(mesh.get("origin", [0, 0]), {2, 3}, "mesh.origin")
    result = {
        "vertex_count": len(vertices), "triangle_count": len(indices) // 3,
        "vertices_sha256": json_digest(vertices), "indices_sha256": json_digest(indices),
        "local_bounds_xy": _bounds(vertices), "origin": origin,
        "origin_nonzero": bool(any(origin)), "origin_applied": False,
        "origin_semantics": "not_assumed; verts used directly for nominal bounds",
    }
    if include_geometry:
        result.update(vertices=vertices, indices=indices)
    return result, vertices


def _grid(node, include_geometry):
    if node.get("type") != "GridDeformer":
        return None, []
    axes = []
    for field in ("grid_axis_x", "grid_axis_y"):
        values = node.get(field, [])
        if not isinstance(values, list):
            raise ValueError(f"{field} must be an array")
        values = [_number(v, field) for v in values]
        if any(a >= b for a, b in zip(values, values[1:])):
            raise ValueError(f"{field} must be strictly increasing")
        axes.append(values)
    vertices = [[x, y] for y in axes[1] for x in axes[0]]
    depths = node.get("depths", [])
    if not isinstance(depths, list):
        raise ValueError("grid depths must be an array")
    depths = [_number(v, "grid.depths") for v in depths]
    if depths and len(depths) != len(vertices):
        raise ValueError("grid depth count differs from axis-product vertex count")
    result = {
        "columns": len(axes[0]), "rows": len(axes[1]),
        "axis_x": axes[0], "axis_y": axes[1],
        "vertex_count": len(vertices), "depth_count": len(depths),
        "depths_sha256": json_digest(depths),
        "depth_range": [min(depths), max(depths)] if depths else None,
        "dynamic": node.get("dynamic"), "formation": node.get("formation"),
        "local_bounds_xy": _bounds(vertices),
        "depth_order_assumed_for_geometry": False,
    }
    if include_geometry:
        result["depths"] = depths
    return result, vertices


def _parameter_summary(value):
    if not isinstance(value, dict):
        raise ValueError("parameter must be an object")
    result = {key: value.get(key) for key in
              ("uuid", "name", "is_vec2", "min", "max", "defaults", "axis_points", "merge_mode")}
    result["binding_count"] = len(value.get("bindings", []))
    result["axis_points_semantics"] = "serialized normalized breakpoints; actual=min+(max-min)*point"
    dimension = 2 if value.get("is_vec2") else 1
    low, high, axes = value.get("min", []), value.get("max", []), value.get("axis_points", [])
    result["actual_axis_values"] = None
    if (isinstance(low, list) and isinstance(high, list) and isinstance(axes, list)
            and len(low) >= dimension and len(high) >= dimension and len(axes) >= dimension):
        actual = []
        for k in range(dimension):
            a, b = _number(low[k], "parameter.min"), _number(high[k], "parameter.max")
            if b < a or not isinstance(axes[k], list):
                raise ValueError("invalid parameter axis")
            points = [_number(x, "parameter.axis_points") for x in axes[k]]
            if any(not 0 <= x <= 1 for x in points):
                raise ValueError("parameter normalized key is outside [0,1]")
            actual.append([a + (b - a) * x for x in points])
        result["actual_axis_values"] = actual
    return result


def observe_model(path=None, include_geometry=True, *, client=None,
                  require_parameters=True, expected_metadata_sha256=None):
    """Observe current NJC resources; never open or directly inspect a file."""
    data, source = read_model_metadata(path, client=client,
                                      require_parameters=require_parameters,
                                      expected_metadata_sha256=expected_metadata_sha256)
    return observe_metadata(data, source, include_geometry=include_geometry)


def observe_metadata(data, source, *, include_geometry=True):
    """Pure in-memory normalization, also usable by transport-stub tests.

    This is not a model-file reader. The caller must supply the source identity;
    the normalizer does not invent NJC or file provenance for arbitrary data.
    """
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), dict):
        raise ValueError("model metadata must contain a nodes object")
    if not isinstance(source, dict):
        raise ValueError("explicit source provenance is required")
    if source.get("metadata_sha256") != json_digest(data):
        raise ValueError("metadata source hash mismatch")
    source = deepcopy(source)
    nodes, seen = [], set()

    def visit(node, parent, parent_matrix, ancestors, grid_ancestors, deformers,
              inherited_enabled, inherited_unknown, inherited_rotation):
        if not isinstance(node, dict):
            raise ValueError("node must be an object")
        uuid = node.get("uuid")
        if isinstance(uuid, bool) or not isinstance(uuid, int) or not 0 <= uuid <= 0xffffffff:
            raise ValueError("node UUID must be a uint32")
        if uuid in seen:
            raise ValueError(f"duplicate node UUID: {uuid}")
        seen.add(uuid)
        if not isinstance(node.get("name", ""), str) or not isinstance(node.get("type"), str):
            raise ValueError("node name/type must be strings")
        enabled = node.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("node enabled must be boolean")
        transform = node.get("transform", {})
        reasons = list(inherited_unknown)
        try:
            local, rotated, normalized = _trs(transform)
            world = _multiply(parent_matrix, local) if parent_matrix is not None else None
        except ValueError as error:
            world, rotated, normalized = None, False, None
            reasons.append(str(error))
        if node.get("lockToRoot"):
            reasons.append("LockToRoot evaluation is not implemented")
            world = None
        if node.get("pinToMesh"):
            reasons.append("pinToMesh evaluation is not implemented")
            world = None
        rotation_uncertain = inherited_rotation or rotated
        mesh, mesh_vertices = _mesh(node, include_geometry)
        grid, grid_vertices = _grid(node, include_geometry)
        vertices = mesh_vertices if mesh is not None else grid_vertices
        nominal = _bounds([_transform_point(world, p) for p in vertices]) if world is not None else None
        bounds_reasons = list(reasons)
        if rotation_uncertain:
            bounds_reasons.append("nonzero rotation: radians and T@Rz@Ry@Rx@S convention unverified against application")
        if mesh and mesh["origin_nonzero"]:
            bounds_reasons.append("nonzero mesh.origin is preserved but not applied; origin semantics unverified")
        if deformers:
            bounds_reasons.append("inherited deformers are not evaluated")
        bounds_reasons.append("parameter bindings, physics and render-time deformation are not evaluated")
        entry = {
            "uuid": uuid, "name": node.get("name", ""), "type": node["type"],
            "parent": parent, "ancestors": list(ancestors),
            "ancestor_grids": list(grid_ancestors),
            "closest_ancestor_grid": grid_ancestors[-1] if grid_ancestors else None,
            "ancestor_deformers": list(deformers),
            "enabled_local": enabled, "enabled_inherited": inherited_enabled,
            "enabled_effective": inherited_enabled and enabled,
            "transform": transform, "normalized_transform": normalized,
            "lock_to_root": node.get("lockToRoot", False), "pin_to_mesh": node.get("pinToMesh"),
            "mesh": mesh, "grid": grid,
            "texture_references": node.get("textures") if node["type"] == "Part" else None,
            "draw_properties": {key: node[key] for key in
                                ("zsort", "opacity", "blend_mode", "mask_threshold") if key in node},
            "bounds": {
                "local_xy": _bounds(vertices), "nominal_world_xy": nominal,
                "status": "unknown" if world is None else (
                    "nominal_affine_unverified_rotation" if rotation_uncertain else "nominal_base_affine"),
                "units": "serialized-model-units", "rendered_world_exact": False,
                "rendered_world_xy": None, "reasons": bounds_reasons,
            },
            "nominal_world_matrix": world,
        }
        nodes.append(entry)
        children = node.get("children", [])
        if not isinstance(children, list):
            raise ValueError("node children must be an array")
        next_grids = grid_ancestors + ([uuid] if node["type"] == "GridDeformer" else [])
        is_deformer = "Deformer" in node["type"] or node["type"] in {"DepthBone", "DepthRigRoot"}
        next_deformers = deformers + ([uuid] if is_deformer else [])
        for child in children:
            visit(child, uuid, world, ancestors + [uuid], next_grids, next_deformers,
                  inherited_enabled and enabled, reasons, rotation_uncertain)

    visit(data["nodes"], None, _identity(), [], [], [], True, [], False)
    parameters = data.get("param", [])
    parameters_complete = source.get("parameters_complete", True)
    if not parameters_complete and parameters is not None:
        raise ValueError("unavailable parameter details must be null, not invented data")
    # Fresh PSD imports serialize an empty parameter collection as null.
    if parameters is None:
        parameters = []
    if not isinstance(parameters, list):
        raise ValueError("model param must be an array")
    summaries = [_parameter_summary(p) for p in parameters]
    if not parameters_complete:
        identities = data.get("public_parameter_identities")
        if not isinstance(identities, list) or len(identities) != source.get("parameter_count_observed"):
            raise ValueError("incomplete parameter identity census")
        summaries = [{"uuid": p["uuid"], "name": p["name"], "details_available": False,
                      "binding_count": None, "actual_axis_values": None,
                      "unavailable_reason": "NJC public Parameter resource omits axes/bindings"}
                     for p in identities]
    return {
        "schema_version": "rig-model-observation/1", "source": source,
        "node_count": len(nodes), "node_counts": dict(sorted(Counter(n["type"] for n in nodes).items())),
        "nodes": nodes, "parameter_count": len(summaries), "parameters": summaries,
        "parameters_complete": parameters_complete,
        "assumptions": [
            "Nominal bounds compare serialized base geometry only, never current rendered geometry.",
            "Full affine chains use T@Rz@Ry@Rx@S, column vectors and assumed radians; nonzero rotation is flagged.",
            "Grid depth arrays are observed but not silently converted into a full 3D evaluated surface.",
            "Part mesh origin is preserved, not added/subtracted without verified semantics.",
            "Names and shared Grid ancestry are candidate structural evidence, not proof of semantic roles.",
        ],
        "model_loaded": False, "model_modified": False,
        "current_live_model_observed": source.get("transport") == "njc",
    }
