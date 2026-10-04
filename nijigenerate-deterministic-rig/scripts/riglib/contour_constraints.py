"""Fit a Part contour on its existing mesh, with exact protected constraints.

The target is supplied by the shaping stage. This solver does not invent a
silhouette, alter a mesh, or reduce the requested contour to prevent folds.
"""
import numpy as np


def nullspace(a):
    if not len(a):
        return np.eye(a.shape[1])
    _, s, vh = np.linalg.svd(a, full_matrices=True)
    tolerance = max(a.shape) * np.finfo(float).eps * (s[0] if len(s) else 0.)
    return vh[int((s > tolerance).sum()):].T


def contour_matrix(indices, weights, count):
    result = np.zeros((len(indices), count))
    np.add.at(result, (np.arange(len(indices))[:, None], indices), weights)
    return result


def fit_contour(rest, triangles, contour, target_delta, allowed, protected, contour_resolution):
    """Preserve protected points and fit the contour at source resolution.

    Far-side support is eliminated before solving. Exact barycentric point
    constraints replace freezing every vertex of a feature's triangle.
    A source-texel discretization allowance prevents subpixel overfitting;
    its smoothness weight is solved, not an authored pose amplitude.
    All coordinates/deltas use the same Part frame.
    """
    rest = np.asarray(rest, float)
    active = np.flatnonzero(allowed)
    out = np.zeros_like(rest)
    if not len(active):
        return out, {'contour_rms': float(np.sqrt(np.mean(target_delta**2))), 'active_vertices': 0}
    free = nullspace(np.asarray(protected)[:, active])
    a = np.asarray(contour)[:, active] @ free
    q = np.linalg.lstsq(a, target_delta, rcond=None)[0]
    # A normalized graph Laplacian extends boundary displacement through
    # interior support. Its scale has no effect in this null-space solve.
    graph = [set() for _ in rest]
    for tri in np.asarray(triangles, int).reshape(-1, 3):
        for i in tri:
            graph[i].update(int(j) for j in tri if j != i)
    laplacian = np.eye(len(rest))
    for i, neighbors in enumerate(graph):
        if neighbors:
            neighbors = sorted(neighbors)
            lengths = np.linalg.norm(rest[neighbors] - rest[i], axis=1)
            weights = 1. / np.maximum(lengths, np.finfo(float).eps)
            laplacian[i, neighbors] = -weights / weights.sum()
    extension = laplacian[:, active] @ free
    # Pixel contours do not constrain subpixel oscillation. Select the
    # smoothest fit within one source texel of the attainable contour fit,
    # rather than amplifying its nearly singular modes in transparent mesh
    # padding. This is a discretization allowance, not a success threshold.
    attainable = np.mean((a @ q-target_delta)**2)
    allowance = attainable + float(contour_resolution)**2
    aa = a.T @ a; ll = extension.T @ extension; rhs = a.T @ target_delta
    def regularized(weight):
        answer = np.linalg.lstsq(aa+weight*ll, rhs, rcond=None)[0]
        return answer, float(np.mean((a @ answer-target_delta)**2))
    lo, hi = 0., 1.
    for _ in range(40):
        candidate, error = regularized(hi)
        if error > allowance: break
        lo = hi; q = candidate; hi *= 2
    for _ in range(35):
        mid = (lo+hi)/2
        candidate, error = regularized(mid)
        if error <= allowance: lo = mid; q = candidate
        else: hi = mid
    out[active] = free @ q
    error = np.asarray(contour) @ out - target_delta
    return out, {'contour_rms': float(np.sqrt(np.mean(error**2))),
                 'contour_maximum_error': float(np.linalg.norm(error, axis=1).max()),
                 'protected_maximum_error': float(np.abs(np.asarray(protected) @ out).max(initial=0)),
                 'active_vertices': len(active), 'source_texel_resolution': float(contour_resolution)}
