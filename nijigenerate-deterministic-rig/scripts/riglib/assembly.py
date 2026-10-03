"""Material-to-structure evidence assembly for flat or grouped source models.

This builds observations for a joint solver, never a fitted scene. Physical
owners, chart coverage and local mechanisms are distinct. No depth or motion
arrays are authored here and source hierarchy cannot dictate physical ownership.
"""
from collections import defaultdict
from copy import deepcopy
import math
import re
from .data import json_digest


def normalized_name(value):
    # Separator normalization is lexical only; suffix L/R remains an opaque tag.
    value = re.sub(r"[\s:\-]+", "_", value.casefold()).strip("_")
    return re.sub(r"__+", "_", value)


def _side(name):
    found = set(re.findall(r"(?:^|_)(l|r|left|right)(?=_|$)", name))
    found = {{"left": "l", "right": "r"}.get(tag, tag) for tag in found}
    return next(iter(found)) if len(found) == 1 else None


def _box(node):
    value = node.get("bounds")
    value = value.get("nominal_world_xy") if isinstance(value, dict) else value
    if value is None:
        return None
    if (not isinstance(value, (list, tuple)) or len(value) != 4 or
        any(type(v) not in (int, float) or not math.isfinite(v) for v in value) or
        value[0] >= value[2] or value[1] >= value[3]):
        raise ValueError("invalid nominal material bounds")
    return list(value)


def _union(boxes):
    boxes = [b for b in boxes if b is not None]
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _classification(name, spec):
    decorator = any(name.startswith(prefix) for prefix in spec["decorator_prefixes"])
    rules = spec["receivers"] if decorator else spec["rules"]
    candidates = []
    for rule in rules:
        match = re.search(rule["pattern"], name)
        if not match:
            continue
        tag = _side(name)
        needs_side = rule.get("side", False) or "{side}" in rule["owner"] + rule["chart"]
        if needs_side and tag is None:
            return None, "side_tag_missing_or_ambiguous"
        candidates.append({"owner": rule["owner"].format(side=tag),
                           "chart": rule["chart"].format(side=tag),
                           "usage": "decoration" if decorator else rule["usage"],
                           "rule": rule.get("id", rule["pattern"]),
                           "side_tag": tag})
    if len(candidates) != 1:
        return None, "role_candidates_ambiguous" if candidates else "material_role_unknown"
    return candidates[0], None


