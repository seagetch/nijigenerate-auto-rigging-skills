"""Deterministic landmark *proposals* on already proposed shared surfaces.

No model reads/writes, NJC calls, pixels, anatomical recognition network, or rig
mutation occurs here. Serialized mesh/bone measurements remain nominal proxies.
Template priors permit preview, but never resolve a required measured role.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence


_SCHEMA = "rig-landmark-proposal/1"
_BAND_FRACTION = 0.08
_EYE_CLUSTER_X_FRACTION = 0.14
_EYE_CLUSTER_Y_FRACTION = 0.12
_TIE_TOLERANCE = 1e-10


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return float(value)


def _xy(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{label} must contain two coordinates")
    return [_number(v, label) for v in value]


def _identifier(value, label):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or str(value) == "":
        raise ValueError(f"invalid {label}")
    return str(value)


def _uuid_sort(values):
    return sorted(values, key=lambda v: (str(v), type(v).__name__))


def _bounds(value, label="bounds"):
    if isinstance(value, Mapping):
        value = value.get("nominal_world_xy")
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f"{label} must contain four coordinates")
    box = [_number(v, label) for v in value]
    if box[2] < box[0] or box[3] < box[1]:
        raise ValueError(f"{label} is inverted")
    return box


def _union(boxes):
    boxes = [b for b in boxes if b is not None]
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _center(box):
    return [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]


def _prior_xy(uv, box):
    return [box[0] + uv[0] * (box[2] - box[0]),
            box[1] + uv[1] * (box[3] - box[1])]


def _type(node):
    return node.get("type", node.get("typeId", ""))


def _enabled(node):
    return bool(node.get("enabled_effective", True) and
                node.get("enabled_local", node.get("enabled", True)))


def _catalog(value):
    if isinstance(value, Mapping):
        if "id" in value and "landmarks" in value:
            entries = [value]
        else:
            entries = list(value.values())
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        entries = list(value)
    else:
        raise ValueError("template_catalog must be a template list or id-to-template mapping")
    result = {}
    for template in entries:
        if not isinstance(template, Mapping) or "id" not in template:
            raise ValueError("catalog entries must be complete template objects")
        tid = _identifier(template["id"], "template id")
        if tid in result:
            raise ValueError(f"duplicate template id {tid}")
        roles = template.get("landmarks", [])
        role_ids = []
        for role in roles:
            rid = _identifier(role.get("id", role.get("role", role.get("name"))), "landmark role")
            uv = _xy(role.get("uv"), f"{tid}.{rid}.uv")
            if any(v < 0 or v > 1 for v in uv):
                raise ValueError("landmark uv outside [0,1]")
            role_ids.append(rid)
        if len(role_ids) != len(set(role_ids)):
            raise ValueError(f"duplicate landmark role in {tid}")
        result[tid] = template
    return result


def _role_id(role):
    return str(role.get("id", role.get("role", role.get("name"))))


def _matrix(node):
    value = node.get("nominal_world_matrix")
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("nominal_world_matrix must be 4x4")
    result = []
    for row in value:
        if not isinstance(row, (list, tuple)) or len(row) != 4:
            raise ValueError("nominal_world_matrix must be 4x4")
        result.append([_number(v, "nominal_world_matrix") for v in row])
    return result


def _transform_xy(matrix, point):
    x, y = _xy(point, "mesh vertex")
    return [matrix[r][0] * x + matrix[r][1] * y + matrix[r][3] for r in (0, 1)]


def _mesh_points(node):
    mesh = node.get("mesh")
    if not isinstance(mesh, Mapping) or "vertices" not in mesh:
        return []
    vertices = mesh["vertices"]
    if not isinstance(vertices, (list, tuple)):
        raise ValueError("mesh.vertices must be observed XY pairs")
    validated = [_xy(p, "mesh vertex") for p in vertices]
    matrix = _matrix(node)
    if matrix is None:
        return []
    return [_transform_xy(matrix, p) for p in validated]


def _evidence(kind, nodes, **extra):
    return {
        "kind": kind,
        "source_uuids": _uuid_sort(n["uuid"] for n in nodes),
        "source_names": [n.get("name", "") for n in sorted(nodes, key=lambda n: str(n["uuid"]))],
        "coordinate_frame": "nominal_world_xy",
        "live_pose_evaluated": False,
        "semantic_verified": False,
        "boundary_certified": False,
        **extra,
    }


def _candidate(xy, state, evidence):
    return {"xy": _xy(xy, "candidate.xy"), "state": state, "evidence": evidence}


def _bbox_candidate(node, xy, method):
    return _candidate(xy, "measured_bbox_proxy",
                      _evidence("serialized_feature_bounds", [node], method=method,
                                semantic_selection="name_and_geometry_candidate"))


def _feature_box(node):
    if not _enabled(node) or _type(node) != "Part":
        return None
    return _bounds(node.get("bounds"), f"node {node['uuid']} bounds")


def _eye_priority(name):
    text = name.casefold()
    if re.search(r"(sclera|eye[\W_]*white|white[\W_]*eye|白目)", text):
        return 0
    if re.search(r"(iris|pupil|虹彩|瞳)", text):
        return 1
    if re.search(r"(corner|canthus|brow|lash|lid|shadow|original|hidden|眉|睫毛|瞼)", text):
        return None
    if re.search(r"(^|[:_\s-])(eye|eyes)(?=$|[:_\s-])", text):
        return 2
    return None


def _cluster_eyes(nodes, surface_box):
    width, height = surface_box[2] - surface_box[0], surface_box[3] - surface_box[1]
    features = []
    for node in nodes:
        priority = _eye_priority(node.get("name", ""))
        box = _feature_box(node)
        if priority is None or box is None or box[2] <= box[0] or box[3] <= box[1]:
            continue
        features.append({"node": node, "box": box, "priority": priority, "center": _center(box)})
    features.sort(key=lambda f: (f["center"][0], f["center"][1], str(f["node"]["uuid"])))
    adjacency = {i: set() for i in range(len(features))}
    for i, a in enumerate(features):
        for j in range(i + 1, len(features)):
            b = features[j]
            overlap = (min(a["box"][2], b["box"][2]) > max(a["box"][0], b["box"][0]) and
                       min(a["box"][3], b["box"][3]) > max(a["box"][1], b["box"][1]))
            close = (abs(a["center"][0] - b["center"][0]) <= _EYE_CLUSTER_X_FRACTION * width and
                     abs(a["center"][1] - b["center"][1]) <= _EYE_CLUSTER_Y_FRACTION * height)
            if overlap or close:
                adjacency[i].add(j)
                adjacency[j].add(i)
    clusters, visited = [], set()
    for seed in range(len(features)):
        if seed in visited:
            continue
        stack, indices = [seed], []
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            indices.append(current)
            stack.extend(sorted(adjacency[current] - visited, reverse=True))
        members = [features[i] for i in indices]
        # Sclera centers are stable under iris/gaze motion. Never average an iris
        # displacement into an eye-white center if the white is available.
        best = min(members, key=lambda f: (
            f["priority"], -(f["box"][2] - f["box"][0]) * (f["box"][3] - f["box"][1]),
            str(f["node"]["uuid"])))
        clusters.append({"best": best, "members": members})
    return sorted(clusters, key=lambda c: (c["best"]["center"][0], c["best"]["center"][1],
                                           str(c["best"]["node"]["uuid"])))


def _unique_named(nodes, pattern):
    matches = [n for n in nodes if _feature_box(n) is not None and
               re.search(pattern, n.get("name", ""), re.IGNORECASE)]
    return matches[0] if len(matches) == 1 else None


def _face_candidates(nodes, box, diagnostics):
    found = {}
    eyes = _cluster_eyes(nodes, box)
    if len(eyes) == 2 and eyes[0]["best"]["center"][0] < eyes[1]["best"]["center"][0]:
        for suffix, cluster in zip(("a", "b"), eyes):
            best = cluster["best"]
            evidence = _evidence("serialized_eye_feature_cluster",
                                 [m["node"] for m in cluster["members"]],
                                 selected_source_uuid=best["node"]["uuid"],
                                 method="preferred_sclera_else_iris_else_eye_bbox_center",
                                 side_basis="increasing_screen_x_not_name_suffix",
                                 semantic_selection="name_and_geometry_candidate")
            found["eye_" + suffix] = _candidate(best["center"], "measured_bbox_proxy", evidence)
            bx, by, ex, ey = best["box"]
            inner_x, outer_x = (ex, bx) if suffix == "a" else (bx, ex)
            found["eye_inner_" + suffix] = _candidate(
                [inner_x, (by + ey) / 2], "measured_bbox_proxy", {**evidence, "method": "inner_bbox_edge"})
            found["eye_outer_" + suffix] = _candidate(
                [outer_x, (by + ey) / 2], "measured_bbox_proxy", {**evidence, "method": "outer_bbox_edge"})
    else:
        diagnostics.append({"kind": "eye_pair_unresolved", "cluster_count": len(eyes),
                            "reason": "two distinct screen-ordered feature clusters required"})
    nose = _unique_named(nodes, r"(^|[:_\s-])(nose|鼻先|鼻)(?=$|[:_\s-](tip|base|先|底)$)")
    if nose is not None:
        found["nose_tip"] = _bbox_candidate(nose, _center(_feature_box(nose)), "nose_part_bbox_center")
    else:
        diagnostics.append({"kind": "nose_not_separately_observed"})
    face = _unique_named(nodes, r"(^|[:_\s-])(face|顔)(?=$|[:_\s-](skin|base)$)")
    if face is not None:
        face_box = _feature_box(face)
        found["chin"] = _bbox_candidate(face, [(face_box[0]+face_box[2])/2, face_box[3]],
                                        "face_body_bbox_bottom_center_not_true_contour")
        found["crown"] = _bbox_candidate(face, [(face_box[0]+face_box[2])/2, face_box[1]],
                                         "face_body_bbox_top_center_not_true_contour")
    mouth = _unique_named(nodes, r"(^|[:_\s-])(mouth|口)(?=$|[:_\s-](outline|base)$)")
    if mouth is not None:
        mb = _feature_box(mouth)
        found["mouth_a"] = _bbox_candidate(mouth, [mb[0], (mb[1]+mb[3])/2], "mouth_bbox_left_edge")
        found["mouth_b"] = _bbox_candidate(mouth, [mb[2], (mb[1]+mb[3])/2], "mouth_bbox_right_edge")
    brows = sorted([n for n in nodes if _feature_box(n) is not None and
                    re.search(r"(brow|眉)", n.get("name", ""), re.IGNORECASE)],
                   key=lambda n: (_center(_feature_box(n))[0], str(n["uuid"])))
    if len(brows) == 2:
        for suffix, brow in zip(("a", "b"), brows):
            found["brow_" + suffix] = _bbox_candidate(brow, _center(_feature_box(brow)), "brow_bbox_center")
    return found


def _opening_candidates(nodes, box, diagnostics):
    eyes = _cluster_eyes(nodes, box)
    if len(eyes) != 1:
        diagnostics.append({"kind": "single_opening_unresolved", "cluster_count": len(eyes)})
        return {}
    best = eyes[0]["best"]
    x0, y0, x1, y1 = best["box"]
    node = best["node"]
    result = {
        "canthus_a": _bbox_candidate(node, [x0, (y0+y1)/2], "opening_bbox_left_edge"),
        "canthus_b": _bbox_candidate(node, [x1, (y0+y1)/2], "opening_bbox_right_edge"),
        "upper_center": _bbox_candidate(node, [(x0+x1)/2, y0], "opening_bbox_top_center"),
        "lower_center": _bbox_candidate(node, [(x0+x1)/2, y1], "opening_bbox_bottom_center"),
    }
    corners = sorted([n for n in nodes if _feature_box(n) is not None and
                      re.search(r"(corner|canthus|目頭|目尻)", n.get("name", ""), re.IGNORECASE)],
                     key=lambda n: (_center(_feature_box(n))[0], str(n["uuid"])))
    if len(corners) == 2:
        for role, node in zip(("canthus_a", "canthus_b"), corners):
            result[role] = _bbox_candidate(node, _center(_feature_box(node)), "explicit_corner_part_bbox_center")
    return result


def _mesh_band_candidates(nodes, diagnostics):
    points = []
    for node in nodes:
        for index, point in enumerate(_mesh_points(node)):
            points.append((point[0], point[1], node["uuid"], index, node))
    if not points:
        diagnostics.append({"kind": "mesh_geometry_unavailable",
                            "reason": "world matrix and observed mesh vertices required; bbox is not a silhouette"})
        return {}
    ymin, ymax = min(p[1] for p in points), max(p[1] for p in points)
    if ymax <= ymin:
        diagnostics.append({"kind": "degenerate_mesh_bands"})
        return {}
    band = _BAND_FRACTION * (ymax-ymin)
    top = [p for p in points if p[1] <= ymin+band]
    bottom = [p for p in points if p[1] >= ymax-band]
    result = {}
    for prefix, candidates in (("waist", top), ("hem", bottom)):
        low = min(candidates, key=lambda p: (p[0], p[1], str(p[2]), p[3]))
        high = max(candidates, key=lambda p: (p[0], p[1], str(p[2]), p[3]))
        if high[0] <= low[0]:
            diagnostics.append({"kind": "degenerate_band_width", "band": prefix})
            continue
        for suffix, point in (("a", low), ("b", high)):
            result[prefix+"_"+suffix] = _candidate(
                [point[0], point[1]], "measured_mesh_band_proxy",
                _evidence("serialized_mesh_band_extreme", [point[4]],
                          source_vertex_index=point[3], band=prefix,
                          band_fraction=_BAND_FRACTION,
                          band_source_uuids=_uuid_sort(set(p[2] for p in candidates)),
                          method="screen_x_extreme_of_top_or_bottom_mesh_band",
                          boundary_status="mesh_extent_only_not_alpha_or_material_seam"))
    return result


def _bone_point(node):
    if _type(node) not in ("DepthBone", "Bone") or not _enabled(node):
        return None
    matrix = _matrix(node)
    if matrix is None:
        return None
    return [matrix[0][3], matrix[1][3]]


def _descendant(node, ancestor, by_id):
    cursor = node
    visited = set()
    while cursor.get("parent") is not None:
        parent = str(cursor["parent"])
        if parent in visited:
            raise ValueError("cycle in bone parent graph")
        visited.add(parent)
        if parent == str(ancestor["uuid"]):
            return True
        cursor = by_id.get(parent)
        if cursor is None:
            return False
    return False


def _bone_candidates(template_id, nodes, by_id, box, diagnostics):
    names = {
        "arm": {
            "root": r"upper[\W_]*arm",
            "joint": r"fore[\W_]*arm|lower[\W_]*arm",
            "end": r"(^|[:_.\s-])hand(?=$|[:_.\s-])",
        },
        "leg": {
            "root": r"thigh|upper[\W_]*leg",
            "joint": r"shin|lower[\W_]*leg",
            "end": r"(^|[:_.\s-])(foot|ankle)(?=$|[:_.\s-])",
        },
    }[template_id]
    width, height = box[2]-box[0], box[3]-box[1]
    scale = max(width, height)
    found, previous = {}, None
    for role, v in (("root", 0), ("joint", .5), ("end", 1)):
        expected = _prior_xy([.5, v], box)
        ranked = []
        for node in nodes:
            if not re.search(names[role], node.get("name", ""), re.IGNORECASE):
                continue
            point = _bone_point(node)
            if point is None:
                continue
            if previous is not None and not _descendant(node, previous, by_id):
                continue
            score = sum(((point[i]-expected[i])/scale)**2 for i in (0, 1))
            ranked.append((score, str(node["uuid"]), node, point))
        ranked.sort(key=lambda item: (item[0], item[1]))
        if (not ranked or ranked[0][0] > 4 or
                (len(ranked)>1 and abs(ranked[1][0]-ranked[0][0]) <= _TIE_TOLERANCE)):
            diagnostics.append({"kind": "bone_role_unresolved", "role": role,
                                "reason": "missing, spatially remote, or tied bone candidate"})
            continue
        score, _, node, point = ranked[0]
        found[role] = _candidate(
            point, "measured_bone_origin_proxy",
            _evidence("serialized_bone_origin", [node],
                      method="nominal_world_matrix_origin", ranking_score=score,
                      score_is_probability=False, side_basis="spatial_proximity_not_suffix",
                      ancestor_consistency=previous is None or _descendant(node, previous, by_id),
                      engine_transform_semantics_verified=False))
        previous = node
    return found


def _assert_finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite landmark proposal")
    if isinstance(value, Mapping):
        for item in value.values():
            _assert_finite(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_finite(item)


def propose_landmarks(observation, structure, template_catalog):
    """Bundle observations per proposed surface and return auditable candidates.

    Catalog accepts a list of templates or an id-to-template mapping. All output
    XY is nominal serialized world XY, never current rendered pose geometry.
    Required roles backed only by template_prior remain in missing_roles.
    Measured proxies leave semantic/source-fit verification false.
    """
    templates = _catalog(template_catalog)
    nodes = observation.get("nodes", [])
    by_id = {}
    for node in nodes:
        uid = _identifier(node.get("uuid"), "node UUID")
        if uid in by_id:
            raise ValueError("duplicate model node UUID")
        by_id[uid] = node
    groups = {}
    for group in structure.get("groups", []):
        gid = _identifier(group.get("id"), "group id")
        if gid in groups:
            raise ValueError("duplicate observed group")
        groups[gid] = group
    surfaces = structure.get("surfaces", [])
    if isinstance(surfaces, Mapping):
        surfaces = [dict(value, id=key) for key, value in surfaces.items()]
    if len({str(s.get("id")) for s in surfaces}) != len(surfaces):
        raise ValueError("duplicate surface id")
    result = {}
    for surface in sorted(surfaces, key=lambda s: str(s["id"])):
        sid = _identifier(surface.get("id"), "surface id")
        group = groups.get(str(surface.get("group")))
        if group is None:
            raise ValueError(f"surface {sid} references an unknown observation group")
        source_nodes = []
        for uid in group.get("parts", []):
            node = by_id.get(str(uid))
            if node is None:
                raise ValueError(f"unknown source part UUID {uid}")
            if _type(node) != "Part":
                raise ValueError("surface observation group contains a non-Part")
            if _enabled(node):
                source_nodes.append(node)
        source_nodes.sort(key=lambda n: str(n["uuid"]))
        if len({str(n["uuid"]) for n in source_nodes}) != len(source_nodes):
            raise ValueError("duplicate Part within a surface group")
        box = _bounds(group.get("bounds"), "surface bounds")
        if box is None:
            box = _union([_feature_box(node) for node in source_nodes])
        tid = surface.get("template_id")
        record = {
            "template_id": tid, "bounds": box, "landmarks": [], "missing_roles": [],
            "source_uuids": _uuid_sort(n["uuid"] for n in source_nodes),
            "diagnostics": [], "source_fit_verified": False,
            "boundary_certified": False,
            "coordinate_frame": "nominal_world_xy",
        }
        result[sid] = record
        if tid is None:
            record["diagnostics"].append({"kind": "unresolved_surface_template"})
            continue
        if str(tid) not in templates:
            raise ValueError(f"template {tid} is absent from catalog")
        template = templates[str(tid)]
        roles = template.get("landmarks", [])
        required = {_role_id(role) for role in roles if role.get("required", False)}
        if box is None or box[2] <= box[0] or box[3] <= box[1]:
            record["missing_roles"] = sorted(required)
            record["diagnostics"].append({"kind": "surface_bounds_unavailable_or_degenerate"})
            continue
        diagnostics = record["diagnostics"]
        measured = {}
        if tid in ("face_head", "head_surface"):
            measured = _face_candidates(source_nodes, box, diagnostics)
        elif tid == "eye_opening":
            measured = _opening_candidates(source_nodes, box, diagnostics)
        elif tid == "skirt":
            measured = _mesh_band_candidates(source_nodes, diagnostics)
        elif tid in ("arm", "leg"):
            measured = _bone_candidates(tid, nodes, by_id, box, diagnostics)
        for role in roles:
            rid, uv = _role_id(role), _xy(role.get("uv"), "role.uv")
            candidate = measured.get(rid)
            if candidate is None:
                candidate = _candidate(
                    _prior_xy(uv, box), "template_prior",
                    {"kind": "template_prior", "source_uuids": [],
                     "bounds_source_uuids": record["source_uuids"],
                     "template_id": str(tid), "template_version": template.get("version"),
                     "method": "fixed_uv_to_observed_bounds", "measurement": False,
                     "semantic_verified": False, "boundary_certified": False})
                if rid in required:
                    record["missing_roles"].append(rid)
            record["landmarks"].append(
                {"role": rid, "uv": uv, **candidate,
                 "candidate_state": candidate["state"],
                 "measurement_based": candidate["state"] != "template_prior"})
        record["missing_roles"].sort()
    output = {
        "schema_version": _SCHEMA, "status": "landmark_proposal",
        "surfaces": result,
        "source_fit_verified": False, "model_modified": False,
        "limitations": [
            "Part labels and nominal geometry provide candidates, not certified anatomical identity.",
            "Mesh/bbox extrema do not establish alpha, material seams, or actual silhouette.",
            "Serialized matrices do not evaluate live deformation, clipping, or physics.",
            "Template-prior coordinates are preview inputs and never measured landmarks.",
        ],
    }
    _assert_finite(output)
    return output
