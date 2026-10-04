"""PSD cheek silhouettes on the immutable native depth-generated face field.

Only a lateral cheek residual is authored on Parts. Feature interiors and
the chin anchor remain fixed. No head rotation or Grid offset is authored.
"""
from pathlib import Path
import numpy as np
from PIL import Image
from .data import read_json, write_json, json_digest, digest
from .carrier import to_local, rotation
from .reference_fields import sample
from .shape_controls import area_ratios
from .cheek_scope import pose_frame, support, assert_scope

MECHANISM = 'psd_cheek_near_scope_v3'
PARAMETER = 'Face::Yaw-Pitch'
POLICY = {'mechanism': MECHANISM, 'alpha_threshold': 32, 'section_samples': 129,
          'scope': 'near-side chin-to-temple skin only; far side and feature interior fixed',
          'side_authority': 'NJC projection and PSD anatomical across axis',
          'contour_solver_status': 'legacy foldback solver still requires replacement',
          'authority': 'PSD alpha and feature anchors; native parent Grid readback',
          'grid_writes': False, 'depth_writes': False, 'reference_part_transfer': False}


def smoothstep(t):
    t = np.clip(t, 0., 1.)
    return t*t*(3.-2.*t)


def skin_profile(material, eyes, mouth, temple_points):
    """Measure asymmetric skin sections in the observed eye-line frame."""
    eye_points = np.concatenate([e['canthi_model'] for e in eyes])
    centers = sorted([np.mean(e['canthi_model'], axis=0) for e in eyes], key=lambda p: p[0])
    across = (centers[-1]-centers[0] if len(centers) >= 2 else
              np.asarray(eyes[0]['canthi_model'][1])-eyes[0]['canthi_model'][0])
    across = across/np.linalg.norm(across)
    if across[0] < 0: across = -across
    basis = np.column_stack((across, [-across[1], across[0]])); origin = eye_points.mean(axis=0)
    with Image.open(material['file']) as image:
        y, x = np.nonzero(np.asarray(image.convert('RGBA'))[:, :, 3] > POLICY['alpha_threshold'])
    if not len(x): raise ValueError('Face skin has no opaque PSD samples')
    source = np.c_[x, y]+np.asarray(material['source_bbox'][:2])+.5
    matrix = np.asarray(material['source_to_model'], float)
    points = (source@matrix[:2, :2].T+matrix[:2, 2]-origin)@basis
    step = float(np.min(np.linalg.svd(matrix[:2, :2], compute_uv=False)))
    bins = np.rint((points[:, 1]-points[:, 1].min())/step).astype(int); count = int(bins.max())+1
    left = np.full(count, np.inf); right = np.full(count, -np.inf)
    np.minimum.at(left, bins, points[:, 0]); np.maximum.at(right, bins, points[:, 0])
    valid = np.isfinite(left) & (right > left); stations = points[:, 1].min()+np.arange(count)*step
    ep = (eye_points-origin)@basis; mp = (np.asarray(mouth['axis_model'])-origin)@basis
    upper = (np.asarray(temple_points)-origin)@basis
    temple_y = float(upper[:, 1].min())
    if not temple_y < float(ep[:, 1].mean()):
        raise ValueError('PSD upper eye/brow support does not resolve the temple level')
    return {'origin': origin.tolist(), 'basis': basis.tolist(), 'y': stations[valid].tolist(),
            'left': left[valid].tolist(), 'right': right[valid].tolist(),
            'temple_y': temple_y,
            'temple_authority': 'top of observed PSD upper eyelid/brow alpha in the eye-line frame',
            'eye_y': float(ep[:, 1].mean()), 'mouth_y': float(mp[:, 1].mean()),
            'eye_span': [float(ep[:, 0].min()), float(ep[:, 0].max())],
            'mouth_span': [float(mp[:, 0].min()), float(mp[:, 0].max())],
            'skin_part': material['part'], 'source_alpha_sha256': material['sha256']}