def assemble_model(observation, specification, evidence=None):
    if specification.get("schema_version") != "rig-material-roles/1":
        raise ValueError("unsupported material roles schema")
    for rule in specification["rules"] + specification["receivers"] + specification["local_mechanisms"]:
        re.compile(rule["pattern"])
    nodes = observation["nodes"]
    by_id = {str(n["uuid"]): n for n in nodes}
    if len(by_id) != len(nodes):
        raise ValueError("duplicate node UUID")
    evidence = evidence or {}
    if evidence:
        if evidence.get("schema_version") != "rig-semantic-evidence/1":
            raise ValueError("unsupported semantic evidence schema")
        if evidence.get("observation_sha256") != json_digest(observation):
            raise ValueError("semantic evidence observation hash mismatch")
    annotated = {}
    rules_by_id = {rule["id"]: rule for rule in specification["rules"]}
    if len(rules_by_id) != len(specification["rules"]):
        raise ValueError("duplicate semantic role")
    for row in evidence.get("materials", []):
        uid = str(row["part"])
        if uid in annotated or uid not in by_id or by_id[uid]["type"] != "Part":
            raise ValueError("invalid or duplicate evidence Part")
        if row.get("role") not in rules_by_id or row.get("provenance") not in {"visual_observation", "source_annotation"}:
            raise ValueError("semantic evidence requires a known role and explicit provenance")
        rule = rules_by_id[row["role"]]
        tag = row.get("side_tag")
        needs_side = rule.get("side", False) or "{side}" in rule["owner"] + rule["chart"]
        if needs_side and (not isinstance(tag, str) or not re.fullmatch(r"[a-z0-9_-]+", tag)):
            raise ValueError("semantic evidence requires an opaque side tag")
        annotated[uid] = {"owner": rule["owner"].format(side=tag), "chart": rule["chart"].format(side=tag),
                          "usage": rule["usage"], "rule": rule["id"], "side_tag": tag,
                          "provenance": row["provenance"]}
    materials, excluded, unknown, charts, owners, mechanisms = [], [], [], {}, {}, {}
    questions = defaultdict(list)
    for node in sorted(nodes, key=lambda n: str(n["uuid"])):
        if node["type"] != "Part":
            continue
        cursor, visited, enabled = node, set(), True
        while cursor is not None:
            uid = str(cursor["uuid"])
            if uid in visited:
                raise ValueError("cyclic node ancestry")
            visited.add(uid)
            enabled &= cursor.get("enabled_effective", True) and cursor.get("enabled_local", cursor.get("enabled", True))
            parent = cursor.get("parent")
            if parent is not None and str(parent) not in by_id:
                raise ValueError("missing parent")
            cursor = by_id.get(str(parent)) if parent is not None else None
        if not enabled:
            excluded.append({"part": node["uuid"], "reason": "disabled_in_source"})
            continue
        name = normalized_name(node["name"])
        role = annotated.get(str(node["uuid"]))
        reason = None
        if role is None:
            role, reason = _classification(name, specification)
        if role is None:
            unknown.append(node["uuid"])
            questions[reason].append(node["uuid"])
            materials.append({"part": node["uuid"], "name": node["name"], "state": "unassigned"})
            continue
        owner, chart = role["owner"], role["owner"] + "/" + role["chart"]
        bounds = _box(node)
        owners.setdefault(owner, {"id": owner, "material_parts": [], "anatomy_evidence_parts": [],
                                  "coverage_boxes": [], "anatomy_boxes": []})
        record = owners[owner]
        record["material_parts"].append(node["uuid"])
        record["coverage_boxes"].append(bounds)
        if role["usage"] == "anatomy":
            record["anatomy_evidence_parts"].append(node["uuid"])
            record["anatomy_boxes"].append(bounds)
        charts.setdefault(chart, {"id": chart, "owner": owner, "parts": [], "coverage_boxes": [],
                                  "semantic_names": [], "usages": set()})
        record = charts[chart]
        record["parts"].append(node["uuid"])
        record["coverage_boxes"].append(bounds)
        record["semantic_names"].append(node["name"])
        record["usages"].add(role["usage"])
        materials.append({"part": node["uuid"], "name": node["name"], "owner": owner, "chart": chart,
                          "state": "semantic_observation" if "provenance" in role else "lexical_candidate", "role": role,
                          "coordinate_frame": "nominal_model_xy",
                          "physical_connection_verified": False})
        if role["usage"] != "decoration":
            for rule in specification["local_mechanisms"]:
                if not re.search(rule["pattern"], name):
                    continue
                tag = _side(name) if rule["side"] else None
                if rule["side"] and tag is None:
                    questions["mechanism_side_unresolved"].append(node["uuid"])
                    continue
                mid = chart + "/" + rule["kind"] + (":" + tag if tag else "")
                mechanisms.setdefault(mid, {"id": mid, "chart": chart, "kind": rule["kind"],
                                           "parts": [], "motion_implemented": False})["parts"].append(node["uuid"])
    for owner in owners.values():
        owner["material_coverage_bounds"] = _union(owner.pop("coverage_boxes"))
        owner["visible_anatomy_bounds"] = _union(owner.pop("anatomy_boxes"))
        owner["anatomical_frame"] = None
        owner["volume_fit"] = None
        owner["state"] = "requires_joint_scaffold_fit"
    for chart in charts.values():
        chart["coverage_bounds"] = _union(chart.pop("coverage_boxes"))
        chart["usages"] = sorted(chart["usages"])
        chart["state"] = "observation_bundle"
        chart["material_registration"] = None
    edges = [{"parent_owner": "torso", "child_owner": owner, "kind": "anatomical_support_candidate",
              "attachment_frame": None, "state": "requires_joint_scaffold_fit"}
             for owner in sorted(owners) if owner != "torso" and "torso" in owners]
    result = {
        "schema_version": "rig-assembly/2", "status": "assembly_proposal",
        "source": deepcopy(observation["source"]),
        "observation_sha256": json_digest(observation), "specification_sha256": json_digest(specification),
        "semantic_evidence_sha256": json_digest(evidence),
        "owners": [owners[k] for k in sorted(owners)], "charts": [charts[k] for k in sorted(charts)],
        "materials": materials, "mechanisms": [mechanisms[k] for k in sorted(mechanisms)],
        "support_relations": edges, "excluded_parts": excluded,
        "questions": [{"kind": kind, "parts": sorted(set(parts), key=str)} for kind, parts in sorted(questions.items())],
        "coverage": {"active_parts": len(materials), "assigned_parts": len(materials)-len(unknown),
                     "unassigned_parts": len(unknown), "owners": len(owners), "charts": len(charts),
                     "unique_material_ownership": len(materials) == len({row['part'] for row in materials})},
        "side_convention": "l/r are source-name tags, not anatomical or screen sides",
        "model_modified": False, "fit_ready": False,
    }
    result["content_sha256"] = json_digest(result)
    return result


def landmark_observation_structure(assembly):
    """Expose shared core observations to existing candidate detectors only.

    No free cloth/appendage topology is coerced into the v1 fit API. This adapter
    is deliberately not a scene, and cannot be passed off as fit-ready output.
    """
    templates = {"head/face": "face_head", "torso/body": "torso"}
    groups, surfaces = [], []
    for chart in assembly["charts"]:
        tid = templates.get(chart["id"])
        if chart["id"].endswith("/skin"):
            tid = chart["owner"].split(":", 1)[0]
        if tid not in ("face_head", "torso", "arm", "leg"):
            continue
        groups.append({"id": chart["id"], "parts": chart["parts"], "bounds": chart["coverage_bounds"]})
        surfaces.append({"id": chart["id"], "group": chart["id"], "template_id": tid})
    return {"status": "landmark_observation_only", "groups": groups, "surfaces": surfaces}
