"""Reproducible fitting and evaluation of a SHARED surface, not a Part recipe."""
from __future__ import annotations
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from . import VERSION
from .data import digest, json_digest, load_template, parameters, read_json
from .observe import observe_image, resolve_landmarks
from .geometry import (fit_guide_grid, sample_grid, validate_grid, evaluate_depth,
                       rotate_points, apply_local_corrections)


def triangles(rows, columns):
    result = []
    for y in range(rows - 1):
        for x in range(columns - 1):
            i = y * columns + x
            result.extend([[i, i+1, i+columns+1], [i, i+columns+1, i+columns]])
    return result


def _axis(lines, count):
    if not 2 <= count <= 129:
        raise ValueError("mesh resolution must be 2..129 per axis")
    # Preserve exact semantic lines; floating-point near-duplicates such as
    # 0.3 and linspace's 0.30000000000000004 must not create zero-area cells.
    values = [float(value) for value in lines]
    for value in np.linspace(0,1,count):
        if all(abs(float(value)-existing)>1e-10 for existing in values):
            values.append(float(value))
    return np.array(sorted(values))


def _fit_controls(u,v,bounds,landmarks):
    corner_keys={(0.,0.),(1.,0.),(0.,1.),(1.,1.)}
    keys=[tuple(float(x) for x in point["uv"]) for point in landmarks]
    if len(keys)==4 and set(keys)==corner_keys:
        # Four boundary corners define a bilinear chart exactly. A TPS of these
        # points can bow a straight material edge and clip the source artwork.
        corners={key:np.asarray(point["xy"],float) for key,point in zip(keys,landmarks)}
        uu,vv=np.meshgrid(u,v)
        grid=((1-uu)*(1-vv))[:,:,None]*corners[(0.,0.)]
        grid+=(uu*(1-vv))[:,:,None]*corners[(1.,0.)]
        grid+=((1-uu)*vv)[:,:,None]*corners[(0.,1.)]
        grid+=(uu*vv)[:,:,None]*corners[(1.,1.)]
        return grid,"four_corner_bilinear"
    return fit_guide_grid(u,v,bounds,landmarks),"thin_plate_landmark_fit"


def _host_values(hints, uv):
    spec = hints.get("host")
    if not spec:
        return None, None
    if spec.get("mapping") != "same_material_uv":
        raise ValueError("host.mapping must explicitly be same_material_uv")
    factor = spec.get("host_to_source_scale")
    if isinstance(factor,bool) or not isinstance(factor,(int,float)) or not np.isfinite(factor) or factor<=0:
        raise ValueError("host.host_to_source_scale must explicitly convert host pixels to this source's units")
    host = read_json(spec["fit"])
    verify_fit(host)
    grid = np.asarray(host["depth"]).reshape(len(host["mesh"]["v_lines"]),
                                            len(host["mesh"]["u_lines"]))
    depth = np.asarray(sample_grid(grid[:, :, None], host["mesh"]["u_lines"],
                                   host["mesh"]["v_lines"], uv)).reshape(-1)
    return depth*factor, {"path": str(Path(spec["fit"]).resolve()), "sha256": digest(spec["fit"]),
                         "mapping": "same_material_uv", "host_to_source_scale":factor}


def alpha_coverage(image_path, xy, faces, threshold=16):
    with Image.open(image_path) as source:
        alpha = np.asarray(source.convert("RGBA").getchannel("A")) > 0
        mask = Image.new("L",source.size,0)
    draw=ImageDraw.Draw(mask)
    for tri in faces:
        draw.polygon([tuple(xy[i]) for i in tri],fill=255)
    exact=np.asarray(mask)>0
    # One pixel is only raster edge quantization tolerance, explicitly reported.
    tolerant=np.asarray(mask.filter(ImageFilter.MaxFilter(3)))>0
    count=int(np.count_nonzero(alpha & ~tolerant))
    return {"alpha_pixels":int(alpha.sum()),"coverage_alpha_threshold":1,"observation_alpha_threshold":threshold,"uncovered_pixels":count,
            "uncovered_without_raster_tolerance":int(np.count_nonzero(alpha & ~exact)),
            "raster_tolerance_pixels":1,"fully_covered_with_tolerance":count==0}


