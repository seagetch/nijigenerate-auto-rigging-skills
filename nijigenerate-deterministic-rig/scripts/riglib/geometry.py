"""Deterministic, model-independent semantic-grid geometry.

Coordinates: material UV is [0, 1]^2; neutral XY uses source-image units.
Depth operators return normalized source-width units. Rotation angles are
degrees, right handed, with R = Rz(roll) @ Ry(yaw) @ Rx(pitch).
This module evaluates front charts; it is not a 3-D contact/cloth simulator.
It has no application, filesystem, model UUID, or part-name dependencies.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np


class GeometryError(ValueError):
    """Invalid or unrepresentable geometry; never silently repair a fold."""


def _array(value: Any, name: str) -> np.ndarray:
    try:
        result = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise GeometryError(f"{name} must be numeric") from exc
    if not np.all(np.isfinite(result)):
        raise GeometryError(f"{name} contains non-finite values")
    return result


def _points(value: Any, dimensions: int, name: str) -> np.ndarray:
    result = _array(value, name)
    if result.ndim != 2 or result.shape[1] != dimensions:
        raise GeometryError(f"{name} must have shape (N, {dimensions})")
    return result


def _uv(value: Any) -> np.ndarray:
    result = _points(value, 2, "uv")
    if np.any(result < 0.0) or np.any(result > 1.0):
        raise GeometryError("uv must lie in [0, 1]")
    return result


def _lines(value: Any, name: str) -> np.ndarray:
    result = _array(value, name)
    if result.ndim != 1 or len(result) < 2:
        raise GeometryError(f"{name} requires at least two coordinates")
    if np.any(np.diff(result) <= 0):
        raise GeometryError(f"{name} must be strictly increasing")
    if result[0] != 0.0 or result[-1] != 1.0:
        raise GeometryError(f"{name} must span exactly 0 to 1")
    return result


def _scalar(value: Any, parameters: Mapping[str, Any], name: str) -> float:
    if isinstance(value, str):
        if value not in parameters:
            raise GeometryError(f"unknown parameter {value!r} for {name}")
        value = parameters[value]
    if isinstance(value, (bool, Mapping)):
        raise GeometryError(f"{name} must be a number or parameter key")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise GeometryError(f"{name} must be a number or parameter key") from exc
    if not math.isfinite(result):
        raise GeometryError(f"{name} must be finite")
    return result


def _value(op: Mapping[str, Any], key: str, parameters: Mapping[str, Any],
           default: Any = None) -> float:
    if key not in op and default is None:
        raise GeometryError(f"missing {key} for {op.get('type', 'operator')}")
    return _scalar(op.get(key, default), parameters, key)


def _pair(value: Any, parameters: Mapping[str, Any], name: str) -> np.ndarray:
    if not isinstance(value, (list, tuple, np.ndarray)) or len(value) != 2:
        raise GeometryError(f"{name} must contain two values")
    return np.array([_scalar(x, parameters, name) for x in value])


def _known_keys(record: Mapping[str, Any], allowed: set[str], name: str) -> None:
    unknown = set(record) - allowed - {"id", "label", "description"}
    if unknown:
        raise GeometryError(f"unknown {name} fields: {sorted(unknown)}")


def make_uv_grid(u_lines: Sequence[float], v_lines: Sequence[float]) -> np.ndarray:
    """Return (rows, columns, 2), v-major, with no hidden resampling."""
    u, v = _lines(u_lines, "u_lines"), _lines(v_lines, "v_lines")
    uu, vv = np.meshgrid(u, v)
    return np.stack((uu, vv), axis=-1)


def _cross(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def validate_grid(xy: Any, min_area_ratio: float = 1e-8) -> dict[str, Any]:
    """Check the bilinear Jacobian at all four corners of every cell.

    A bilinear cell's determinant is affine on the cell, so strictly positive
    corner determinants rule out a local sign change anywhere in that cell.
    This does not establish that distant cells never overlap globally.
    """
    grid = _array(xy, "grid")
    if grid.ndim != 3 or grid.shape[2] != 2 or min(grid.shape[:2]) < 2:
        raise GeometryError("grid must have shape (rows>=2, columns>=2, 2)")
    ratio = _scalar(min_area_ratio, {}, "min_area_ratio")
    if ratio < 0:
        raise GeometryError("min_area_ratio cannot be negative")
    p00, p10 = grid[:-1, :-1], grid[:-1, 1:]
    p01, p11 = grid[1:, :-1], grid[1:, 1:]
    jacobians = np.stack((
        _cross(p10-p00, p01-p00),
        _cross(p10-p00, p11-p10),
        _cross(p11-p01, p01-p00),
        _cross(p11-p01, p11-p10),
    ), axis=-1)
    extent = np.ptp(grid.reshape(-1, 2), axis=0)
    cells = (grid.shape[0]-1) * (grid.shape[1]-1)
    area_scale = float(extent[0] * extent[1] / cells)
    threshold = max(np.finfo(float).tiny, area_scale * ratio)
    bad = np.argwhere(jacobians <= threshold)
    if len(bad):
        row, col, corner = map(int, bad[0])
        raise GeometryError(
            f"folded/degenerate grid at cell ({row},{col}), corner {corner}: "
            f"Jacobian {jacobians[row,col,corner]:.9g} <= {threshold:.9g}"
        )
    return {
        "cells": cells,
        "min_jacobian": float(jacobians.min()),
        "reference_cell_area": area_scale,
        "min_area_ratio": float(jacobians.min() / area_scale),
        "local_orientation_preserved": True,
        "global_injectivity_tested": False,
    }


def _landmark_arrays(landmarks: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    rows: dict[tuple[float, float], tuple[float, float]] = {}
    for index, landmark in enumerate(landmarks):
        if not isinstance(landmark, Mapping) or "uv" not in landmark or "xy" not in landmark:
            raise GeometryError(f"landmark {index} needs uv and xy")
        source = _pair(landmark["uv"], {}, "landmark uv")
        target = _pair(landmark["xy"], {}, "landmark xy")
        if np.any(source < 0) or np.any(source > 1):
            raise GeometryError("landmark uv must lie in [0, 1]")
        key, point = tuple(source.tolist()), tuple(target.tolist())
        if key in rows and rows[key] != point:
            raise GeometryError(f"conflicting landmark targets at {key}")
        rows[key] = point
    keys = sorted(rows)  # Input dictionary/list ordering cannot change the fit.
    if not keys:
        return np.empty((0, 2)), np.empty((0, 2))
    return np.asarray(keys), np.asarray([rows[key] for key in keys])


def _tps_kernel(r_squared: np.ndarray) -> np.ndarray:
    result = np.zeros_like(r_squared)
    mask = r_squared > 0
    result[mask] = 0.5 * r_squared[mask] * np.log(r_squared[mask])
    return result


def _fit_points(query: np.ndarray, source: np.ndarray, target: np.ndarray,
                bounds: np.ndarray, method: str) -> np.ndarray:
    base = bounds[:2] + query * (bounds[2:] - bounds[:2])
    if len(source) == 0:
        return base
    source_base = bounds[:2] + source * (bounds[2:] - bounds[:2])
    displacement = target - source_base
    affine = np.column_stack((np.ones(len(source)), source))
    if method == "tps" and len(source) >= 3 and np.linalg.matrix_rank(affine) == 3:
        d2 = np.sum((source[:, None] - source[None, :]) ** 2, axis=2)
        system = np.block([
            [_tps_kernel(d2), affine],
            [affine.T, np.zeros((3, 3))],
        ])
        rhs = np.vstack((displacement, np.zeros((3, 2))))
        try:
            solution = np.linalg.solve(system, rhs)
        except np.linalg.LinAlgError as exc:
            raise GeometryError("singular thin-plate landmark system") from exc
        q2 = np.sum((query[:, None] - source[None, :]) ** 2, axis=2)
        result = base + _tps_kernel(q2) @ solution[:len(source)]
        result += np.column_stack((np.ones(len(query)), query)) @ solution[len(source):]
    else:
        # A one/two-point or collinear request cannot determine a 2-D TPS affine
        # tail. IDW interpolates displacement over the explicit neutral bounds.
        d2 = np.sum((query[:, None] - source[None, :]) ** 2, axis=2)
        result = np.empty_like(base)
        hits = d2 == 0
        exact = np.any(hits, axis=1)
        if np.any(exact):
            result[exact] = target[np.argmax(hits[exact], axis=1)]
        if np.any(~exact):
            local = d2[~exact]
            weights = np.min(local, axis=1, keepdims=True) / local
            weights /= np.sum(weights, axis=1, keepdims=True)
            result[~exact] = base[~exact] + weights @ displacement
    if not np.all(np.isfinite(result)):
        raise GeometryError("non-finite landmark fit")
    return result


def fit_guide_grid(u_lines: Sequence[float], v_lines: Sequence[float],
                   bounds: Sequence[float],
                   landmarks: Sequence[Mapping[str, Any]],
                   method: str = "tps", *, min_area_ratio: float = 1e-8) -> np.ndarray:
    """Fit a semantic grid to neutral XY landmarks, then reject local folds.

    TPS interpolates landmark displacements with an affine tail. Underconstrained
    (<3 noncollinear points) TPS uses deterministic IDW displacement. Landmarks
    between grid nodes are exact in the fitted field, not necessarily in its
    later bilinear approximation: callers must report the resampling residual.
    """
    if method not in {"tps", "idw"}:
        raise GeometryError(f"unsupported fit method {method!r}")
    box = _array(bounds, "bounds")
    if box.shape != (4,) or np.any(box[2:] <= box[:2]):
        raise GeometryError("bounds must be [xmin,ymin,xmax,ymax] with positive extent")
    material = make_uv_grid(u_lines, v_lines)
    source, target = _landmark_arrays(landmarks)
    result = _fit_points(material.reshape(-1, 2), source, target, box, method)
    result = result.reshape(material.shape)
    validate_grid(result, min_area_ratio)
    return result


def sample_grid(values: Any, u_lines: Sequence[float], v_lines: Sequence[float],
                uv: Any) -> np.ndarray:
    """Bilinear resampling on an explicitly nonuniform semantic grid."""
    u, v = _lines(u_lines, "u_lines"), _lines(v_lines, "v_lines")
    query, data = _uv(uv), _array(values, "grid values")
    if data.ndim not in {2, 3} or data.shape[:2] != (len(v), len(u)):
        raise GeometryError("grid values shape does not match guide coordinates")
    col = np.minimum(np.searchsorted(u, query[:, 0], side="right") - 1, len(u)-2)
    row = np.minimum(np.searchsorted(v, query[:, 1], side="right") - 1, len(v)-2)
    s = (query[:, 0]-u[col]) / (u[col+1]-u[col])
    t = (query[:, 1]-v[row]) / (v[row+1]-v[row])
    if data.ndim == 3:
        s, t = s[:, None], t[:, None]
    return ((1-s)*(1-t)*data[row, col] + s*(1-t)*data[row, col+1]
            + (1-s)*t*data[row+1, col] + s*t*data[row+1, col+1])


def inverse_grid(xy: Any, u_lines: Sequence[float], v_lines: Sequence[float],
                 points: Any, *, tolerance: float = 1e-9,
                 max_iterations: int = 30) -> np.ndarray:
    """Invert valid bilinear cells by deterministic, bounded Newton iteration.

    Outside points and ambiguous overlapping-cell solutions are rejected.
    This is registration, not nearest-boundary clipping.
    """
    grid, query = _array(xy, "xy"), _points(points, 2, "points")
    u, v = _lines(u_lines, "u_lines"), _lines(v_lines, "v_lines")
    if grid.shape != (len(v), len(u), 2):
        raise GeometryError("xy shape does not match guide coordinates")
    validate_grid(grid)
    tol = _scalar(tolerance, {}, "tolerance")
    if tol <= 0 or not isinstance(max_iterations, int) or max_iterations < 1:
        raise GeometryError("positive tolerance and iteration count required")
    scale = max(1.0, float(np.max(np.ptp(grid.reshape(-1, 2), axis=0))))
    eps = tol * scale
    output = []
    for point in query:
        solutions = []
        for row in range(len(v)-1):
            for col in range(len(u)-1):
                p00, p10 = grid[row, col], grid[row, col+1]
                p01, p11 = grid[row+1, col], grid[row+1, col+1]
                corners = np.stack((p00, p10, p01, p11))
                if np.any(point < corners.min(axis=0)-eps) or np.any(point > corners.max(axis=0)+eps):
                    continue
                a, b, c = p10-p00, p01-p00, p11-p10-p01+p00
                local = np.array([0.5, 0.5])
                for _ in range(max_iterations):
                    s, t = local
                    error = p00 + a*s + b*t + c*s*t - point
                    if np.linalg.norm(error, ord=np.inf) <= eps:
                        break
                    jacobian = np.column_stack((a+c*t, b+c*s))
                    try:
                        local -= np.linalg.solve(jacobian, error)
                    except np.linalg.LinAlgError:
                        break
                    if not np.all(np.isfinite(local)) or np.max(np.abs(local)) > 1e6:
                        break
                s, t = local
                error = p00 + a*s + b*t + c*s*t - point
                if (np.all(np.isfinite(local)) and np.linalg.norm(error, ord=np.inf) <= eps
                        and np.all(local >= -tol) and np.all(local <= 1+tol)):
                    local = np.clip(local, 0, 1)
                    solutions.append(np.array([
                        u[col] + local[0]*(u[col+1]-u[col]),
                        v[row] + local[1]*(v[row+1]-v[row]),
                    ]))
        if not solutions:
            raise GeometryError(f"point {point.tolist()} lies outside fitted grid or inverse did not converge")
        if any(np.max(np.abs(solutions[0]-other)) > 10*tol for other in solutions[1:]):
            raise GeometryError("ambiguous inverse: nonadjacent grid cells overlap")
        output.append(solutions[0])
    return np.asarray(output, dtype=float).reshape(-1, 2)


def _profile(coordinate: np.ndarray, specification: Any,
             parameters: Mapping[str, Any], default: float) -> np.ndarray:
    if specification is None:
        return np.full(len(coordinate), default)
    if not isinstance(specification, (list, tuple)) or len(specification) < 1:
        raise GeometryError("profile requires [coordinate,value] pairs")
    parsed = np.array([_pair(point, parameters, "profile point") for point in specification])
    if np.any(parsed[:, 0] < 0) or np.any(parsed[:, 0] > 1) or np.any(np.diff(parsed[:, 0]) <= 0):
        raise GeometryError("profile coordinates must increase strictly within [0,1]")
    return np.interp(coordinate, parsed[:, 0], parsed[:, 1])


def _compact(uv: np.ndarray, op: Mapping[str, Any],
             parameters: Mapping[str, Any]) -> np.ndarray:
    center = _pair(op.get("center", [0.5, 0.5]), parameters, "center")
    radius = _pair(op.get("radius", [0.5, 0.5]), parameters, "radius")
    if np.any(radius <= 0):
        raise GeometryError("compact support radii must be positive")
    angle = math.radians(_value(op, "rotation_degrees", parameters, 0.0))
    c, s = math.cos(angle), math.sin(angle)
    local = (uv-center) @ np.array([[c, -s], [s, c]])
    distance = np.linalg.norm(local/radius, axis=1)
    remaining = np.maximum(0.0, 1.0-distance)
    return remaining**4 * (4.0*distance+1.0)


def _section(uv: np.ndarray, op: Mapping[str, Any],
             parameters: Mapping[str, Any], swept: bool = False) -> np.ndarray:
    coordinate = uv[:, 1]
    depth = _value(op, "depth", parameters, 1.0)
    profile = _profile(coordinate, op.get("depth_profile"), parameters, 1.0)
    base = _value(op, "base", parameters, 0.0)
    center = _profile(coordinate, op.get("center_u_profile") if swept else None,
                      parameters, _value(op, "center_u", parameters, 0.5))
    radius = _profile(coordinate, op.get("radius_u_profile") if swept else None,
                      parameters, _value(op, "radius_u", parameters, 0.5))
    if np.any(radius <= 0):
        raise GeometryError("section radius must be positive")
    cross = op.get("cross_section", "ellipse")
    if cross == "ellipse":
        exponent = _value(op, "exponent", parameters, 0.5)
        if exponent <= 0:
            raise GeometryError("section exponent must be positive")
        factor = np.maximum(0.0, 1.0-((uv[:, 0]-center)/radius)**2)**exponent
    elif cross == "angular":
        theta = _pair(op.get("theta_degrees", [-90, 90]), parameters, "theta_degrees")
        if theta[0] == theta[1]:
            raise GeometryError("angular section must span a nonzero interval")
        factor = np.cos(np.deg2rad(theta[0]+uv[:, 0]*(theta[1]-theta[0])))
    elif cross == "flat":
        factor = np.ones(len(uv))
    else:
        raise GeometryError(f"unsupported cross_section {cross!r}")
    axis_depth = _profile(coordinate, op.get("center_depth_profile") if swept else None,
                          parameters, 0.0)
    return base + axis_depth + depth*profile*factor


def _ribbons(uv: np.ndarray, op: Mapping[str, Any],
             parameters: Mapping[str, Any]) -> np.ndarray:
    ribbons = op.get("ribbons")
    if not isinstance(ribbons, list) or not ribbons:
        raise GeometryError("ribbon_network requires nonempty ribbons")
    result = np.full(len(uv), _value(op, "outside_depth", parameters, 0.0))
    assigned = np.zeros(len(uv), dtype=bool)
    for ribbon in ribbons:
        if not isinstance(ribbon, Mapping):
            raise GeometryError("ribbon must be an object")
        _known_keys(ribbon, {"support", "depth", "depth_profile", "base",
                            "center_depth_profile"}, "ribbon chart")
        box = _array(ribbon.get("support", [0, 0, 1, 1]), "ribbon support")
        if (box.shape != (4,) or np.any(box[2:] <= box[:2])
                or np.any(box < 0) or np.any(box > 1)):
            raise GeometryError("ribbon support must be an ordered UV rectangle")
        inside = np.all(uv >= box[:2], axis=1) & np.all(uv <= box[2:], axis=1)
        local = (uv[inside]-box[:2])/(box[2:]-box[:2])
        values = _section(local, {**ribbon, "cross_section": "flat"}, parameters, swept=True)
        repeated = assigned[inside]
        if np.any(np.abs(result[inside][repeated]-values[repeated]) > 1e-9):
            raise GeometryError("ribbon charts overlap with incompatible depth; use separate charts")
        result[inside] = values
        assigned[inside] = True
    return result


def evaluate_depth(uv: Any, operators: Sequence[Mapping[str, Any]],
                   parameters: Mapping[str, Any] | None = None,
                   host_depth: Any = None) -> np.ndarray:
    """Evaluate an additive declarative front-chart depth field.

    No expression evaluation occurs. Scalar strings reference numeric parameters.
    Profiles are piecewise linear with endpoint clamping. Ribbon networks here
    mean separate rectangular material charts, not a knot/contact solver.
    """
    query = _uv(uv)
    parameters = {} if parameters is None else parameters
    if not isinstance(parameters, Mapping):
        raise GeometryError("parameters must be a mapping")
    result = np.zeros(len(query))
    if not isinstance(operators, (list, tuple)):
        raise GeometryError("operators must be a list")
    for op in operators:
        if not isinstance(op, Mapping):
            raise GeometryError("operator must be an object")
        kind = op.get("type")
        section_fields = {"type", "depth", "depth_profile", "center_u", "radius_u",
                          "exponent", "base", "cross_section", "theta_degrees"}
        allowed_fields = {
            "section_surface": section_fields,
            "section": section_fields,
            "flared_shell": section_fields,
            "swept_surface": section_fields | {"center_depth_profile", "center_u_profile", "radius_u_profile"},
            "swept_tube": section_fields | {"center_depth_profile", "center_u_profile", "radius_u_profile"},
            "ribbon": section_fields | {"center_depth_profile", "center_u_profile", "radius_u_profile"},
            "compact_relief": {"type", "center", "radius", "height", "rotation_degrees"},
            "host_offset": {"type", "offset"},
            "constant": {"type", "value"},
            "bend": {"type", "amplitude", "axis", "power", "origin"},
            "wave": {"type", "amplitude", "axis", "frequency", "phase", "fade_axis", "fade_power"},
            "ribbon_network": {"type", "ribbons", "outside_depth"},
        }
        if not isinstance(kind, str) or kind not in allowed_fields:
            raise GeometryError(f"unsupported depth operator {kind!r}")
        _known_keys(op, allowed_fields[kind], "depth operator")
        if kind in {"section_surface", "section", "flared_shell"}:
            result += _section(query, op, parameters)
        elif kind in {"swept_surface", "swept_tube", "ribbon"}:
            result += _section(query, op, parameters, swept=True)
        elif kind == "compact_relief":
            result += _value(op, "height", parameters) * _compact(query, op, parameters)
        elif kind == "host_offset":
            if host_depth is None:
                raise GeometryError("host_offset needs an explicitly supplied host_depth")
            host = _array(host_depth, "host_depth")
            if host.shape != (len(query),):
                raise GeometryError("host_depth must have one value per query")
            result += host + _value(op, "offset", parameters, 0.0)
        elif kind == "constant":
            result += _value(op, "value", parameters, 0.0)
        elif kind == "bend":
            axis = op.get("axis", "v")
            if axis not in {"u", "v"}:
                raise GeometryError("bend axis must be u or v")
            power = _value(op, "power", parameters, 2.0)
            if power <= 0:
                raise GeometryError("bend power must be positive")
            d = query[:, int(axis == "v")] - _value(op, "origin", parameters, 0.0)
            result += _value(op, "amplitude", parameters) * np.sign(d)*np.abs(d)**power
        elif kind == "wave":
            axis, fade_axis = op.get("axis", "u"), op.get("fade_axis")
            if axis not in {"u", "v"} or fade_axis not in {None, "u", "v"}:
                raise GeometryError("wave axes must be u/v or null for fade_axis")
            argument = (_value(op, "frequency", parameters, 1.0)*query[:, int(axis == "v")]
                        + _value(op, "phase", parameters, 0.0))
            fade = np.ones(len(query))
            if fade_axis is not None:
                power = _value(op, "fade_power", parameters, 1.0)
                if power <= 0:
                    raise GeometryError("wave fade_power must be positive")
                fade = query[:, int(fade_axis == "v")]**power
            result += _value(op, "amplitude", parameters)*np.sin(2*np.pi*argument)*fade
        elif kind == "ribbon_network":
            result += _ribbons(query, op, parameters)
        else:
            raise GeometryError(f"unsupported depth operator {kind!r}")
    if not np.all(np.isfinite(result)):
        raise GeometryError("non-finite depth result")
    return result


def _angles(angles: Mapping[str, Any] | Sequence[float]) -> np.ndarray:
    if isinstance(angles, Mapping):
        unknown = set(angles)-{"yaw", "pitch", "roll"}
        if unknown:
            raise GeometryError(f"unsupported pose axes {sorted(unknown)}")
        return np.array([_scalar(angles.get(axis, 0), {}, axis)
                         for axis in ("yaw", "pitch", "roll")])
    result = _array(angles, "angles")
    if result.shape != (3,):
        raise GeometryError("angles must be yaw/pitch/roll degrees")
    return result


def rotation_matrix(angles: Mapping[str, Any] | Sequence[float]) -> np.ndarray:
    yaw, pitch, roll = np.deg2rad(_angles(angles))
    cy, sy, cp, sp, cr, sr = (
        math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch),
        math.cos(roll), math.sin(roll),
    )
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    rz = np.array([[cr, -sr, 0], [sr, cr, 0], [0, 0, 1]])
    return rz @ ry @ rx


def rotate_points(xyz: Any, angles: Mapping[str, Any] | Sequence[float],
                  pivot: Sequence[float] = (0, 0, 0),
                  neutral_angles: Mapping[str, Any] | Sequence[float] = (0, 0, 0)) -> np.ndarray:
    """Rotate neutral camera-space points by R(q) R(q0)^T about pivot."""
    points, origin = _points(xyz, 3, "xyz"), _array(pivot, "pivot")
    if origin.shape != (3,):
        raise GeometryError("pivot must contain three coordinates")
    current, neutral = _angles(angles), _angles(neutral_angles)
    if np.array_equal(current, neutral):
        return points.copy()  # Exact neutral preservation, including FP bits.
    relative = rotation_matrix(current) @ rotation_matrix(neutral).T
    result = (points-origin) @ relative.T + origin
    if not np.all(np.isfinite(result)):
        raise GeometryError("non-finite rotation result")
    return result


def rotate_project(xyz: Any, angles: Mapping[str, Any] | Sequence[float],
                   pivot: Sequence[float] = (0, 0, 0),
                   neutral_angles: Mapping[str, Any] | Sequence[float] = (0, 0, 0)) -> np.ndarray:
    """Orthographic projection only; XY uses the same units as input XYZ."""
    return rotate_points(xyz, angles, pivot, neutral_angles)[:, :2].copy()


def _pose_basis(pose: np.ndarray, driver: Mapping[str, Any],
                parameters: Mapping[str, Any]) -> float:
    axis = driver.get("axis", "yaw")
    if axis not in {"yaw", "pitch", "roll"}:
        raise GeometryError(f"unsupported correction axis {axis!r}")
    x = math.radians(float(pose[("yaw", "pitch", "roll").index(axis)]))
    x *= _value(driver, "scale", parameters, 1.0)
    kind = driver.get("basis", "sin")
    if kind == "linear":
        return x
    if kind == "sin":
        return math.sin(x)
    if kind == "sin2":
        return math.sin(x)**2
    if kind == "positive_sin":
        return max(0.0, math.sin(x))
    raise GeometryError(f"unsupported correction basis {kind!r}")


def apply_local_corrections(xy: Any, uv: Any, pose: Mapping[str, Any],
                            rules: Sequence[Mapping[str, Any]],
                            parameters: Mapping[str, Any] | None = None,
                            neutral_pose: Mapping[str, Any] | None = None,
                            *, scale: float = 1.0) -> np.ndarray:
    """Add compact, boundary-zero fields with exactly zero neutral amplitude.

    amplitude is normalized source-width; scale converts it to XY units.
    This creates a projected target. It does not itself solve 3-D contacts or
    prove the corrected drawing mesh is nonfolded; callers must validate it.
    """
    positions, material = _points(xy, 2, "xy"), _uv(uv)
    if len(positions) != len(material):
        raise GeometryError("xy and uv point counts differ")
    parameters = {} if parameters is None else parameters
    if not isinstance(parameters, Mapping):
        raise GeometryError("parameters must be a mapping")
    current = _angles(pose)
    neutral = _angles({} if neutral_pose is None else neutral_pose)
    unit_scale = _scalar(scale, {}, "scale")
    if unit_scale <= 0:
        raise GeometryError("scale must be positive")
    if not isinstance(rules, (list, tuple)):
        raise GeometryError("correction rules must be a list")
    result = positions.copy()
    for rule in rules:
        if not isinstance(rule, Mapping) or rule.get("type", "local") != "local":
            raise GeometryError("only local correction rules are implemented")
        _known_keys(rule, {"type", "center", "radius", "rotation_degrees", "direction",
                           "amplitude", "driver", "pin_edges"}, "correction rule")
        direction = _pair(rule.get("direction", [1, 0]), parameters, "direction")
        length = float(np.linalg.norm(direction))
        if length == 0:
            raise GeometryError("correction direction cannot be zero")
        direction /= length
        driver = rule.get("driver", {})
        if not isinstance(driver, Mapping):
            raise GeometryError("correction driver must be an object")
        _known_keys(driver, {"axis", "basis", "scale"}, "correction driver")
        amplitude = _value(rule, "amplitude", parameters)
        response = _pose_basis(current, driver, parameters)-_pose_basis(neutral, driver, parameters)
        weights = _compact(material, rule, parameters)
        edges = rule.get("pin_edges", [])
        if (not isinstance(edges, list) or not all(isinstance(edge, str) for edge in edges)
                or len(edges) != len(set(edges))):
            raise GeometryError("pin_edges must be a list of unique edge names")
        for edge in edges:
            if edge not in {"u0", "u1", "v0", "v1"}:
                raise GeometryError(f"unknown pinned edge {edge!r}")
            coordinate = material[:, int(edge[0] == "v")]
            weights *= (coordinate if edge[1] == "0" else 1-coordinate)**2
        result += (weights * amplitude * unit_scale * response)[:, None] * direction
    if not np.all(np.isfinite(result)):
        raise GeometryError("non-finite correction result")
    return result


# Descriptive aliases for small consumers; both use the documented contracts.
generate_depth = evaluate_depth
rotation_points = rotate_points
invert_grid = inverse_grid