def cheek_field(world, profile, domain, offsets):
    """Return an additive world-XY residual for the standard static face Grid."""
    origin = np.asarray(profile['origin']); basis = np.asarray(profile['basis'])
    points = (np.asarray(world)-origin)@basis; y = points[:, 1]
    left = np.interp(y, profile['y'], profile['left']); right = np.interp(y, profile['y'], profile['right'])
    ey, my, chin = profile['eye_y'], profile['mouth_y'], profile['y'][-1]
    if not ey < my < chin: raise ValueError('PSD eye, mouth and chin order is unresolved')
    temple = profile['temple_y']
    vertical = smoothstep((y-temple)/(ey-temple))*smoothstep((chin-y)/(chin-my))
    il = np.maximum(np.interp(y, [ey, my], [profile['eye_span'][0], profile['mouth_span'][0]]), left)
    ir = np.minimum(np.interp(y, [ey, my], [profile['eye_span'][1], profile['mouth_span'][1]]), right)
    local_rotation = rotation(domain['carrier_frame']['rotation'])
    def projected(q):
        flat = q.reshape(-1, 2); wp = flat@basis.T+origin
        delta = sample(domain['axis_x'], domain['axis_y'], offsets,
                       to_local(wp, domain['carrier_frame']))@local_rotation.T
        return (wp+delta).reshape(q.shape)
    t = np.linspace(0., 1., POLICY['section_samples'])
    sections = np.stack((left[:, None]+(right-left)[:, None]*t,
                         np.broadcast_to(y[:, None], (len(y), len(t)))), axis=-1)
    posed = projected(sections)
    middle = projected(np.stack((np.c_[il, y], np.c_[ir, y]), axis=1))
    direction = middle[:, 1]-middle[:, 0]; length = np.linalg.norm(direction, axis=1)
    usable = (length > 1e-8) & (right-left > 1e-8) & (vertical > 0)
    direction = direction/np.maximum(length[:, None], 1e-8)
    lateral = np.einsum('nki,ni->nk', posed, direction); rows = np.arange(len(y))
    dl = posed[rows, np.argmin(lateral, axis=1)]-posed[:, 0]
    dr = posed[rows, np.argmax(lateral, axis=1)]-posed[:, -1]
    wl = smoothstep((il-points[:, 0])/np.maximum(il-left, 1e-8))
    wr = smoothstep((points[:, 0]-ir)/np.maximum(right-ir, 1e-8))
    result = (wl[:, None]*dl+wr[:, None]*dr)*vertical[:, None]; result[~usable] = 0.
    return result


def anchor_vertices(rest, indices, anchors):
    """Pin native triangles carrying the face origin and feature anchors.

    A zero analytic residual at a point is insufficient on a coarse mesh:
    its containing triangle must also carry zero residual to retain children.
    """
    triangles = np.asarray(indices, int).reshape(-1, 3); pinned = np.zeros(len(rest), bool)
    for tri in triangles:
        a, b, c = rest[tri]; matrix = np.column_stack((b-a, c-a))
        if abs(np.linalg.det(matrix)) < 1e-10: continue
        q = (anchors-a)@np.linalg.inv(matrix).T
        if np.any((q[:, 0] >= -1e-7) & (q[:, 1] >= -1e-7) & (q.sum(axis=1) <= 1.+1e-7)):
            pinned[tri] = True
    return pinned


