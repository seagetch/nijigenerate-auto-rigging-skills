from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Apply an exact GridDeformer BoneSource map to the active nijigenerate "
            "model through njc. Direct INX editing and FileCommand_OpenFile are never used."
        )
    )
    parser.add_argument(
        "--njc",
        type=Path,
        help="Explicit njc executable. Otherwise use NJC_PATH, then process PATH.",
    )
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--save", type=Path)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow FileCommand_SaveFile to use an existing requested destination.",
    )
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--allow-subset",
        action="store_true",
        help="Allow the map to omit GridDeformers. Default requires every GridDeformer.",
    )
    return parser.parse_args()


class Njc:
    def __init__(self, executable: Path):
        if not executable.is_file():
            raise RuntimeError(f"njc does not exist: {executable}")
        self.executable = executable

    def run(self, *args: str) -> dict:
        process = subprocess.run(
            [str(self.executable), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return json.loads(process.stdout)

    def call(self, name: str, payload: dict) -> dict:
        outer = self.run(
            "tools",
            "call",
            name,
            "--json",
            json.dumps(payload, ensure_ascii=False),
        )
        for item in outer.get("result", {}).get("content", []):
            if item.get("type") != "text":
                continue
            try:
                inner = json.loads(item["text"])
            except json.JSONDecodeError:
                continue
            if isinstance(inner, dict):
                if inner.get("succeeded") is False:
                    raise RuntimeError(f"{name} failed: {inner}")
                return inner
        raise RuntimeError(f"{name} returned no JSON result")

    def read(self, uuid: int) -> dict:
        outer = self.run("read", str(uuid))
        item = json.loads(outer["result"]["contents"][0]["text"])["item"]
        if item is None:
            raise RuntimeError(f"node does not exist: {uuid}")
        return item["data"]

    def tree(self) -> dict[int, dict]:
        outer = self.run("find", "*")
        items = json.loads(outer["result"]["contents"][0]["text"])["items"]
        result: dict[int, dict] = {}

        def visit(children: list[dict], parent: int | None = None) -> None:
            for item in children:
                uuid = int(item["uuid"])
                result[uuid] = {
                    "uuid": uuid,
                    "name": item["name"],
                    "type": item["data"]["type"],
                    "parent": parent,
                }
                visit(item.get("children", []), uuid)

        visit(items)
        return result


def resolve_njc(explicit: Path | None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    configured = os.environ.get("NJC_PATH")
    if configured:
        candidates.append(Path(configured))
    discovered = shutil.which("njc") or shutil.which("njc.exe")
    if discovered:
        candidates.append(Path(discovered))
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.is_file():
            return resolved
    raise RuntimeError(
        "njc executable was not found. Pass --njc, set NJC_PATH, "
        "or place njc on the process PATH."
    )


def stable_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_map(document: dict) -> tuple[int, list[dict]]:
    root = document.get("root", document.get("depthRigRoot"))
    if root is None:
        raise RuntimeError("mapping requires root or depthRigRoot")
    raw_targets = document.get("targets", document.get("rows"))
    if not isinstance(raw_targets, list) or not raw_targets:
        raise RuntimeError("mapping requires non-empty targets or rows")
    targets = []
    for raw in raw_targets:
        target = raw.get("target", raw.get("targetUuid"))
        sources = raw.get("sources", raw.get("sourceBoneUuids"))
        if target is None or not isinstance(sources, list) or not sources:
            raise RuntimeError(f"invalid mapping row: {raw}")
        source_uuids = [
            int(source["uuid"]) if isinstance(source, dict) else int(source)
            for source in sources
        ]
        if len(source_uuids) != len(set(source_uuids)):
            raise RuntimeError(f"duplicate source UUIDs for target {target}")
        targets.append(
            {
                "target": int(target),
                "targetName": raw.get("targetName"),
                "sources": source_uuids,
                "sourceNames": raw.get("sourceNames", []),
            }
        )
    if len({item["target"] for item in targets}) != len(targets):
        raise RuntimeError("duplicate target UUIDs in mapping")
    return int(root), targets


def source_result(njc: Njc, root: int, target: int) -> dict:
    return njc.call(
        "DepthBoneCommand_ListDepthBoneSources",
        {"root": root, "target": target},
    )["result"]


def is_prefix(current: list[int], expected: list[int]) -> bool:
    return current == expected[: len(current)]


def main() -> None:
    args = parse_args()
    if args.save and args.save.exists() and not args.overwrite:
        raise RuntimeError(f"save target already exists: {args.save}")
    mapping_document = json.loads(args.mapping.read_text(encoding="utf-8"))
    root_uuid, targets = normalize_map(mapping_document)
    njc = Njc(resolve_njc(args.njc))
    tree_before = njc.tree()
    if tree_before.get(root_uuid, {}).get("type") != "DepthRigRoot":
        raise RuntimeError(f"root is not a DepthRigRoot: {root_uuid}")

    grid_uuids = {
        uuid for uuid, item in tree_before.items() if item["type"] == "GridDeformer"
    }
    mapped_targets = {item["target"] for item in targets}
    if not args.allow_subset and mapped_targets != grid_uuids:
        missing = sorted(grid_uuids - mapped_targets)
        extra = sorted(mapped_targets - grid_uuids)
        raise RuntimeError(
            f"mapping must cover every GridDeformer; missing={missing}, extra={extra}"
        )

    ancestor_cache: dict[int, bool] = {}

    def belongs_to_root(uuid: int) -> bool:
        if uuid in ancestor_cache:
            return ancestor_cache[uuid]
        cursor = uuid
        visited: set[int] = set()
        while cursor in tree_before and cursor not in visited:
            if cursor == root_uuid:
                ancestor_cache[uuid] = True
                return True
            visited.add(cursor)
            parent = tree_before[cursor]["parent"]
            if parent is None:
                break
            cursor = parent
        ancestor_cache[uuid] = False
        return False

    for item in targets:
        target_node = tree_before.get(item["target"])
        if not target_node or target_node["type"] != "GridDeformer":
            raise RuntimeError(f"target is not a GridDeformer: {item}")
        for source in item["sources"]:
            bone = tree_before.get(source)
            if not bone or bone["type"] != "DepthBone":
                raise RuntimeError(f"source is not a DepthBone: {source}")
            if not belongs_to_root(source):
                raise RuntimeError(
                    f"DepthBone {source} is not a descendant of root {root_uuid}"
                )

    before_hashes = {
        uuid: stable_hash(njc.read(uuid))
        for uuid in tree_before
        if uuid != root_uuid
    }
    before_pairs = njc.call("ViewportCommand_ListFlipPairs", {}).get("result", [])
    before_pair_set = {
        (int(pair["leftUuid"]), int(pair["rightUuid"])) for pair in before_pairs
    }

    preflight = []
    for item in targets:
        current = [
            int(value)
            for value in source_result(njc, root_uuid, item["target"])[
                "sourceBoneUuids"
            ]
        ]
        expected = item["sources"]
        if not is_prefix(current, expected):
            raise RuntimeError(
                f"target {item['target']} is not resumable: "
                f"current={current}, expected={expected}"
            )
        preflight.append(
            {
                **item,
                "current": current,
                "state": (
                    "exact"
                    if current == expected
                    else "empty"
                    if not current
                    else "prefix"
                ),
                "missingSuffix": expected[len(current) :],
            }
        )

    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "DRY RUN / NOT APPLIED",
                    "root": root_uuid,
                    "targets": preflight,
                    "allTargetsResumable": True,
                    "inxDirectEditUsed": False,
                    "fileCommandOpenFileUsed": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    commands = []
    for item in preflight:
        for bone in item["missingSuffix"]:
            payload = {
                "root": root_uuid,
                "target": item["target"],
                "bone": bone,
            }
            njc.call("DepthBoneCommand_AddDepthBoneSource", payload)
            commands.append(
                {"command": "DepthBoneCommand_AddDepthBoneSource", **payload}
            )

    readback = []
    for item in targets:
        actual = source_result(njc, root_uuid, item["target"])
        actual_uuids = [int(value) for value in actual["sourceBoneUuids"]]
        if actual_uuids != item["sources"]:
            raise RuntimeError(
                f"source readback mismatch for {item['target']}: {actual_uuids}"
            )
        if len(actual_uuids) != len(set(actual_uuids)):
            raise RuntimeError(f"duplicate source readback for {item['target']}")
        inline_settings = {
            int(source["uuid"]): {
                "weight": float(source["weight"]),
                "depthOffset": float(source["depthOffset"]),
                "depthScale": float(source["depthScale"]),
            }
            for source in actual["sources"]
        }
        if set(inline_settings) != set(item["sources"]):
            raise RuntimeError(f"inline setting UUID mismatch for {item['target']}")
        for uuid, settings in inline_settings.items():
            if settings != {
                "weight": 1.0,
                "depthOffset": 0.0,
                "depthScale": 1.0,
            }:
                raise RuntimeError(
                    f"non-default source settings for {item['target']}/{uuid}: "
                    f"{settings}"
                )
        readback.append(
            {
                **item,
                "actualSourceBoneUuids": actual_uuids,
                "inlineSettings": inline_settings,
                "exact": True,
            }
        )

    tree_after = njc.tree()
    if {
        uuid: (item["name"], item["type"], item["parent"])
        for uuid, item in tree_before.items()
    } != {
        uuid: (item["name"], item["type"], item["parent"])
        for uuid, item in tree_after.items()
    }:
        raise RuntimeError("tree changed during BoneSource assignment")
    for uuid, before_hash in before_hashes.items():
        if stable_hash(njc.read(uuid)) != before_hash:
            raise RuntimeError(f"non-DepthRigRoot node changed: {uuid}")
    after_pairs = njc.call("ViewportCommand_ListFlipPairs", {}).get("result", [])
    after_pair_set = {
        (int(pair["leftUuid"]), int(pair["rightUuid"])) for pair in after_pairs
    }
    if before_pair_set != after_pair_set:
        raise RuntimeError("flip pair set changed")

    if args.save:
        njc.call("FileCommand_SaveFile", {"file": str(args.save)})

    audit = {
        "schema": "nijigenerate-bone-source-apply-audit-v1",
        "status": "APPLIED / VERIFIED",
        "root": root_uuid,
        "preflight": preflight,
        "readback": readback,
        "checks": {
            "allTargetsExact": True,
            "allSourcesUnique": True,
            "allInlineSettingsDefault": True,
            "nonDepthRigRootNodeHashesPreserved": True,
            "treeUnchanged": True,
            "flipPairsUnchanged": True,
        },
        "commands": commands,
        "save": str(args.save) if args.save else None,
        "inxDirectEditUsed": False,
        "fileCommandOpenFileUsed": False,
        "computerUseUsed": False,
    }
    if args.audit:
        if args.audit.exists():
            raise RuntimeError(f"audit target already exists: {args.audit}")
        args.audit.parent.mkdir(parents=True, exist_ok=True)
        args.audit.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
