#!/usr/bin/env python3
"""Internal reference accounting using NJC-opened, fingerprinted PSD derivatives.

Opens models through NJC; never reads an INX/INP container in Python.
References must already have NJC snapshot fingerprints from the same PSD run.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re
import sys

from riglib.data import digest, json_digest, load_template, read_json, write_json
from riglib.landmarks import propose_landmarks
from riglib.model import observe_model
from riglib.live import Live
from riglib.structure import infer_structure, observe_groups

ROOT = Path(__file__).resolve().parents[1]


def summarize(observation, structure, landmarks):
    seeds, _ = observe_groups(observation)
    # Do not reuse the inference's grouping as the expected ownership set.
    parts = [node for node in observation["nodes"] if node["type"] == "Part"]
    all_parts = {str(node["uuid"]) for node in parts}
    active = {str(node["uuid"]) for node in parts if node.get("enabled_effective", True)
              and node.get("enabled_local", node.get("enabled", True))}
    grouped = [str(part) for seed in seeds for part in seed["parts"]]
    excluded = structure["excluded_parts"]
    excluded_ids = [str(row["part"]) for row in excluded]
    assigned = [str(row["part"]) for row in structure["part_assignments"]]
    surface_ids = {surface["id"] for surface in structure["surfaces"]}
    proposals = [point for surface in landmarks["surfaces"].values()
                 for point in surface["landmarks"]]
    checks = {
        "every_active_part_owned_once": len(assigned) == len(set(assigned)) and set(assigned) == active,
        "observation_groups_cover_active_parts": len(grouped) == len(set(grouped)) and set(grouped) == active,
        "excluded_parts_partition_source": len(excluded_ids) == len(set(excluded_ids))
                                           and set(excluded_ids) == all_parts - active
                                           and not (set(excluded_ids) & set(assigned))
                                           and set(excluded_ids) | set(assigned) == all_parts,
        "every_assignment_surface_exists": all(row["surface"] in surface_ids
                                               for row in structure["part_assignments"]),
        "landmark_surfaces_match": set(landmarks["surfaces"]) == surface_ids,
        "source_identity_matches": observation["source"] == structure["source"],
        "proposal_status_preserved": structure["status"] == "structural_proposal"
                                     and landmarks["status"] == "landmark_proposal",
        "no_fit_claim": landmarks["source_fit_verified"] is False
                        and all(row["source_fit_verified"] is False for row in landmarks["surfaces"].values()),
        "priors_not_measurements": all(point["measurement_based"] is False
                                       for point in proposals if point["state"] == "template_prior"),
        "no_model_mutation_claim": structure["live_model_modified"] is False and landmarks["model_modified"] is False,
    }
    groups = {group["id"]: group for group in structure["group_candidates"]}
    chosen = structure["hypotheses"][structure["selected_hypothesis"]]["assignment"]
    primary = {role: None if gid is None else {
        "group": gid, "name": groups[gid]["name"], "parts": groups[gid]["parts"],
        "bounds": groups[gid]["bounds"], "candidate_kind": groups[gid]["candidate_kind"],
    } for role, gid in chosen.items()}
    return {
        "source": observation["source"], "checks": checks, "checks_passed": all(checks.values()),
        "counts": {
            "nodes": len(observation["nodes"]),
            "node_types": dict(sorted(Counter(node["type"] for node in observation["nodes"]).items())),
            "parameters": len(observation["parameters"]), "active_parts": len(active),
            "excluded_parts": len(excluded), "observation_seeds": len(seeds),
            "group_candidates": len(groups), "shared_surfaces": len(surface_ids),
            "structure_questions": len(structure["questions"]),
            "empty_candidate_questions": sum(question.get("candidates", None) == [] for question in structure["questions"]),
            "landmark_states": dict(sorted(Counter(point["state"] for point in proposals).items())),
            "missing_required_roles": sum(len(row["missing_roles"]) for row in landmarks["surfaces"].values()),
        },
        "coverage": structure["coverage"], "primary_assignment": primary,
        "normalization": structure.get("normalization", {"method": "enabled_observation_bounds"}),
        "template_use": dict(sorted(Counter(surface["template_id"] or "unresolved"
                                             for surface in structure["surfaces"]).items())),
        "questions": structure["questions"],
        "excluded_parts": excluded,
        "missing_required_roles": {sid: row["missing_roles"] for sid, row in landmarks["surfaces"].items()
                                   if row["missing_roles"]},
    }


def run(config_path, out_path, *, njc):
    config_path, out_path = Path(config_path).resolve(), Path(out_path).resolve()
    config = read_json(config_path)
    if config.get("schema_version") != "rig-reference-set/1":
        raise ValueError("unsupported reference set schema")
    entries = config["references"]
    ids = [entry["id"] for entry in entries]
    if not ids or len(ids) != len(set(ids)) or any(not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", rid) for rid in ids):
        raise ValueError("reference IDs must be unique lowercase path-safe identifiers")
    paths = {}
    for entry in entries:
        paths[entry["id"]] = (config_path.parent / entry["model"]).resolve()
        if not re.fullmatch(r"[0-9a-f]{64}", entry.get("njc_metadata_sha256", "")):
            raise ValueError("Every internal reference requires its prior NJC snapshot fingerprint")
        if out_path == paths[entry["id"]] or out_path in paths[entry["id"]].parents:
            raise ValueError("output directory cannot contain a source model")
    spec_path = ROOT / "structures" / "character.json"
    template_paths = sorted((ROOT / "templates").glob("*.json"))
    code_paths = [Path(__file__).resolve(), *sorted((ROOT / "scripts" / "riglib").glob("*.py"))]
    input_paths = [config_path, spec_path, *template_paths, *code_paths]
    before_hashes = {str(path): digest(path) for path in input_paths}
    spec = read_json(spec_path)
    catalog = {path.stem: load_template(path) for path in template_paths
               if path.name not in ("manifest.json", "template.schema.json")}
    summaries = {}
    client = Live(njc)
    for entry in entries:
        rid = entry["id"]
        client.open(paths[rid])
        observation = observe_model(client=client, require_parameters=False,
                                    expected_metadata_sha256=entry["njc_metadata_sha256"])
        structure = infer_structure(observation, spec)
        landmarks = propose_landmarks(observation, structure, catalog)
        summary = summarize(observation, structure, landmarks)
        after = observe_model(client=client, include_geometry=False, require_parameters=False)["source"]
        summary["checks"]["source_metadata_unchanged"] = after == observation["source"]
        summary["checks_passed"] = all(summary["checks"].values())
        summary["reference_selection"] = {key: value for key, value in entry.items() if key != "model"}
        summaries[rid] = summary
        for name, value in (("observation", observation), ("structure", structure), ("landmarks", landmarks)):
            write_json(out_path / rid / f"{name}.json", value)
    after_hashes = {str(path): digest(path) for path in input_paths}
    unchanged = before_hashes == after_hashes
    report = {
        "schema_version": "rig-reference-audit/1", "references": summaries,
        "checks_passed": unchanged and all(row["checks_passed"] for row in summaries.values()),
        "execution_inputs_unchanged": unchanged,
        "config_sha256": before_hashes[str(config_path)], "specification_sha256": json_digest(spec),
        "template_manifest_sha256": before_hashes[str(ROOT / "templates" / "manifest.json")],
        "actual_template_sha256": {path.name: before_hashes[str(path)] for path in template_paths},
        "implementation_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): before_hashes[str(path)]
                                  for path in code_paths},
        "comparison": {
            "template_use": {rid: row["template_use"] for rid, row in summaries.items()},
            "counts": {rid: row["counts"] for rid, row in summaries.items()},
        },
        "limitations": [
            "Counts measure proposal accounting, not anatomical recognition accuracy.",
            "Each model is opened via NJC and compared with its expected NJC snapshot fingerprint.",
            "Only public NJC node data is inspected; complete parameter properties and file bytes are not verified.",
            "Visual observations are separately recorded and are not inferred by this script.",
        ],
        "model_modified": False, "source_fit_verified": False,
    }
    write_json(out_path / "audit.json", report)
    lines = ["# 共通コードによる参照監査", "",
             "これは保存モデルの構造候補の監査であり、形状適合・完成リグ・外観の合格ではない。", "",
             "| 参照 | 全Part | 有効Part | 提案面 | 未解決面 | 未解決の必須基準点 |",
             "|---|---:|---:|---:|---:|---:|"]
    for rid, row in summaries.items():
        counts = row["counts"]
        lines.append(f"| {rid} | {counts['node_types'].get('Part', 0)} | {counts['active_parts']} | "
                     f"{counts['shared_surfaces']} | {row['coverage']['unresolved_surfaces']} | {counts['missing_required_roles']} |")
    lines += ["", f"所有・参照・入力不変性の検査: {'PASS' if report['checks_passed'] else 'FAIL'}。", "",
              "コード・実template・source metadataのhashと未解決候補は [audit.json](audit.json) に記録。",
              "各参照の structure.json に主構造候補・正規化frame・スコアを保存。",
              "モデルの変更・保存は行わない。読込と構造読取はすべてnjc経由。完全なparameter設定とファイル内容の一致は未検証。", ""]
    (out_path / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--njc", required=True)
    args = parser.parse_args()
    try:
        report = run(args.config, args.out, njc=args.njc)
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"reference accounting checks: {'PASS' if report['checks_passed'] else 'FAIL'}; {len(report['references'])} references")
    return 0 if report["checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