def compile_corrections(evidence, capture, nodes, program, state, bake, grid):
    domain = next(d for d in program['domains'] if d['semantic_chart'] == 'head/face')
    if grid.get('dynamic'): raise ValueError('Cheek residual requires standard static face Grid sampling')
    materials = {m['part']: m for m in capture['materials']}; face_ids = set(evidence['face_parts']['face'])
    skin = program['hierarchy']['face_origin']
    if skin not in face_ids: raise ValueError('Face origin is not registered PSD skin')
    if not evidence.get('eyes') or not evidence.get('mouth'):
        raise ValueError('Cheek correction requires internally observed eye and mouth anchors')
    from .shape_controls import source_cloud
    temple_ids = sorted({uid for eye in evidence['eyes'] for role in ('brow', 'upper')
                         for uid in eye['part_groups'].get(role, [])})
    temple_points = source_cloud(materials, temple_ids, np.asarray(evidence['source_to_model'])[:2, 2])
    profile = skin_profile(materials[skin], evidence['eyes'], evidence['mouth'], temple_points)
    profile['temple_source_parts'] = temple_ids
    binding = next(b for b in bake['bindings'] if b['target']['uuid'] == state['grids'][domain['id']]
                   and b['parameter']['name'] == PARAMETER and b['name'] == 'deform')
    from .reference_materials import mesh_weights
    poses = {tuple(row['key']): pose_frame(row['projection_matrix'], profile['basis'])
             for row in bake['head_projection_checks'] if row['parameter'] == PARAMETER}
    ops = []; observations = []; skin_fields = {}; skin_world = None; skin_indices = None
    for uid in [skin, *sorted(face_ids-{skin})]:
        node = nodes[uid]
        if node['type'] != 'Part': raise ValueError('Cheek output must target a Part')
        matrix = np.asarray(node['nominal_world_matrix']); linear = matrix[:2, :2]
        rest = np.asarray(node['mesh']['vertices']); world = rest@linear.T+matrix[:2, 3]
        pinned = np.zeros(len(rest), bool)
        if uid == skin:
            skin_world = world; skin_indices = node['mesh']['indices']
            anchors = [matrix[:2, 3], *evidence.get('facial_landmarks_model', {}).values()]
            feature_ids = {u for e in evidence.get('eyes', []) for ids in e['part_groups'].values() for u in ids}
            feature_ids.update(evidence.get('mouth', {}).get('parts', []))
            anchors.extend(np.asarray(nodes[u]['nominal_world_matrix'])[:2, 3] for u in feature_ids)
            local_anchors = (np.asarray(anchors)-matrix[:2, 3])@np.linalg.inv(linear).T
            pinned = anchor_vertices(rest, node['mesh']['indices'], local_anchors)
        else:
            sample_ids, sample_weights, _ = mesh_weights(skin_world, skin_indices, world)
        for i, x in enumerate(binding['axisValues'][0]):
            for j, y in enumerate(binding['axisValues'][1]):
                frame = poses[i, j]
                allowed = support(world, node['mesh']['indices'], profile, frame)
                if uid == skin:
                    delta = (np.zeros_like(rest) if x == 0 and y == 0 else
                             cheek_field(world, profile, domain, binding['data']['values'][i][j])@np.linalg.inv(linear).T)
                else:
                    shared = np.einsum('ni,nij->nj', sample_weights, skin_fields[i, j][sample_ids])
                    delta = shared@np.linalg.inv(linear).T
                delta = np.round(delta, 5)
                delta[~allowed] = 0.
                delta[pinned] = 0.
                assert_scope(delta, allowed)
                if uid == skin: skin_fields[i, j] = delta@linear.T
                if not np.isfinite(delta).all(): raise ValueError('Nonfinite cheek residual')
                ratio = float(area_ratios(rest, delta, node['mesh']['indices']).min())
                observations.append({'target': uid, 'key': [x, y], 'maximum_local_residual': float(abs(delta).max()),
                                     'near_side': frame['near_side'], 'near_depth_slope': frame['near_depth_slope'],
                                     'forbidden_support_maximum': 0.,
                                     'minimum_local_area_ratio': ratio})
                ops.append({'parameter': PARAMETER, 'target': uid, 'key': [x, y],
                            'mechanism': MECHANISM, 'protected_vertices': np.flatnonzero(pinned).tolist(),
                            'forbidden_vertices': np.flatnonzero(~allowed).tolist(),
                            'near_side': frame['near_side'],
                            'values': delta.ravel().tolist()})
    return {'policy': POLICY, 'profile': profile, 'operations': ops, 'observations': observations,
            'axes': binding['axisValues'], 'face_targets': sorted(face_ids),
            'program_sha256': program['content_sha256'], 'evidence_sha256': json_digest(evidence),
            'source_uv_program_sha256': state['source_uv_program_sha256'],
            'depth_angle_program_sha256': bake['content_sha256'], 'generator_sha256': digest(Path(__file__)),
            'applicable_scope': 'cheek silhouette only; other Part angle corrections remain separate work'}