def fit_surface(template_path, image_path, hints=None, resolution=(17, 21), threshold=16):
    hints = hints or {}
    template = load_template(template_path)
    observation = observe_image(image_path, threshold)
    landmarks, missing = resolve_landmarks(template, observation, hints)
    if missing:
        return {"schema_version": "rig-fit-request/1", "status": "needs_landmarks",
                "template_id": template["id"], "observation": observation,
                "landmarks_found": landmarks, "missing_roles": missing,
                "message": "Supply only these unresolved semantic anchors; no depth arrays or pose vertices."}
    values = parameters(template, hints.get("parameters"))
    bounds = hints.get("bounds", observation["bounds"])
    if len(bounds) != 4 or not np.isfinite(bounds).all() or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        raise ValueError("invalid fit bounds")
    u = [item["u"] for item in template["guide_grid"]["columns"]]
    v = [item["v"] for item in template["guide_grid"]["rows"]]
    control,fit_method = _fit_controls(u, v, bounds, landmarks)
    grid_check = validate_grid(control)
    mu, mv = _axis(u, resolution[0]), _axis(v, resolution[1])
    uv = np.array([[x, y] for y in mv for x in mu])
    xy = np.asarray(sample_grid(control, u, v, uv))
    validate_grid(xy.reshape(len(mv), len(mu), 2))
    faces=triangles(len(mv),len(mu))
    coverage=alpha_coverage(image_path,xy,faces,threshold)
    if not coverage["fully_covered_with_tolerance"]:
        return {"schema_version":"rig-fit-request/1","status":"needs_coverage",
                "template_id":template["id"],"observation":observation,"coverage":coverage,
                "message":"Fitted chart does not cover source alpha; repair support/registration without cropping artwork."}
    scale = float(bounds[2] - bounds[0])
    host_depth, host_identity = _host_values(hints, uv)
    z = np.asarray(evaluate_depth(uv, template["geometry"]["operators"], values,
                   host_depth=None if host_depth is None else host_depth/scale)).reshape(-1) * scale
    if z.shape != (len(xy),) or not np.isfinite(z).all():
        raise ValueError("depth kernel returned invalid output")
    pivot = hints.get("pivot", [(bounds[0]+bounds[2])/2, (bounds[1]+bounds[3])/2, 0.0])
    if len(pivot) != 3 or not np.isfinite(pivot).all():
        raise ValueError("pivot must be finite [x,y,z]")
    neutral = pose_dict(hints.get("neutral_pose", {}))
    artifact = {
        "schema_version": "rig-fit/1", "status": "fitted_unreviewed", "engine_version": VERSION,
        "template": template, "template_source": {"path": str(Path(template_path).resolve()),
                                                     "sha256": digest(template_path)},
        "source": observation["source"], "observation": observation,
        "frame": {"x": "image-right", "y": "image-down", "z": "toward-viewer",
                  "units": "source-pixel", "angles": "degree",
                  "engine_axis_calibration": "not-performed"},
        "bounds": list(bounds), "depth_scale": scale, "parameters": values,
        "landmarks": landmarks, "control": {"u_lines": u, "v_lines": v, "xy": control.tolist(),"fit_method":fit_method},
        "mesh": {"u_lines": mu.tolist(), "v_lines": mv.tolist(), "uv": uv.tolist(),
                 "rest_xy": xy.tolist(), "triangles": faces},
        "depth": z.tolist(), "pivot": list(pivot), "neutral_pose": neutral,
        "host": host_identity, "grid_validation": grid_check,"alpha_coverage":coverage,
        "assumptions": ["Depth is a template prior, not a single-image depth measurement.",
                        "This is one shared surface chart; Part membership is resolved by scene structure.",
                        "Attachments, topology and hidden artwork are not inferred from this isolated image."],
        "live_model_modified": False,
    }
    # Content integrity avoids replaying an edited fit as its previous identity.
    artifact["content_sha256"] = json_digest(artifact)
    result = evaluate_surface(artifact, neutral)
    if result["validation"]["max_displacement"] > 1e-7:
        raise ValueError("neutral preservation failed")
    return artifact


