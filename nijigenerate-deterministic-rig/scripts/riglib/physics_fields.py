"""Rest-material secondary displacement fields; no model I/O or simulation.

Coordinates are model XY, Y down. Frames are O=fixed, N=root-to-free,
T=(N.y,-N.x). A field is sampled on the existing NJC mesh, never remeshed.
The engine owns SpringPendulum integration; this module authors its travel.
"""
import numpy as np
from scipy.spatial import cKDTree


def smooth(value):
    s = np.clip(value, 0, 1)
    return s*s*(3-2*s)


def segment_distance(points, a, b):
    p = np.asarray(points, float); a = np.asarray(a, float); v = np.asarray(b, float)-a
    t = np.clip((p-a)@v/max(float(v@v), 1e-12), 0, 1)
    return np.linalg.norm(p-(a+t[:, None]*v), axis=1)


def frame(fixed, free):
    o = np.asarray(fixed, float); v = np.asarray(free, float)-o
    length = float(np.linalg.norm(v))
    if not np.isfinite(length) or length <= 1e-6:
        raise ValueError('Degenerate physics support-to-free frame')
    n = v/length; t = np.array([n[1], -n[0]])
    return o, t, n, length


def field_weight(spec, points, policy):
    p = np.asarray(points, float); o, t, n, length = frame(spec['fixed'], spec['free'])
    s = (p-o)@n/length; band = policy['anchor_band_fraction']
    w = smooth((s-band)/(1-band))
    if spec['pattern'] == 'two_ends':
        w = 16*smooth((s-band)/(1-2*band))**2*(1-smooth((s-band)/(1-2*band)))**2
    if spec.get('limb'):
        limb = spec['limb']; joints = limb['joints']; radius = limb['radius']
        distance = np.minimum.reduce([segment_distance(p, a, b) for a, b in zip(joints[:-1], joints[1:])])
        # Anatomical tube remains fixed even inside a combined arm/sleeve Part.
        w *= smooth((distance-radius)/(radius*0.75))
        for joint in joints:
            w *= smooth((np.linalg.norm(p-joint, axis=1)-radius)/(radius*0.75))
    if spec.get('protected_pixels'):
        distance = cKDTree(spec['protected_pixels']).query(p)[0]
        w *= smooth((distance-spec['protection_margin'])/spec['protection_margin'])
    if spec.get('boundary_pixels'):
        distance = cKDTree(spec['boundary_pixels']).query(p)[0]
        w *= smooth(distance/spec['boundary_margin'])
    return np.clip(w, 0, 1)


def displacement(spec, points, key, policy):
    _, t, n, length = frame(spec['fixed'], spec['free'])
    amplitude = np.asarray(policy['profiles'][spec['profile']]['amplitude_ratio'])*length
    # X positive = local transverse T, Y positive = toward the fixed end (-N).
    vector = amplitude[0]*key[0]*t-amplitude[1]*key[1]*n
    return field_weight(spec, points, policy)[:, None]*vector


def protect_triangles(delta, vertices, indices, spec, policy):
    """Protect complete faces touching a fixed sampled vertex, not only its node.

This avoids interpolating a moving neighbour over a protected joint/skin area.
Fine semantic boundaries still require a sufficiently resolved existing mesh.
"""
    result = np.asarray(delta, float).copy()
    w = field_weight(spec, vertices, policy)
    faces = np.asarray(indices, int).reshape(-1, 3)
    fixed_faces = faces[np.any(w[faces] <= 1e-12, axis=1)]
    if len(fixed_faces):
        result[np.unique(fixed_faces)] = 0
    return result


def no_inversion(vertices, indices, values):
    v = np.asarray(vertices, float); d = np.asarray(values, float)
    tri = np.asarray(indices, int).reshape(-1, 3)
    def areas(p):
        q = p[tri]; a = q[:, 1]-q[:, 0]; b = q[:, 2]-q[:, 0]
        return a[:, 0]*b[:, 1]-a[:, 1]*b[:, 0]
    before = areas(v); after = areas(v+d); valid = abs(before)>1e-8
    return bool(np.all(before[valid]*after[valid]>0))
