"""Strict JSON, source identity and template parameter handling."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath


def _non_model_path(path):
    """Keep native model files out of generic filesystem helpers.

    Check before resolving/opening anything, then check the resolved target
    to reject ordinary symlink aliases. Windows stream syntax and trailing
    dots/spaces must not disguise a native-model suffix. This is a path guard,
    not content sniffing or protection against concurrent symlink replacement.
    """
    candidate = Path(path)
    def reject_native(value):
        leaf = PureWindowsPath(str(value)).name.split(":", 1)[0].rstrip(" .")
        if leaf.casefold().endswith((".inx", ".inp")):
            raise ValueError("INX/INP model I/O must use the NJC client; generic file access is forbidden")
    reject_native(candidate)
    reject_native(candidate.resolve())
    return candidate


def read_json(path):
    source = _non_model_path(path)
    def reject(value):
        raise ValueError(f"non-finite JSON constant: {value}")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(source.read_text(encoding="utf-8-sig"),
                      parse_constant=reject, object_pairs_hook=unique)


def write_json(path, value):
    destination = _non_model_path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True,
                  indent=2, allow_nan=False)
        stream.write("\n")


def digest(path):
    source = _non_model_path(path)
    h = hashlib.sha256()
    with source.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def json_digest(value):
    hasher = hashlib.sha256()
    encoder = json.JSONEncoder(sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"), allow_nan=False)
    for chunk in encoder.iterencode(value):
        hasher.update(chunk.encode("utf-8"))
    return hasher.hexdigest()


def finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def parameters(template, overrides=None):
    definitions = {item["id"]: item for item in template.get("tunables", [])}
    if len(definitions) != len(template.get("tunables", [])):
        raise ValueError("duplicate tunable id")
    overrides = overrides or {}
    unknown = set(overrides) - set(definitions)
    if unknown:
        raise ValueError(f"unknown parameters: {sorted(unknown)}")
    result = {}
    for key, definition in definitions.items():
        value = finite(overrides.get(key, definition["default"]), key)
        if not definition["min"] <= value <= definition["max"]:
            raise ValueError(f"{key} outside [{definition['min']}, {definition['max']}]")
        result[key] = value
    return result


def load_template(path):
    template = read_json(path)
    for key in ("id", "version", "guide_grid", "geometry", "landmarks", "tunables"):
        if key not in template:
            raise ValueError(f"template missing {key}")
    if not template["geometry"].get("operators"):
        raise ValueError("template has no executable depth operators")
    for name, coordinate in (("columns", "u"), ("rows", "v")):
        values = [finite(item[coordinate], name) for item in template["guide_grid"][name]]
        if len(values) < 2 or values[0] != 0 or values[-1] != 1:
            raise ValueError(f"{name} must span [0,1]")
        if any(a >= b for a, b in zip(values, values[1:])):
            raise ValueError(f"{name} must be strictly increasing")
    roles = [item["id"] for item in template["landmarks"]]
    if len(set(roles)) != len(roles):
        raise ValueError("duplicate landmark role")
    parameters(template)
    return template
