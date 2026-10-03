"""Validate this catalog's JSON Schema subset and semantic contracts.

Python standard library only. This is NOT a complete JSON Schema implementation.
Every unsupported schema keyword/type/reference is rejected, never ignored.
No model is loaded or modified. Optional --output writes only a validation report.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SUPPORTED = {
    "$schema", "$id", "title", "$defs", "$ref", "type", "const", "enum", "oneOf",
    "required", "properties", "additionalProperties", "items", "prefixItems",
    "minimum", "maximum", "exclusiveMinimum", "pattern", "minItems", "maxItems",
    "uniqueItems",
}
TYPES = {"object", "array", "number", "string", "boolean", "null"}
PARAMETER_FIELDS = {"depth", "height", "amplitude", "offset", "base"}
FORBIDDEN_IDENTITY_FIELDS = {"uuid", "node_uuid", "part_uuid", "parameter_uuid", "keyframe_values"}


class ValidationFailure(ValueError):
    pass


def _loads(text):
    def constant(value):
        raise ValidationFailure(f"non-finite JSON constant: {value}")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValidationFailure(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(text, parse_constant=constant, object_pairs_hook=unique)


def read_json(path):
    return _loads(Path(path).read_text(encoding="utf-8-sig"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json_equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return set(a) == set(b) and all(_json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_json_equal(x, y) for x, y in zip(a, b))
    return a == b


def _resolve(schema, root):
    if "$ref" not in schema:
        return schema
    if set(schema) != {"$ref"}:
        raise ValidationFailure("$ref siblings are outside the supported subset")
    ref = schema["$ref"]
    if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
        raise ValidationFailure("only local #/$defs/ references are supported")
    key = ref[len("#/$defs/"):].replace("~1", "/").replace("~0", "~")
    try:
        return root["$defs"][key]
    except KeyError as error:
        raise ValidationFailure(f"unresolved schema reference {ref}") from error


def check_schema_subset(schema, root=None, path="$"):
    root = schema if root is None else root
    if not isinstance(schema, dict):
        raise ValidationFailure(f"{path}: only object schemas are supported")
    unknown = set(schema) - SUPPORTED
    if unknown:
        raise ValidationFailure(f"{path}: unsupported schema keywords {sorted(unknown)}")
    if "type" in schema and schema["type"] not in TYPES:
        raise ValidationFailure(f"{path}: unsupported schema type")
    if "$ref" in schema:
        _resolve(schema, root)
    if "additionalProperties" in schema and not isinstance(schema["additionalProperties"], bool):
        raise ValidationFailure("schema-valued additionalProperties is unsupported")
    if "pattern" in schema:
        re.compile(schema["pattern"])
    for key in ("properties", "$defs"):
        for name, child in schema.get(key, {}).items():
            check_schema_subset(child, root, f"{path}/{key}/{name}")
    for key in ("oneOf", "prefixItems"):
        if key in schema and not isinstance(schema[key], list):
            raise ValidationFailure(f"{path}: {key} must be a list")
        for index, child in enumerate(schema.get(key, [])):
            check_schema_subset(child, root, f"{path}/{key}/{index}")
    if "items" in schema:
        check_schema_subset(schema["items"], root, path + "/items")


def schema_errors(schema, value, root=None, path="$", depth=0):
    root = schema if root is None else root
    if depth > 64:
        raise ValidationFailure("schema recursion limit")
    schema = _resolve(schema, root)
    errors = []
    if "oneOf" in schema:
        count = sum(not schema_errors(child, value, root, path, depth+1)
                    for child in schema["oneOf"])
        if count != 1:
            errors.append(f"{path}: oneOf matched {count}, expected exactly one")
        # Other constraints still apply if a future catalog adds them.
    if "const" in schema and not _json_equal(value, schema["const"]):
        errors.append(f"{path}: const mismatch")
    if "enum" in schema and not any(_json_equal(value, item) for item in schema["enum"]):
        errors.append(f"{path}: value outside enum")
    typ = ("boolean" if isinstance(value, bool) else "null" if value is None else
           "number" if isinstance(value, (int, float)) else "object" if isinstance(value, dict) else
           "array" if isinstance(value, list) else "string" if isinstance(value, str) else "unsupported")
    if "type" in schema and schema["type"] != typ:
        return errors + [f"{path}: expected {schema['type']}, got {typ}"]
    if typ == "number":
        if not math.isfinite(value):
            errors.append(f"{path}: non-finite number")
        for key, fails in (("minimum", lambda x, bound: x < bound),
                           ("maximum", lambda x, bound: x > bound),
                           ("exclusiveMinimum", lambda x, bound: x <= bound)):
            if key in schema and fails(value, schema[key]):
                errors.append(f"{path}: {key}")
    elif typ == "string" and "pattern" in schema:
        if re.search(schema["pattern"], value) is None:
            errors.append(f"{path}: pattern mismatch")
    elif typ == "object":
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: required property {key}")
        properties = schema.get("properties", {})
        for key, child in value.items():
            if key in properties:
                errors.extend(schema_errors(properties[key], child, root, path+"."+key, depth+1))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: additional property {key}")
    elif typ == "array":
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: minItems")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: maxItems")
        if schema.get("uniqueItems") and any(
                _json_equal(value[i], value[j]) for i in range(len(value)) for j in range(i)):
            errors.append(f"{path}: duplicate items")
        prefix = schema.get("prefixItems", [])
        for index, child in enumerate(value):
            target = prefix[index] if index < len(prefix) else schema.get("items")
            if target is not None:
                errors.extend(schema_errors(target, child, root, f"{path}[{index}]", depth+1))
    return errors


def _unique(items, label, errors):
    if len(items) != len(set(items)):
        errors.append(f"{label}: duplicate identifiers")


def _walk(value, path="$"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child, path+"."+key
            yield from _walk(child, path+"."+key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def template_semantic_errors(template):
    errors = []
    tid = template["id"]
    landmarks = {entry["id"]: entry for entry in template["landmarks"]}
    tunables = {entry["id"]: entry for entry in template["tunables"]}
    for key in ("landmarks", "tunables", "attachment_slots", "drivers"):
        _unique([row["id"] for row in template[key]], f"{tid}.{key}", errors)
    for name, coord in (("rows", "v"), ("columns", "u")):
        rows = template["guide_grid"][name]
        _unique([row["id"] for row in rows], f"{tid}.{name}", errors)
        values = [row[coord] for row in rows]
        if values[0] != 0 or values[-1] != 1 or any(a >= b for a, b in zip(values, values[1:])):
            errors.append(f"{tid}.{name}: axes must span [0,1] in strict order")
        for row in rows:
            for role in row["landmark_roles"]:
                if role not in landmarks:
                    errors.append(f"{tid}.{name}: unresolved role {role}")
    for item in template["tunables"]:
        if not item["min"] <= item["default"] <= item["max"]:
            errors.append(f"{tid}: default outside bounds for {item['id']}")
    expected_required = {key for key, value in landmarks.items() if value["required"]}
    expected_optional = set(landmarks) - expected_required
    if set(template["hints"]["required"]) != expected_required:
        errors.append(f"{tid}: required hints disagree with landmark flags")
    if set(template["hints"]["optional"]) != expected_optional:
        errors.append(f"{tid}: optional hints disagree with landmark flags")
    for key, value, path in _walk(template):
        if key in FORBIDDEN_IDENTITY_FIELDS:
            errors.append(f"{tid}{path}: model-specific identity or key data is forbidden")
        if isinstance(value, float) and not math.isfinite(value):
            errors.append(f"{tid}{path}: non-finite")
    for container in (template["geometry"]["operators"], template["correction_rules"]):
        for key, value, path in _walk(container):
            if key in PARAMETER_FIELDS and isinstance(value, str) and value not in tunables:
                errors.append(f"{tid}{path}: unresolved parameter {value}")
            if key.endswith("_profile"):
                if (value[0][0] != 0 or value[-1][0] != 1 or
                        any(a[0] >= b[0] for a, b in zip(value, value[1:]))):
                    errors.append(f"{tid}{path}: profile must strictly span [0,1]")
                for _, scalar in value:
                    if isinstance(scalar, str) and scalar not in tunables:
                        errors.append(f"{tid}{path}: unresolved profile parameter {scalar}")
            if key == "radius" and any(v <= 0 for v in value):
                errors.append(f"{tid}{path}: radius must be positive")
            if key == "direction" and not any(value):
                errors.append(f"{tid}{path}: direction must be nonzero")
            if key == "support" and (value[0] >= value[2] or value[1] >= value[3]):
                errors.append(f"{tid}{path}: ribbon support must have positive size")
    for item in template["attachment_slots"] + template["guide_grid"]["patches"]:
        if any(item["region"][axis][0] > item["region"][axis][1] for axis in ("u", "v")):
            errors.append(f"{tid}.{item['id']}: reversed region")
    uses_host = any(op["type"] == "host_offset" for op in template["geometry"]["operators"])
    required_inputs = template["capabilities"]["required_runtime_inputs"]
    if uses_host != ("host_depth" in required_inputs):
        errors.append(f"{tid}: host_depth runtime requirement mismatch")
    if set(required_inputs) - {"host_depth"}:
        errors.append(f"{tid}: unknown runtime input")
    if (template["geometry"]["depth_mode"] == "host_offset") != uses_host:
        errors.append(f"{tid}: host_offset ownership mismatch")
    if template["frame"]["depth_units"] != "bounds_width" or template["frame"]["angle_unit"] != "degree":
        errors.append(f"{tid}: units mismatch")
    return errors


def _inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValidationFailure(f"path escapes allowed root: {relative}")
    return path


def structure_errors(structure, templates):
    errors = []
    slots = structure.get("primary_slots", [])
    rules = structure.get("secondary_rules", [])
    slot_ids = {item["id"] for item in slots}
    _unique([item["id"] for item in slots], "primary_slots", errors)
    _unique([item["id"] for item in rules], "secondary_rules", errors)
    for item in slots + rules:
        if item["template_id"] not in templates:
            errors.append(f"structure {item['id']}: unknown template")
        for pattern in item.get("name_patterns", []):
            try:
                re.compile(pattern)
            except re.error as error:
                errors.append(f"structure {item['id']}: invalid regex: {error}")
        for host in item.get("host_slots", []):
            if host not in slot_ids:
                errors.append(f"structure {item['id']}: unknown host {host}")
        for alt in item.get("alternative_templates", []):
            if alt not in templates:
                errors.append(f"structure {item['id']}: unknown alternative template {alt}")
        definitions = {c["id"]: c for c in templates[item["template_id"]]["tunables"]} if item["template_id"] in templates else {}
        for key, value in item.get("parameter_overrides", {}).items():
            if key not in definitions or not definitions[key]["min"] <= value <= definitions[key]["max"]:
                errors.append(f"structure {item['id']}: invalid parameter override {key}")
    for relation in structure.get("relations", []):
        if relation["a"] not in slot_ids or relation["b"] not in slot_ids:
            errors.append("structure: unknown relation endpoint")
        if relation["kind"] not in {"above", "below", "left_of", "right_of"}:
            errors.append("structure: unsupported relation kind")
    for key, value, path in _walk(structure):
        if key in FORBIDDEN_IDENTITY_FIELDS:
            errors.append(f"structure{path}: model-specific identity")
        if isinstance(value, float) and not math.isfinite(value):
            errors.append(f"structure{path}: non-finite")
    return errors


def validate_catalog(root=ROOT):
    root = Path(root).resolve()
    folder = root / "templates"
    manifest_path = folder / "manifest.json"
    manifest = read_json(manifest_path)
    schema_path = _inside(folder, manifest["template_schema"])
    schema = read_json(schema_path)
    check_schema_subset(schema)
    errors, templates = [], {}
    if sha256(schema_path) != manifest["template_schema_sha256"]:
        errors.append("manifest: schema hash mismatch")
    filenames = manifest["template_files"]
    _unique(filenames, "manifest.template_files", errors)
    entries = {entry["id"]: entry for entry in manifest["templates"]}
    _unique([entry["id"] for entry in manifest["templates"]], "manifest.templates", errors)
    declared = set(filenames) | {manifest["template_schema"], "manifest.json"}
    unexpected = {p.name for p in folder.glob("*.json")} - declared
    if unexpected:
        errors.append(f"manifest: unlisted template JSON files {sorted(unexpected)}")
    for filename in filenames:
        path = _inside(folder, filename)
        value = read_json(path)
        structural = schema_errors(schema, value)
        errors.extend(f"{filename}: {error}" for error in structural)
        if structural:
            continue
        tid = value["id"]
        if tid in templates:
            errors.append(f"duplicate catalog template id {tid}")
        templates[tid] = value
        errors.extend(template_semantic_errors(value))
        entry = entries.get(tid)
        if entry is None:
            errors.append(f"{tid}: missing manifest entry")
        else:
            for key in ("id", "version", "family"):
                if entry[key] != value[key]:
                    errors.append(f"{tid}: manifest {key} mismatch")
            if entry["file"] != filename or entry["sha256"] != sha256(path):
                errors.append(f"{tid}: manifest filename/hash mismatch")
            if entry["representation"] != value["geometry"]["representation"] or entry["depth_mode"] != value["geometry"]["depth_mode"]:
                errors.append(f"{tid}: manifest geometry mismatch")
            if set(entry["operators"]) != {op["type"] for op in value["geometry"]["operators"]}:
                errors.append(f"{tid}: manifest operator list mismatch")
            if entry["required_runtime_inputs"] != value["capabilities"]["required_runtime_inputs"]:
                errors.append(f"{tid}: manifest runtime input mismatch")
    if set(templates) != set(entries):
        errors.append("manifest: template ID set mismatch")
    structures = []
    for name in manifest.get("structure_files", []):
        path = _inside(root, str((folder / name).resolve().relative_to(root)))
        data = read_json(path)
        errors.extend(structure_errors(data, templates))
        structures.append({"id": data["id"], "sha256": sha256(path),
                           "primary_slots": len(data["primary_slots"]),
                           "secondary_rules": len(data["secondary_rules"])})
    return {
        "schema_version": "semantic-template-validation/1",
        "validator": "stdlib catalog-specific JSON Schema subset plus semantic checks",
        "full_json_schema_implementation": False,
        "unsupported_schema_keywords": "rejected",
        "template_count": len(templates), "structures": structures,
        "manifest_sha256": sha256(manifest_path),
        "schema_sha256": sha256(schema_path),
        "errors": errors, "passed": not errors,
        "source_fit_verified": False, "rig_quality_verified": False, "model_modified": False,
    }


def self_test(root=ROOT):
    root = Path(root)
    schema = read_json(root / "templates/template.schema.json")
    sample = read_json(root / "templates/face_head.json")
    checks = []
    bad_schema = copy.deepcopy(schema)
    bad_schema["allOf"] = []
    try:
        check_schema_subset(bad_schema)
    except ValidationFailure:
        checks.append("unsupported_keyword_rejected")
    else:
        raise ValidationFailure("self-test: unsupported schema keyword was ignored")
    mutations = [
        ("unknown_operator", lambda t: t["geometry"]["operators"][0].update(type="unknown")),
        ("default_out_of_bounds", lambda t: t["tunables"][0].update(default=100)),
        ("unknown_parameter", lambda t: t["geometry"]["operators"][0].update(depth="missing_parameter")),
        ("axis_reversal", lambda t: t["guide_grid"]["rows"][1].update(v=0)),
        ("missing_required_hint", lambda t: t["hints"]["required"].pop()),
    ]
    for label, mutate in mutations:
        bad = copy.deepcopy(sample)
        mutate(bad)
        structural = schema_errors(schema, bad)
        if not structural and not template_semantic_errors(bad):
            raise ValidationFailure(f"self-test: {label} was accepted")
        checks.append(label + "_rejected")
    host = read_json(root / "templates/surface_layer.json")
    host["capabilities"]["required_runtime_inputs"] = []
    if not template_semantic_errors(host):
        raise ValidationFailure("self-test: missing host input was accepted")
    checks.append("missing_host_input_rejected")
    for label, text in (("duplicate_json_key", '{"a":1,"a":2}'),
                        ("nonfinite_json", '{"a":NaN}')):
        try:
            _loads(text)
        except ValidationFailure:
            checks.append(label + "_rejected")
        else:
            raise ValidationFailure(f"self-test: {label} was accepted")
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        report = validate_catalog(args.root)
        if args.self_test:
            report["self_tests"] = self_test(args.root)
    except (ValueError, KeyError, TypeError, OSError) as error:
        report = {"passed": False, "errors": [str(error)], "model_modified": False}
    text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
