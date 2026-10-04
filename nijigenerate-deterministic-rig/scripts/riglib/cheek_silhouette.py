"""Near-side silhouette targets and native-mesh constrained fitting."""
from pathlib import Path
import numpy as np
from PIL import Image
from .data import read_json, digest
from .reference_fields import sample
from .reference_materials import mesh_weights
from .carrier import to_local, rotation
from .contour_constraints import contour_matrix, fit_contour
from .cheek_scope import coordinates, support

PRIOR = Path(__file__).resolve().parents[2] / 'structures' / 'face-silhouette.json'


def prepare(node, material, profile, eyes, materials, anchors):
    with Image.open(material['file']) as image:
        alpha = np.asarray(image.convert('RGBA'))[:, :, 3] > 32
    pixels = []
    for y in np.flatnonzero(alpha.any(axis=1)):
        xs = np.flatnonzero(alpha[y])
        pixels.extend(((xs[0], y), (xs[-1], y)))
    uv = (np.asarray(pixels)+.5) / [alpha.shape[1], alpha.shape[0]]
    mesh = node['mesh']; rest = np.asarray(mesh['vertices'])
    ids, weights, distance = mesh_weights(np.asarray(mesh['uvs']).reshape(-1, 2), mesh['indices'], uv)
    if np.max(distance) > 1e-6:
        raise ValueError('Skin contour lies outside its native AutoMesh UV domain')
    c = contour_matrix(ids, weights, len(rest))
    matrix = np.asarray(node['nominal_world_matrix']); linear = matrix[:2, :2]
    world = rest @ linear.T + matrix[:2, 3]
    contour = c @ world
    source, _, _, _ = coordinates(contour, profile)
    chin_row = np.argmax(source[:, 1])
    chin = contour[chin_row:chin_row+2].mean(axis=0)
    centers = []
    for eye in eyes:
        # Iris alpha is the homologous landmark used by the generated-image
        # measurements. Eye-corner midpoints are not substituted for it.
        choices = [materials[u] for u in eye['part_groups']['iris']]
        best = max(choices, key=lambda m: np.prod(m['size']))
        with Image.open(best['file']) as image:
            a = np.asarray(image.convert('RGBA'))[:, :, 3].astype(float)
        y, x = np.indices(a.shape); mass = a.sum()
        point = np.array([(x*a).sum()/mass, (y*a).sum()/mass]) + .5 + best['source_bbox'][:2]
        transform = np.asarray(best['source_to_model'])
        centers.append(point @ transform[:2, :2].T + transform[:2, 2])
    centers.sort(key=lambda p: float((p-profile['origin']) @ np.asarray(profile['basis'])[:, 0]))
    anchor_points = np.asarray([*anchors, chin])
    ids, weights, _ = mesh_weights(world, mesh['indices'], anchor_points)
    protected = contour_matrix(ids, weights, len(rest))
    return dict(rest=rest, world=world, contour=contour, C=c, protected=protected,
                chin=chin, eyes=centers, linear=linear, indices=mesh['indices'],
                contour_resolution=float(np.min(np.linalg.svd(np.asarray(material['pixel_to_model'])[:2, :2] @ np.linalg.inv(linear).T, compute_uv=False))),
                prior=read_json(PRIOR), prior_sha256=digest(PRIOR))


def solve(prepared, profile, domain, offsets, frame):
    p = prepared; side = frame['near_side']
    if not side:
        return np.zeros_like(p['rest']), {'near_side': 0, 'contour_rms': 0., 'maximum_target_residual': 0.}
    def pose(points):
        return points + sample(domain['axis_x'], domain['axis_y'], offsets,
                               to_local(points, domain['carrier_frame'])) @ rotation(domain['carrier_frame']['rotation']).T
    current = p['C'] @ pose(p['world'])
    chin, eye = pose(np.asarray([p['chin'], p['eyes'][0 if side < 0 else 1]]))
    tangent = eye-chin; length = np.linalg.norm(tangent); tangent /= length
    normal = np.array([-tangent[1], tangent[0]]) * side
    coordinates_2d = np.column_stack(((current-chin)@tangent, (current-chin)@normal))/length
    samples = [r for r in p['prior']['samples'] if np.sign(r['view_depth_axis'][0]) == side]
    samples.sort(key=lambda r: r['view_depth_axis'][1])
    view = np.asarray(frame['view_depth_axis'])
    stations = np.array([r['view_depth_axis'][1] for r in samples])
    hi = int(np.clip(np.searchsorted(stations, view[1]), 1, len(samples)-1)); lo = hi-1
    fraction = np.clip((view[1]-stations[lo])/(stations[hi]-stations[lo]), 0., 1.)
    desired = np.zeros(len(current)); end = 0.; reference_slope = 0.
    for index, weight in ((lo, 1-fraction), (hi, fraction)):
        curve = np.asarray(samples[index]['curve'])
        desired += weight*np.interp(coordinates_2d[:, 0], curve[:, 0], curve[:, 1])
        end += weight*curve[-1, 0]
        reference_slope += weight*abs(samples[index]['view_depth_axis'][0])
    # Intermediate yaw is interpolation of the reference shape in the
    # actual viewing-depth coordinate, not an independently authored turn.
    turn = np.clip(abs(view[0])/reference_slope, 0., 1.)
    source, _, _, mid = coordinates(p['contour'], profile)
    near = side*(source[:, 0]-mid) > 0
    band = (source[:, 1] >= profile['temple_y']) & (source[:, 1] <= profile['y'][-1])
    upper = np.max(coordinates_2d[near & band, 0])
    taper = np.clip((upper-coordinates_2d[:, 0])/max(upper-end, 1e-8), 0., 1.)
    taper = taper*taper*(3-2*taper)
    # Hair-covered continuation joins the measured cheek to the unchanged
    # temple; it is not labeled an observed silhouette in the reference.
    delta = ((desired-coordinates_2d[:, 1])*length*turn*taper)[:, None]*normal
    delta[~(near & band)] = 0.
    allowed = support(p['world'], p['indices'], profile, frame)
    local_target = delta @ np.linalg.inv(p['linear']).T
    selected = near & band
    protected = np.vstack([p['protected'], p['C'][~selected]])
    result, observation = fit_contour(p['rest'], p['indices'], p['C'][selected], local_target[selected], allowed, protected, p['contour_resolution'])
    observation.update(maximum_target_residual=float(np.linalg.norm(delta, axis=1).max()),
                       prior_sha256=p['prior_sha256'], reference_shape_weight=float(turn),
                       reference_samples=[samples[lo]['source_id'], samples[hi]['source_id']])
    return result, observation
