"""Vector contour/difference plots from NJC-read mesh UVs and saved bindings.

No screenshots, image synthesis, model-file parsing, or model re-import.
The plot isolates the Part residual in the fixed parent face-Grid frame.
"""
from pathlib import Path
from html import escape
import numpy as np
from PIL import Image
from .data import write_json, digest
from .reference_materials import mesh_weights
from .reference_fields import sample
from .carrier import to_local, rotation
from .cheek_scope import coordinates


def binding_field(bindings, uid, parameter, key, size):
    b = next((b for b in bindings if b['target']['uuid'] == uid and
              b['parameter']['name'] == parameter and b['name'] == 'deform'), None)
    if b is None: return np.zeros((size, 2))
    i, j = [axis.index(value) for axis, value in zip(b['axisValues'], key)]
    return np.asarray(b['data']['values'][i][j], float).reshape(-1, 2)


def compare(run, report, node, material, domain, grid_uuid, before, after):
    import cv2
    parameter = 'Face::Yaw-Pitch'; uid = node['uuid']
    with Image.open(material['file']) as image:
        alpha = np.asarray(image.convert('RGBA'))[:, :, 3]
    contours, _ = cv2.findContours((alpha > report['policy']['alpha_threshold']).astype('uint8'),
                                   cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    contour = max(contours, key=cv2.contourArea).reshape(-1, 2)
    # Alpha texel centers and native texture UVs are in the same coordinate
    # system; interpolate within the original AutoMesh, never a new mesh.
    uv = (contour+.5)/np.array([alpha.shape[1], alpha.shape[0]])
    mesh = node['mesh']; rest = np.asarray(mesh['vertices'])
    ids, weights, distance = mesh_weights(np.asarray(mesh['uvs']).reshape(-1, 2), mesh['indices'], uv)
    if np.any(distance > 1e-6):
        raise ValueError('PSD contour is outside native UV triangles; cannot claim an exact contour comparison')
    matrix = np.asarray(node['nominal_world_matrix']); linear = matrix[:2, :2]
    world = rest@linear.T+matrix[:2, 3]
    interp = lambda field: np.einsum('ni,nij->nj', weights, field[ids])
    neutral_contour = interp(world)
    source_points, _, _, mid = coordinates(neutral_contour, report['profile'])
    band = (source_points[:, 1] >= report['profile']['temple_y']) & (source_points[:, 1] <= report['profile']['y'][-1])
    rows = []
    for x in report['axes'][0]:
        for y in report['axes'][1]:
            key = [x, y]
            g_before = binding_field(before, grid_uuid, parameter, key, len(domain['axis_x'])*len(domain['axis_y']))
            g_after = binding_field(after, grid_uuid, parameter, key, len(g_before))
            if not np.array_equal(g_before, g_after): raise ValueError('Parent face Grid changed during Part comparison')
            parent = sample(domain['axis_x'], domain['axis_y'], g_before,
                            to_local(world, domain['carrier_frame']))@rotation(domain['carrier_frame']['rotation']).T
            old = interp(world+parent+binding_field(before, uid, parameter, key, len(rest))@linear.T)
            new = interp(world+parent+binding_field(after, uid, parameter, key, len(rest))@linear.T)
            delta = new-old; length = np.linalg.norm(delta, axis=1)
            op = next(op for op in report['operations'] if op['target'] == uid and op['key'] == key)
            far = op['near_side']*(source_points[:, 0]-mid) <= 0
            rows.append({'key': key, 'near_side': op['near_side'], 'before': old.tolist(), 'after': new.tolist(),
                         'difference': delta.tolist(), 'maximum_movement': float(length.max()),
                         'far_side_maximum_movement': float(length[far].max()) if far.any() else 0.,
                         'changed_contour_samples': int((length > 1e-7).sum())})
    result = {'scope': 'existing INX face Part only, fixed parent face-Grid frame; not full-rig visual verification',
              'source': 'NJC mesh UVs and pre/post saved deform bindings; PSD alpha contour',
              'skin_part': uid, 'contour_points': len(contour), 'jaw_to_temple': band.tolist(),
              'native_grid_unchanged': True, 'keys': rows}
    write_json(run/'cheek-contour-difference.json', result)
    full = draw(run/'cheek-contours-all.svg', rows, band, 5)
    central = [row for row in rows if row['key'][1] == 0]
    main = draw(run/'cheek-contours-yaw.svg', central, band, 5)
    return {'data': str(run/'cheek-contour-difference.json'), 'all': full, 'yaw': main,
            'maximum_movement': max(r['maximum_movement'] for r in rows),
            'far_side_maximum_movement': max(r['far_side_maximum_movement'] for r in rows)}


def draw(path, rows, band, columns):
    cell_w, cell_h = 300, 390
    height = 72+int(np.ceil(len(rows)/columns))*cell_h
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{columns*cell_w}" height="{height}" viewBox="0 0 {columns*cell_w} {height}">',
             '<rect width="100%" height="100%" fill="#fff"/>',
             '<style>text{font-family:Arial,sans-serif;fill:#182335} .before{fill:none;stroke:#1976d2;stroke-width:1.8} .after{fill:none;stroke:#d83432;stroke-width:1.8}</style>',
             f'<text x="18" y="24" font-size="18">{escape(Path(path).parent.name)} | near-side jaw-to-temple Part contour</text>',
             '<text x="18" y="48" font-size="14">Blue: BEFORE   Red: AFTER   Orange fill: changed area</text>']
    for index, row in enumerate(rows):
        old, new = np.asarray(row['before']), np.asarray(row['after'])
        extent = np.concatenate([old[band], new[band]])
        lo, hi = extent.min(0), extent.max(0)
        scale = min((cell_w-32)/max(hi[0]-lo[0], 1), (cell_h-105)/max(hi[1]-lo[1], 1))
        origin = np.array([(index % columns)*cell_w+cell_w/2, 72+(index//columns)*cell_h+25])
        project = lambda p: (p-np.array([(lo[0]+hi[0])/2, lo[1]]))*scale+origin
        a, b = project(old), project(new)
        # Draw only the requested anatomical band, retaining exact ordering.
        def path_segments(points):
            commands=[]; active=False
            for point, keep in zip(points, band):
                if keep:
                    commands.append(('L' if active else 'M')+f'{point[0]:.3f},{point[1]:.3f}'); active=True
                else: active=False
            return ' '.join(commands)
        changed = np.linalg.norm(new-old, axis=1) > 1e-7
        for k in range(len(a)):
            j = (k+1) % len(a)
            if band[k] and band[j] and (changed[k] or changed[j]):
                q = [a[k], a[j], b[j], b[k]]
                parts.append('<polygon points="'+' '.join(f'{p[0]:.3f},{p[1]:.3f}' for p in q)+'" fill="#ffb34b" fill-opacity=".7"/>')
        parts += [f'<path d="{path_segments(a)}" class="before"/>', f'<path d="{path_segments(b)}" class="after"/>']
        for k in range(0, len(a), max(1, len(a)//50)):
            if band[k] and changed[k]:
                parts.append(f'<path d="M{a[k,0]:.3f},{a[k,1]:.3f} L{b[k,0]:.3f},{b[k,1]:.3f}" stroke="#936000" stroke-width=".6"/>')
        tx = (index % columns)*cell_w+14; ty = 72+(index//columns)*cell_h+cell_h-55
        near = {-1:'source left', 0:'none', 1:'source right'}[row['near_side']]
        parts += [f'<text x="{tx}" y="{ty}" font-size="14">Yaw/Pitch {escape(str(row["key"]))} | near: {near}</text>',
                  f'<text x="{tx}" y="{ty+20}" font-size="13">Max shift: {row["maximum_movement"]:.3f} model units</text>',
                  f'<text x="{tx}" y="{ty+39}" font-size="13">Far-side shift: {row["far_side_maximum_movement"]:.6f}</text>']
    parts.append('</svg>'); Path(path).write_text('\n'.join(parts), encoding='utf-8')
    return {'file': str(path), 'sha256': digest(path)}
