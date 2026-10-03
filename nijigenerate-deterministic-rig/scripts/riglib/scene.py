"""Register observed Parts into shared fitted surfaces; evaluate nominal scenes.

A scene is a proposed replacement surface model, not an evaluator for imported
Grid bindings, physics, mesh origins, or live application state. No I/O or NJC
calls occur here. Parent relationships and image-to-model registration are
explicit; native Part ancestry is never silently promoted into physical skin.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

import numpy as np

from .data import json_digest
from .geometry import (
    GeometryError, apply_local_corrections, evaluate_depth, inverse_grid,
    rotation_matrix, rotate_points, sample_grid,
)
from .pipeline import pose_dict, verify_fit


def _array(value, shape, label):
    try:
        data = np.asarray(value, dtype=float)
    except (ValueError, TypeError) as exc:
        raise GeometryError(f"{label} must be numeric") from exc
    if data.shape != shape or not np.all(np.isfinite(data)):
        raise GeometryError(f"{label} must be finite with shape {shape}")
    return data


def _similarity(matrix, depth_origin=0.0):
    source = _array(matrix, (3, 3), "source_to_model")
    if not np.allclose(source[2], [0, 0, 1], rtol=0, atol=1e-12):
        raise GeometryError("source_to_model must be affine")
    a = source[:2, :2]
    scale = float(np.linalg.norm(a[:, 0]))
    if scale <= 0 or np.linalg.det(a) <= 0:
        raise GeometryError("source_to_model must be an orientation-preserving similarity")
    if not np.allclose(a.T @ a, scale**2*np.eye(2), rtol=1e-8, atol=scale**2*1e-12):
        raise GeometryError("source_to_model must have uniform scale and no shear")
    depth_origin = float(depth_origin)
    if not np.isfinite(depth_origin):
        raise GeometryError("depth_origin must be finite model units")
    world = np.eye(4)
    world[:2, :2], world[:2, 3], world[2, 2], world[2, 3] = (
        a, source[:2, 2], scale, depth_origin,
    )
    return source, world, scale


def _world_matrix(node):
    if node.get("bounds", {}).get("status") in {None, "unknown"}:
        raise GeometryError(f"Part {node['uuid']} has unknown nominal bounds")
    matrix = _array(node.get("nominal_world_matrix"), (4, 4), "nominal_world_matrix")
    if not np.allclose(matrix[3], [0, 0, 0, 1], rtol=0, atol=1e-12):
        raise GeometryError("nominal_world_matrix must be affine")
    if np.linalg.cond(matrix[:3, :3]) > 1e12:
        raise GeometryError("nominal_world_matrix is singular/ill-conditioned")
    mesh = node.get("mesh")
    if not isinstance(mesh, Mapping) or "vertices" not in mesh:
        raise GeometryError(f"Part {node['uuid']} observation needs mesh.vertices")
    if mesh.get("origin_nonzero") and not mesh.get("origin_applied"):
        raise GeometryError("nonzero mesh origin has unverified semantics")
    vertices = np.asarray(mesh["vertices"], dtype=float)
    if vertices.ndim != 2 or vertices.shape[1] != 2 or not np.all(np.isfinite(vertices)):
        raise GeometryError("mesh.vertices must be finite Nx2 local coordinates")
    if not len(vertices):
        raise GeometryError("empty Part mesh cannot be registered")
    if mesh.get("vertex_count", len(vertices)) != len(vertices):
        raise GeometryError("Part vertex_count disagrees with mesh.vertices")
    return matrix, vertices


def _transform(matrix, xyz):
    values = np.column_stack((xyz, np.ones(len(xyz)))) @ matrix.T
    if not np.all(np.isfinite(values)):
        raise GeometryError("non-finite transformed coordinates")
    return values[:, :3]


def _assignments(structure):
    raw = structure.get("part_assignments", {})
    entries = []
    if isinstance(raw, Mapping):
        entries = list(raw.items())
    elif isinstance(raw, list):
        for row in raw:
            if not isinstance(row, Mapping) or "part" not in row or "surface" not in row:
                raise GeometryError("each Part assignment requires part and surface")
            entries.append((row["part"], row["surface"]))
    else:
        raise GeometryError("part_assignments must be a mapping or assignment list")
    result = {}
    for part, surface in entries:
        part, surface = str(part), str(surface)
        if part in result:
            raise GeometryError(f"duplicate Part assignment {part}")
        result[part] = surface
    return result


def _ordered_surfaces(surfaces):
    ordered, visiting, complete = [], set(), set()

    def visit(sid):
        if sid in visiting:
            raise GeometryError("cycle in explicit surface parent graph")
        if sid in complete:
            return
        visiting.add(sid)
        parent = surfaces[sid]["parent"]
        if parent is not None:
            if parent not in surfaces:
                raise GeometryError(f"surface {sid} references missing parent {parent}")
            visit(parent)
        visiting.remove(sid)
        complete.add(sid)
        ordered.append(sid)

    for sid in sorted(surfaces):
        visit(sid)
    return ordered


def _depth_at(fit, uv):
    operators = fit["template"]["geometry"]["operators"]
    scale = float(fit["depth_scale"])
    if not np.isfinite(scale) or scale <= 0:
        raise GeometryError("fit depth_scale must be positive source-pixel units")
    if any(op.get("type") == "host_offset" for op in operators):
        # The signed fit contains sampled host data and provenance. Do not read a
        # path or silently supply a zero host. Reuse this explicitly baked field.
        if fit.get("host") is None:
            raise GeometryError("host-dependent fit has no recorded host provenance")
        mesh = fit["mesh"]
        depth = np.asarray(fit["depth"], dtype=float)
        if depth.size != len(mesh["v_lines"])*len(mesh["u_lines"]):
            raise GeometryError("host fit depth grid size mismatch")
        values = sample_grid(depth.reshape(len(mesh["v_lines"]), len(mesh["u_lines"])),
                             mesh["u_lines"], mesh["v_lines"], uv)
        return values, "sampled_signed_host_fit"
    values = evaluate_depth(uv, operators, fit["parameters"])*scale
    return values, "evaluated_shared_template"


def register_scene(model_observation, structure, surface_specs):
    """Register all assigned Parts into shared surfaces once.

    surface_specs[sid] = {fit: inline rig-fit/1, source_to_model: 3x3,
                          parent: sid or None, depth_origin: optional model Z}
    Missing specifications are returned as unresolved. Invalid matrices, hashes,
    unknown Part IDs, outside points, and ambiguous inverse registrations fail.
    """
    if not isinstance(surface_specs, Mapping):
        raise GeometryError("surface_specs must map surface IDs to specifications")
    if any(not isinstance(sid, str) for sid in surface_specs):
        raise GeometryError("surface IDs in specifications must be strings")
    nodes = model_observation.get("nodes", [])
    by_id = {str(node["uuid"]): node for node in nodes}
    if len(by_id) != len(nodes):
        raise GeometryError("duplicate observed node UUID")
    assignments = _assignments(structure)
    declared = {str(row["id"]) for row in structure.get("surfaces", [])}
    if declared and set(assignments.values())-declared:
        raise GeometryError("Part assignment references undeclared surface")
    if declared and set(surface_specs)-declared:
        raise GeometryError("surface specification does not match structure surface IDs")
    required = declared | set(assignments.values()) | set(surface_specs)
    unresolved, surfaces = [], {}
    exclusions = {
        str(row["part"] if isinstance(row, Mapping) else row)
        for row in structure.get("excluded_parts", [])
    }
    for node in nodes:
        if node.get("type", node.get("typeId")) != "Part":
            continue
        uid = str(node["uuid"])
        active = node.get("enabled_effective", node.get("enabled", True))
        if active and uid not in assignments and uid not in exclusions:
            unresolved.append({"kind": "unassigned_active_part", "part": uid})
    for uid in assignments:
        if uid not in by_id or by_id[uid].get("type", by_id[uid].get("typeId")) != "Part":
            raise GeometryError(f"assignment {uid} is not an observed Part")
        if uid in exclusions:
            raise GeometryError(f"Part {uid} is both assigned and excluded")
    for sid in sorted(required):
        spec = surface_specs.get(sid)
        if not isinstance(spec, Mapping):
            unresolved.append({"kind": "missing_surface_specification", "surface": sid})
            continue
        missing = [key for key in ("fit", "source_to_model", "parent") if key not in spec]
        if missing:
            unresolved.append({"kind": "incomplete_surface_specification",
                               "surface": sid, "fields": missing})
            continue
        parent = spec["parent"]
        if parent is not None:
            parent = str(parent)
            if parent not in required:
                raise GeometryError(f"surface {sid} names undeclared parent {parent}")
        fit = deepcopy(spec["fit"])
        if not isinstance(fit, Mapping):
            raise GeometryError("surface fit must be an inline artifact, not a path")
        verify_fit(fit)
        source, world, scale = _similarity(spec["source_to_model"], spec.get("depth_origin", 0))
        surfaces[sid] = {
            "fit": fit, "fit_sha256": fit["content_sha256"], "parent": parent,
            "source_to_model": source.tolist(), "source_to_model_3d": world.tolist(),
            "source_to_model_scale": scale, "depth_origin": float(spec.get("depth_origin", 0)),
        }
    # A complete child with an unresolved parent is itself unavailable.
    changed = True
    while changed:
        changed = False
        for sid, surface in list(surfaces.items()):
            if surface["parent"] is not None and surface["parent"] not in surfaces:
                unresolved.append({"kind": "unresolved_parent_surface", "surface": sid,
                                   "parent": surface["parent"]})
                del surfaces[sid]
                changed = True
    order = _ordered_surfaces(surfaces)
    parts = {}
    for uid, sid in sorted(assignments.items()):
        if sid not in surfaces:
            unresolved.append({"kind": "part_surface_unresolved", "part": uid, "surface": sid})
            continue
        node, surface = by_id[uid], surfaces[sid]
        matrix, local = _world_matrix(node)
        nominal = _transform(matrix, np.column_stack((local, np.zeros(len(local)))))
        source_inverse = np.linalg.inv(np.asarray(surface["source_to_model"]))
        source_xy = np.column_stack((nominal[:, :2], np.ones(len(local)))) @ source_inverse.T
        source_xy = source_xy[:, :2]
        fit, control = surface["fit"], surface["fit"]["control"]
        uv = inverse_grid(control["xy"], control["u_lines"], control["v_lines"], source_xy)
        z, depth_method = _depth_at(fit, uv)
        source_xyz = np.column_stack((source_xy, z))
        inferred_world = _transform(np.asarray(surface["source_to_model_3d"]), source_xyz)
        # Exact authored neutral XY, independent of round-trip matrix error.
        inferred_world[:, :2] = nominal[:, :2]
        parts[uid] = {
            "uuid": node["uuid"], "surface": sid, "vertex_count": len(local),
            "source_vertex_sha256": json_digest(local.tolist()),
            "rest_local_xy": local.tolist(), "nominal_world_matrix": matrix.tolist(),
            "nominal_world_xyz": nominal.tolist(), "rest_source_xy": source_xy.tolist(),
            "material_uv": uv.tolist(), "rest_source_xyz": source_xyz.tolist(),
            "rest_world_xyz": inferred_world.tolist(), "depth_method": depth_method,
            "observation_bounds_status": node["bounds"]["status"],
        }
    scene = {
        "schema_version": "rig-scene/1",
        "status": "unresolved" if unresolved else "registered_nominal_unreviewed",
        "model_observation_sha256": json_digest(model_observation),
        "structure_sha256": json_digest(structure), "surface_order": order,
        "surfaces": surfaces, "parts": parts, "unresolved": unresolved,
        "structural_questions": deepcopy(structure.get("questions", [])),
        "coverage": {"assigned_parts": len(assignments), "registered_parts": len(parts),
                     "required_surfaces": len(required), "registered_surfaces": len(surfaces)},
        "limitations": [
            "Registration uses nominal serialized affine geometry; imported Grid/bindings/physics are not evaluated.",
            "Explicit parent edges define rigid pose inheritance only; attachment contact is not solved.",
            "Parent local skin/corrections are not propagated to child surfaces; Parts sharing one surface share its field.",
            "Depth is a shared template prior; neutral projected XY is preserved.",
            "Surface local corrections are projected targets; contact and clipping are not evaluated.",
            "This artifact is not authorized or certified for live application mutation.",
        ],
        "live_model_modified": False,
    }
    scene["content_sha256"] = json_digest(scene)
    return scene


def _verify_scene(scene):
    if scene.get("schema_version") != "rig-scene/1":
        raise GeometryError("not a rig-scene/1 artifact")
    if scene.get("content_sha256") != json_digest(
            {key: value for key, value in scene.items() if key != "content_sha256"}):
        raise GeometryError("scene integrity mismatch")
    if scene.get("unresolved") or scene.get("status") != "registered_nominal_unreviewed":
        raise GeometryError("scene has unresolved surfaces or Parts")
    for surface in scene["surfaces"].values():
        verify_fit(surface["fit"])


def _delta_matrix(pose, neutral, pivot):
    if pose == neutral:
        return np.eye(4)
    rotation = rotation_matrix(pose) @ rotation_matrix(neutral).T
    origin = np.asarray(pivot, dtype=float)
    result = np.eye(4)
    result[:3, :3], result[:3, 3] = rotation, origin-rotation@origin
    return result


def evaluate_scene(scene, poses_by_surface=None, *, include_local=False):
    """Evaluate own pose once, then compose explicit ancestor rigid transforms.

    include_local returns world-baked positions in each nominal node frame.
    They include ancestor motion and must not be blindly combined with the same
    live parent deformation again.
    """
    _verify_scene(scene)
    poses_by_surface = {} if poses_by_surface is None else poses_by_surface
    if not isinstance(poses_by_surface, Mapping):
        raise GeometryError("poses_by_surface must be a mapping")
    if set(poses_by_surface)-set(scene["surfaces"]):
        raise GeometryError("pose references unknown surface")
    state = {}
    for sid in scene["surface_order"]:
        surface = scene["surfaces"][sid]
        fit = surface["fit"]
        neutral = pose_dict(fit["neutral_pose"])
        pose = pose_dict(poses_by_surface.get(sid, neutral))
        source_to_world = np.asarray(surface["source_to_model_3d"], dtype=float)
        own = source_to_world @ _delta_matrix(pose, neutral, fit["pivot"]) @ np.linalg.inv(source_to_world)
        parent_id = surface["parent"]
        parent = np.eye(4) if parent_id is None else state[parent_id]["composed"]
        neutral_chain = pose == neutral and (parent_id is None or state[parent_id]["neutral_chain"])
        state[sid] = {"pose": pose, "neutral": neutral, "own": own, "parent": parent,
                      "composed": parent @ own, "neutral_chain": neutral_chain}
    result = {}
    max_displacement = 0.0
    for uid, registration in scene["parts"].items():
        sid = registration["surface"]
        surface, current = scene["surfaces"][sid], state[sid]
        fit = surface["fit"]
        material = np.asarray(registration["material_uv"], dtype=float)
        source_xyz = np.asarray(registration["rest_source_xyz"], dtype=float)
        rest_world = np.asarray(registration["rest_world_xyz"], dtype=float)
        own_source = rotate_points(source_xyz, current["pose"], fit["pivot"], current["neutral"])
        corrected_source = apply_local_corrections(
            own_source[:, :2], material, current["pose"],
            fit["template"].get("correction_rules", []), fit["parameters"],
            current["neutral"], scale=fit["depth_scale"],
        )
        correction = np.column_stack((corrected_source-own_source[:, :2], np.zeros(len(material))))
        world_linear = np.asarray(surface["source_to_model_3d"], dtype=float)[:3, :3]
        own_world = _transform(current["own"], rest_world) + correction @ world_linear.T
        world = _transform(current["parent"], own_world)
        if current["neutral_chain"]:
            world = rest_world.copy()
        displacement = world[:, :2]-rest_world[:, :2]
        max_displacement = max(max_displacement, float(np.linalg.norm(displacement, axis=1).max()))
        entry = {
            "uuid": registration["uuid"], "surface": sid,
            "vertex_count": registration["vertex_count"],
            "source_vertex_sha256": registration["source_vertex_sha256"],
            "world_xyz": world.tolist(), "world_xy": world[:, :2].tolist(),
            "world_xy_displacements": displacement.tolist(),
        }
        if include_local:
            local = _transform(np.linalg.inv(np.asarray(registration["nominal_world_matrix"])), world)
            entry["local_xyz_in_nominal_frame"] = local.tolist()
            entry["local_xy_displacements_in_nominal_frame"] = (
                local[:, :2]-np.asarray(registration["rest_local_xy"])).tolist()
            entry["local_output_semantics"] = "world_baked; ancestor motion included; not a live binding plan"
            entry["local_neutral_preservation_guaranteed"] = False
        result[uid] = entry
    return {
        "schema_version": "rig-scene-pose/1", "scene_sha256": scene["content_sha256"],
        "poses": {sid: item["pose"] for sid, item in state.items()}, "parts": result,
        "validation": {"finite": True, "max_projected_displacement": max_displacement,
                       "shared_surface_evaluated": True, "parent_rigid_motion_applied_once": True,
                       "imported_deformation_evaluated": False, "contact_solved": False,
                       "clipping_evaluated": False, "mesh_foldover_tested": False,
                       "live_parent_double_application_safe": False},
        "live_model_modified": False,
    }