def load_owned(run, state):
    if 'shape_corrections_sha256' not in state: return None
    run = Path(run); report = read_json(run/'shape-corrections-program.json'); signature = report['content_sha256']
    if (signature != state['shape_corrections_sha256'] or
            json_digest({k: v for k, v in report.items() if k != 'content_sha256'}) != signature):
        raise ValueError('Part correction identity mismatch')
    evidence = read_json(run/'evidence.json')
    if (report['evidence_sha256'] != json_digest(evidence) or report['program_sha256'] != state['program_sha256'] or
            report['source_uv_program_sha256'] != state['source_uv_program_sha256'] or
            report['depth_angle_program_sha256'] != state['depth_angle_program_sha256']):
        raise ValueError('Part correction belongs to different PSD, mesh or native depth bake')
    allowed = set(evidence['face_parts']['face'])
    if report['policy'] != POLICY or set(report['face_targets']) != allowed:
        raise ValueError('Unrecognized cheek correction authority')
    for op in report['operations']:
        if op['target'] not in allowed or op['parameter'] != PARAMETER or op['mechanism'] != MECHANISM:
            raise ValueError('Part angle correction escaped the PSD cheek scope')
        if np.any(np.asarray(op['values']).reshape(-1, 2)[op['protected_vertices']]):
            raise ValueError('Cheek correction moved a protected origin or feature triangle')
        if np.any(np.asarray(op['values']).reshape(-1, 2)[op['forbidden_vertices']]):
            raise ValueError('Cheek correction moved the far side or a triangle spanning the midline')
    return report


def capture_poses(n, run, state, label):
    from .render_camera import capture
    cases = [[x, y] for x in (-1., 0., 1.) for y in (-1., 0., 1.)]
    files = []
    for index, key in enumerate(cases):
        n.call('ViewportCommand_ResetParameters')
        n.call('ParameditCommand_SetParameterKeypoint',
               context={'parameters': [state['parameters'][PARAMETER]], 'parameterValue': key})
        path = run/f'cheek-{label}-{index:02d}.png'
        capture(n, run, path)
        files.append({'key': key, 'file': str(path), 'sha256': digest(path)})
    n.call('ViewportCommand_ResetParameters')
    return files


