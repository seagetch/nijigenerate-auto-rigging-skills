#!/usr/bin/env python3
"""One CLI for structural observation, shared-surface generation and validation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import numpy as np
from riglib.data import read_json, write_json, load_template, parameters

ROOT = Path(__file__).resolve().parents[1]


def template_path(value):
    explicit = Path(value)
    return explicit if explicit.is_file() else ROOT / "templates" / f"{value}.json"


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("catalog")
    p.add_argument("--out")
    p = sub.add_parser("validate-templates")
    p.add_argument("--out")
    p = sub.add_parser("prepare-psd", help="Only external character input: one PSD; extract internal observations")
    p.add_argument("--psd", required=True)
    p.add_argument("--out", required=True, help="Output directory for internally generated PSD observations")
    p = sub.add_parser("inspect-image")
    p.add_argument("--image", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("inspect-model")
    p.add_argument("--njc", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("assemble-model")
    p.add_argument("--njc", required=True)
    p.add_argument("--roles", default=str(ROOT/"structures"/"material-roles.json"))
    p.add_argument("--evidence")
    p.add_argument("--out", required=True)
    p = sub.add_parser("propose-core-landmarks")
    p.add_argument("--observation", required=True); p.add_argument("--assembly", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("infer-structure")
    p.add_argument("--njc", required=True)
    p.add_argument("--spec", default=str(ROOT/"structures"/"character.json"))
    p.add_argument("--hints"); p.add_argument("--out", required=True)
    p = sub.add_parser("propose-landmarks")
    p.add_argument("--observation",required=True); p.add_argument("--structure",required=True)
    p.add_argument("--out",required=True)
    p = sub.add_parser("fit-surface")
    p.add_argument("--template", required=True); p.add_argument("--image", required=True)
    p.add_argument("--hints"); p.add_argument("--mesh", nargs=2, type=int, default=[17,21])
    p.add_argument("--out", required=True)
    p = sub.add_parser("evaluate")
    p.add_argument("--fit", required=True); p.add_argument("--out", required=True)
    for axis in ("yaw","pitch","roll"):
        p.add_argument("--"+axis,type=float,default=None)
    p = sub.add_parser("suite")
    p.add_argument("--fit", required=True); p.add_argument("--out", required=True)
    p.add_argument("--extent",type=float,default=25); p.add_argument("--render",action="store_true")
    p = sub.add_parser("register-scene")
    p.add_argument("--observation",required=True); p.add_argument("--structure",required=True)
    p.add_argument("--surfaces",required=True); p.add_argument("--out",required=True)
    p = sub.add_parser("evaluate-scene")
    p.add_argument("--scene",required=True); p.add_argument("--poses",required=True)
    p.add_argument("--out",required=True)
    p = sub.add_parser("compile-njc")
    p.add_argument("--snapshot",required=True); p.add_argument("--sampled",required=True)
    p.add_argument("--out",required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare-psd":
        from riglib.psd_source import prepare_psd
        result = prepare_psd(args.psd, args.out)
        print(json.dumps({"status":result["status"],
                          "path":str((Path(args.out)/"psd-source.json").resolve()),
                          "external_character_input":"psd_only",
                          "rig_completed":False}, ensure_ascii=False))
        return 0 if result["status"] == "psd_observation_ready" else 2
    elif args.command in ("catalog","validate-templates"):
        from riglib.geometry import evaluate_depth, apply_local_corrections
        templates = [load_template(p) for p in sorted((ROOT/"templates").glob("*.json"))
                     if p.name not in ("manifest.json","template.schema.json")]
        if args.command == "catalog":
            result = [{"id":t["id"],"family":t["family"],"capabilities":t.get("capabilities"),
                       "required_landmarks":[l["id"] for l in t["landmarks"] if l.get("required")]}
                      for t in templates]
        else:
            checks = []
            uv = np.array([[0,0],[.25,.25],[.5,.5],[.75,.75],[1,1]],dtype=float)
            for t in templates:
                values = parameters(t)
                host = np.zeros(len(uv)) if any(o["type"] == "host_offset" for o in t["geometry"]["operators"]) else None
                depth = evaluate_depth(uv,t["geometry"]["operators"],values,host_depth=host)
                for pose in ({},{"yaw":25},{"pitch":-25},{"yaw":-25,"pitch":25,"roll":10}):
                    corrected = apply_local_corrections(uv,uv,pose,t.get("correction_rules",[]),values)
                    if not np.isfinite(corrected).all():
                        raise ValueError(f"nonfinite correction: {t['id']}")
                checks.append({"id":t["id"],"finite":bool(np.isfinite(depth).all()),
                               "synthetic_host_used":host is not None})
            structure = read_json(ROOT/"structures"/"character.json")
            ids = {t["id"] for t in templates}
            for slot in structure["primary_slots"]+structure["secondary_rules"]:
                if slot["template_id"] not in ids:
                    raise ValueError("structure references absent template")
            result = {"templates":checks,"count":len(checks),"structure_references_valid":True,
                      "scope":"synthetic operator/schema checks; no artwork quality claim"}
    elif args.command == "inspect-image":
        from riglib.observe import observe_image
        result = observe_image(args.image)
    elif args.command == "inspect-model":
        from riglib.model import observe_model
        from riglib.live import Live
        result = observe_model(client=Live(args.njc),require_parameters=False)
    elif args.command == "assemble-model":
        from riglib.model import observe_model
        from riglib.assembly import assemble_model
        from riglib.live import Live
        result = assemble_model(observe_model(client=Live(args.njc),require_parameters=False), read_json(args.roles),
                                read_json(args.evidence) if args.evidence else None)
    elif args.command == "propose-core-landmarks":
        from riglib.assembly import landmark_observation_structure
        from riglib.landmarks import propose_landmarks
        observation, assembly = read_json(args.observation), read_json(args.assembly)
        from riglib.data import json_digest
        if assembly["observation_sha256"] != json_digest(observation):
            raise ValueError("assembly observation hash mismatch")
        signed = dict(assembly); signed.pop("content_sha256", None)
        if assembly.get("content_sha256") != json_digest(signed):
            raise ValueError("assembly content hash mismatch")
        structure = landmark_observation_structure(assembly)
        catalog = {s["template_id"]: load_template(template_path(s["template_id"])) for s in structure["surfaces"]}
        result = propose_landmarks(observation, structure, catalog)
        result["assembly_sha256"] = assembly["content_sha256"]
    elif args.command == "infer-structure":
        from riglib.model import observe_model
        from riglib.structure import infer_structure
        from riglib.live import Live
        result = infer_structure(observe_model(client=Live(args.njc),require_parameters=False),read_json(args.spec),
                                 read_json(args.hints) if args.hints else None)
    elif args.command == "fit-surface":
        from riglib.pipeline import fit_surface
        result = fit_surface(template_path(args.template),args.image,
                             read_json(args.hints) if args.hints else None,tuple(args.mesh))
    elif args.command == "propose-landmarks":
        from riglib.landmarks import propose_landmarks
        catalog={}
        for path in sorted((ROOT/"templates").glob("*.json")):
            if path.name not in ("manifest.json","template.schema.json"):
                template=load_template(path);catalog[template["id"]]=template
        result=propose_landmarks(read_json(args.observation),read_json(args.structure),catalog)
    elif args.command == "evaluate":
        from riglib.pipeline import evaluate_surface
        fit=read_json(args.fit)
        result = evaluate_surface(fit,{a:getattr(args,a) if getattr(args,a) is not None else fit["neutral_pose"][a]
                                       for a in ("yaw","pitch","roll")})
    elif args.command == "suite":
        from riglib.pipeline import sample_pose_suite, verify_fit
        fit = read_json(args.fit); verify_fit(fit)
        result = {"schema_version":"rig-suite/1","fit_sha256":fit["content_sha256"],
                  "poses":sample_pose_suite(fit,args.extent),"engine_render_verified":False}
        out = Path(args.out); out.mkdir(parents=True,exist_ok=True)
        write_json(out/"poses.json",result)
        if args.render:
            from riglib.render import render_sheet
            render_sheet(fit,result["poses"],out/"preview.png")
        print(json.dumps({"status":"written","path":str(out.resolve()),"poses":len(result["poses"])}))
        return 0
    elif args.command == "register-scene":
        from riglib.scene import register_scene
        specs = read_json(args.surfaces)
        for spec in specs.values():
            if isinstance(spec.get("fit"),str):
                spec["fit"] = read_json(spec["fit"])
        result = register_scene(read_json(args.observation),read_json(args.structure),specs)
    elif args.command == "evaluate-scene":
        from riglib.scene import evaluate_scene
        result = evaluate_scene(read_json(args.scene),read_json(args.poses))
    elif args.command == "compile-njc":
        from riglib.njc import export_plan
        result = export_plan(read_json(args.snapshot),read_json(args.sampled))
    else:
        raise ValueError("unknown command")
    if args.out:
        write_json(args.out,result)
        status = result.get("status","written") if isinstance(result,dict) else "written"
        print(json.dumps({"status":status,"path":str(Path(args.out).resolve())},ensure_ascii=False))
        return 2 if status in ("needs_landmarks","needs_coverage","unresolved") else 0
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except (ValueError,KeyError,TypeError,OSError,RuntimeError) as error:
        print(json.dumps({"status":"error","message":str(error)},ensure_ascii=False),file=sys.stderr)
        raise SystemExit(1)
