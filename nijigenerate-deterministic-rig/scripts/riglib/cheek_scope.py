"""Pose-derived authority for the near jaw-to-temple correction.

This module selects support only. It does not invent a target silhouette or
turn a projection foldback into a cheek correction.
"""
import numpy as np


def pose_frame(projection, face_basis):
    """Recover the viewing-depth row from NJC's actual orthographic projection.

    NJC projects model XYZ to XY; the proper rotation's third row is the
    cross product of its first two. Positive anatomical front depth is near.
    Use the calibrated anatomical across axis, never a layer suffix or the
    parameter's presumed sign. Float noise at a frontal pose is not a side.
    """
    xy = np.asarray(projection, float)[:3].T
    if xy.shape != (2, 3) or not np.isfinite(xy).all():
        raise ValueError('Missing native XYZ projection for cheek side selection')
    depth = np.cross(xy[0], xy[1])
    length = np.linalg.norm(depth)
    if length <= 1e-12:
        raise ValueError('Degenerate native projection has no viewing-depth axis')
    depth /= length
    across = np.r_[np.asarray(face_basis, float)[:, 0], 0.]
    near_slope = float(depth @ across)
    side = 0 if abs(near_slope) <= 1e-6 else (1 if near_slope > 0 else -1)
    return {'near_side': side, 'near_depth_slope': near_slope,
            'view_depth_axis': depth.tolist(),
            'authority': 'cross product of NJC projection rows in PSD eye-line frame'}


def coordinates(world, profile):
    points = (np.asarray(world)-profile['origin']) @ np.asarray(profile['basis'])
    y = points[:, 1]
    left = np.interp(y, profile['y'], profile['left'])
    right = np.interp(y, profile['y'], profile['right'])
    # The observed feature midline remains the dividing line even for an
    # asymmetric outline. A contour midpoint is not the anatomical midline.
    mid = np.interp(y, [profile['eye_y'], profile['mouth_y'], profile['y'][-1]],
                    [sum(profile['eye_span'])/2, sum(profile['mouth_span'])/2,
                     (profile['left'][-1]+profile['right'][-1])/2])
    return points, left, right, mid


def support(world, indices, profile, frame):
    """Freeze the entire far-side half-plane, including triangle interiors.

    Zeroing far-side vertices alone leaks deformation across triangles that
    straddle the midline. Pin all vertices of those native triangles too.
    Do not retessellate AutoMesh to work around this restriction.
    """
    points, _, _, mid = coordinates(world, profile)
    side = frame['near_side']
    near = side*(points[:, 0]-mid) > 0 if side else np.zeros(len(points), bool)
    triangles = np.asarray(indices, int).reshape(-1, 3)
    allowed = near.copy()
    outside = ~near[triangles].all(axis=1)
    # Test the exact breaks of the piecewise-linear feature midline as well
    # as triangle vertices; a bent midline may cross a triangle's interior.
    for level in (profile['eye_y'], profile['mouth_y'], profile['y'][-1]):
        center = np.interp(level, [profile['eye_y'], profile['mouth_y'], profile['y'][-1]],
                           [sum(profile['eye_span'])/2, sum(profile['mouth_span'])/2,
                            (profile['left'][-1]+profile['right'][-1])/2])
        for a, b in ((0, 1), (1, 2), (2, 0)):
            p, q = points[triangles[:, a]], points[triangles[:, b]]
            dy = q[:, 1]-p[:, 1]
            intersects = (np.minimum(p[:, 1], q[:, 1]) <= level) & (np.maximum(p[:, 1], q[:, 1]) >= level)
            t = np.divide(level-p[:, 1], dy, out=np.zeros_like(dy), where=abs(dy) > 1e-12)
            x = p[:, 0]+t*(q[:, 0]-p[:, 0])
            outside |= intersects & (side*(x-center) <= 0)
    in_band = (points[:, 1] >= profile['temple_y']) & (points[:, 1] <= profile['y'][-1])
    outside |= ~in_band[triangles].all(axis=1)
    allowed[triangles[outside].ravel()] = False
    allowed &= in_band
    return allowed


def assert_scope(delta, allowed):
    if np.any(np.asarray(delta)[~allowed]):
        raise ValueError('Cheek correction wrote outside its near-side native-mesh support')