def verify_fit(fit):
    if fit.get("schema_version") != "rig-fit/1":
        raise ValueError("not a fitted surface artifact")
    expected = fit.get("content_sha256")
    payload = {key: value for key, value in fit.items() if key != "content_sha256"}
    if expected != json_digest(payload):
        raise ValueError("fit integrity mismatch; refit after changing inputs")


def pose_dict(pose):
    if not isinstance(pose, dict) or set(pose) - {"yaw", "pitch", "roll"}:
        raise ValueError("pose must contain only yaw/pitch/roll in degrees")
    if any(isinstance(value,bool) or not isinstance(value,(int,float)) for value in pose.values()):
        raise ValueError("pose angles must be numbers, not booleans or strings")
    result = {key: float(pose.get(key, 0)) for key in ("yaw", "pitch", "roll")}
    if not np.isfinite(list(result.values())).all() or any(abs(x) > 90 for x in result.values()):
        raise ValueError("angles must be finite and within [-90,90] degrees")
    return result


def evaluate_surface(fit, pose):
    verify_fit(fit)
    pose = pose_dict(pose)
    rest = np.asarray(fit["mesh"]["rest_xy"], dtype=float)
    uv = np.asarray(fit["mesh"]["uv"], dtype=float)
    xyz = np.column_stack([rest, fit["depth"]])
    posed_xyz = rotate_points(xyz, pose, fit["pivot"], fit["neutral_pose"])
    base = posed_xyz[:, :2]
    final = apply_local_corrections(base, uv, pose, fit["template"].get("correction_rules", []),
                                    fit["parameters"], fit["neutral_pose"], scale=fit["depth_scale"])
    if not np.isfinite(final).all():
        raise ValueError("non-finite evaluated coordinates")
    delta = np.asarray(final) - rest
    posed_xyz[:, :2] = final
    tri = np.asarray(fit["mesh"]["triangles"], dtype=int)
    def areas(points):
        a, b = points[tri[:, 1]]-points[tri[:, 0]], points[tri[:, 2]]-points[tri[:, 0]]
        return a[:, 0]*b[:, 1]-a[:, 1]*b[:, 0]
    a0, a1 = areas(rest), areas(np.asarray(final))
    return {"schema_version": "rig-pose/1", "fit_sha256": fit["content_sha256"],
            "pose": pose, "xy": np.asarray(final).tolist(), "xyz":posed_xyz.tolist(),"displacements": delta.tolist(),
            "validation": {"finite": True, "max_displacement": float(np.linalg.norm(delta, axis=1).max()),
                           "projected_reversed_triangles": int(np.count_nonzero(a0*a1 < 0)),
                           "projected_collapsed_triangles": int(np.count_nonzero(abs(a1) < 1e-9)),
                           "projection_quality_reviewed": False,
                           "contact_solved": False}, "live_model_modified": False}


def sample_pose_suite(fit, extent=25):
    if not 0 < extent <= 60:
        raise ValueError("pose suite extent must be (0,60]")
    neutral = fit["neutral_pose"]
    poses = [neutral]
    for yaw, pitch in ((-extent,0),(extent,0),(0,-extent),(0,extent),
                       (-extent,-extent),(-extent,extent),(extent,-extent),(extent,extent)):
        poses.append({"yaw": neutral["yaw"]+yaw, "pitch": neutral["pitch"]+pitch,
                      "roll": neutral["roll"]})
    return [evaluate_surface(fit, pose) for pose in poses]