def comparison_sheet(run, before, after, capture, skin):
    from PIL import ImageDraw
    material = next(m for m in capture['materials'] if m['part'] == skin)
    bounds = np.asarray(material['model_bounds']); center = (bounds[:2]+bounds[2:])/2
    extent = (bounds[2:]-bounds[:2])*.9
    camera = read_json(run/'render-camera.json')['data']; transform = camera['transform']
    viewport = np.asarray(camera['viewport']); scale = np.asarray(transform['scale'])
    camera_center = np.asarray(transform['trans'][:2])
    lo = (center-extent-camera_center)/scale+viewport/2
    hi = (center+extent-camera_center)/scale+viewport/2
    crop = tuple(int(v) for v in np.r_[np.floor(lo), np.ceil(hi)])
    width, height = 420, 400
    sheet = Image.new('RGB', (width*2, height*len(before)), (32, 38, 48)); draw = ImageDraw.Draw(sheet)
    for row, pair in enumerate(zip(before, after)):
        for col, item in enumerate(pair):
            with Image.open(item['file']) as source:
                tile = source.convert('RGBA').crop(crop); tile.thumbnail((width, height-30))
                sheet.paste(tile, (col*width+(width-tile.width)//2, row*height), tile)
            draw.text((col*width+8, row*height+height-24),
                      ('before ' if col == 0 else 'after ')+str(item['key']), fill='white')
    path = run/'review-cheek-before-after.jpg'; sheet.save(path)
    return {'file': str(path), 'sha256': digest(path), 'crop_pixels': list(crop)}


def apply(run, njc):
    from .live import Live
    from .model import observe_model
    from bake_depth_angles import angle_bindings, fixed_inputs, check_bindings
    from build_native import require_single_rig
    run = Path(run); state = read_json(run/'native-state.json'); program = read_json(run/'program.json')
    if state.get('shape_corrections_sha256'): raise ValueError('Start a fresh PSD model instead of patching the cheek stage')
    n = Live(njc, run/'shape-corrections-journal')
    n.call('ToolCommand_ModelEditMode'); n.call('ViewportCommand_ResetParameters')
    require_single_rig(n, state['rig_root'], state['bones'].values())
    bake = read_json(run/'depth-angle-program.json')
    if bake['content_sha256'] != state['depth_angle_program_sha256']: raise ValueError('Native depth bake identity mismatch')
    before = angle_bindings(n); check_bindings(state, before); fixed_before = json_digest(fixed_inputs(n, state))
    nodes = {row['uuid']: row for row in observe_model(client=n, require_parameters=False)['nodes']}
    face = next(d for d in program['domains'] if d['semantic_chart'] == 'head/face')
    grid = n.read(state['grids'][face['id']])['item']['data']
    capture = read_json(run/'capture.json')
    report = compile_corrections(read_json(run/'evidence.json'), capture, nodes, program, state, bake, grid)
    targets = {op['target'] for op in report['operations'] if np.any(op['values'])}
    report['bound_targets'] = sorted(targets); report['content_sha256'] = json_digest(report)
    write_json(run/'shape-corrections-pending.json', report)
    operations = [op for op in report['operations'] if op['target'] in targets]
    for op in operations:
        n.preflight_call('ModelCommand_SetDeformBinding', bindingName='deform', values=op['values'],
                         context={'parameters': [state['parameters'][op['parameter']]], 'nodes': [op['target']], 'parameterValue': op['key']})
    before_images = capture_poses(n, run, state, 'before')
    for op in sorted(operations, key=lambda op: not np.any(op['values'])):
        n.call('ModelCommand_SetDeformBinding', bindingName='deform', values=op['values'],
               context={'parameters': [state['parameters'][op['parameter']]], 'nodes': [op['target']], 'parameterValue': op['key']})
    n.call('ViewportCommand_ResetParameters'); n.save(state['output']); after = angle_bindings(n)
    original_targets = set(state['bones'].values()) | set(state['grids'].values())
    retained = [b for b in after if b['target']['uuid'] in original_targets]
    keyed = lambda rows: {(b['target']['uuid'], b['parameter']['name'], b['name']): b for b in rows}
    if keyed(before) != keyed(retained) or fixed_before != json_digest(fixed_inputs(n, state)):
        raise ValueError('Part correction changed native Grid, depth or bone authority')
    lookup = {(b['target']['uuid'], b['parameter']['name']): b for b in after if b['name'] == 'deform'}; maximum = 0.
    for op in operations:
        b = lookup[op['target'], op['parameter']]; i, j = [axis.index(q) for axis, q in zip(b['axisValues'], op['key'])]
        error = float(np.max(abs(np.asarray(b['data']['values'][i][j]).ravel()-op['values']))); maximum = max(maximum, error)
        if not b['data']['isSet'][i][j] or error > .0003: raise ValueError('Cheek key readback differs')
    write_json(run/'shape-corrections-program.json', report)
    state['shape_corrections_sha256'] = report['content_sha256']; write_json(run/'native-state.json', state)
    (run/'shape-corrections-pending.json').unlink()
    write_json(run/'shape-corrections-readback.json', {'verified_keys': len(operations), 'maximum_saved_error': maximum,
               'native_grid_depth_bones_unchanged': True, 'program_sha256': report['content_sha256'], 'visually_reviewed': False})
    after_images = capture_poses(n, run, state, 'after')
    sheet = comparison_sheet(run, before_images, after_images, capture, report['profile']['skin_part'])
    write_json(run/'cheek-review.json', {'program_sha256': program['content_sha256'],
               'correction_sha256': report['content_sha256'], 'before': before_images, 'after': after_images,
               'sheet': sheet, 'visually_reviewed': False})
    print('Saved PSD cheek Part corrections:', len(targets), 'Parts,', len(operations), 'keys', flush=True)
