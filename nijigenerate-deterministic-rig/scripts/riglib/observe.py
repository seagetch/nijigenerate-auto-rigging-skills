"""Image observations are measurements, not inferred anatomy or true depth."""
from __future__ import annotations
from pathlib import Path
import numpy as np
from PIL import Image
from .data import digest


def observe_image(path, threshold=16, row_count=33):
    if not 1 <= threshold <= 255 or row_count < 2:
        raise ValueError("threshold must be 1..255 and row_count >= 2")
    with Image.open(path) as image:
        rgba = np.asarray(image.convert("RGBA"))
    mask = rgba[:, :, 3] >= threshold
    ys, xs = np.nonzero(mask)
    if not len(xs):
        raise ValueError("source has no alpha support at selected threshold")
    # Pixel centers, not corners; bounds are inclusive observed centers.
    bounds = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
    if bounds[0] == bounds[2] or bounds[1] == bounds[3]:
        raise ValueError("source must have nonzero width and height")
    rows = []
    for y in np.unique(np.rint(np.linspace(bounds[1], bounds[3], row_count)).astype(int)):
        xx = np.flatnonzero(mask[y])
        runs = []
        if len(xx):
            cuts = np.flatnonzero(np.diff(xx) > 1) + 1
            for run in np.split(xx, cuts):
                runs.append([int(run[0]), int(run[-1])])
        rows.append({"y": int(y), "intervals": runs})
    return {
        "schema_version": "rig-observation/1",
        "source": {"path": str(Path(path).resolve()), "sha256": digest(path),
                   "width": rgba.shape[1], "height": rgba.shape[0]},
        "frame": {"x": "image-right", "y": "image-down", "units": "source-pixel"},
        "alpha_threshold": threshold, "bounds": bounds,
        "alpha_pixel_count": int(mask.sum()),
        "alpha_centroid": [float(xs.mean()), float(ys.mean())],
        "full_rectangle": bool(mask.all()), "rows": rows,
        "depth_observed": False, "anatomical_landmarks_observed": False,
    }


def resolve_landmarks(template, observation, hints):
    supplied = hints.get("landmarks", {})
    if not isinstance(supplied, dict):
        raise ValueError("hints.landmarks must map role IDs to [x,y]")
    roles = {entry["id"]: entry for entry in template["landmarks"]}
    if set(supplied) - set(roles):
        raise ValueError(f"unknown landmark roles: {sorted(set(supplied)-set(roles))}")
    found, missing = [], []
    bounds = observation["bounds"]
    x0, y0, x1, y1 = bounds
    # Only geometric extrema are automatic. A bbox center is never labeled a nose.
    extractors = {
        "bbox_center": [(x0+x1)/2, (y0+y1)/2],
        "bbox_top_center": [(x0+x1)/2, y0],
        "bbox_bottom_center": [(x0+x1)/2, y1],
        "bbox_left_center": [x0, (y0+y1)/2],
        "bbox_right_center": [x1, (y0+y1)/2],
        "alpha_centroid": observation["alpha_centroid"],
    }
    for role, definition in roles.items():
        value = supplied.get(role)
        origin = "provided"
        if value is None and definition.get("automatic_geometric_anchor"):
            extractor = definition["automatic_geometric_anchor"]
            if extractor not in extractors:
                raise ValueError(f"unsupported automatic extractor {extractor}")
            value = extractors[extractor]
            origin = f"measured:{extractor}"
        if value is None:
            if definition.get("required", False):
                missing.append(role)
            continue
        xy = np.asarray(value, dtype=float)
        if xy.shape != (2,) or not np.isfinite(xy).all():
            raise ValueError(f"invalid landmark {role}")
        found.append({"id": role, "uv": definition["uv"], "xy": xy.tolist(), "origin": origin})
    return found, missing
