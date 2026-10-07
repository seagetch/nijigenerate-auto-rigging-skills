"""Infer the neck/body attachment from a head-local alpha width profile."""
import numpy as np


def _section(points, fraction):
    lo, hi = np.quantile(points[:, 1], [.01, .99])
    y = lo + fraction * (hi - lo)
    band = points[np.abs(points[:, 1] - y) <= max(1., (hi - lo) * .025)]
    if not len(band):
        band = points[np.argsort(np.abs(points[:, 1] - y))[:max(1, len(points)//100)]]
    return np.array([np.median(band[:, 0]), y])


def infer_head_frame(face, eye_right, eye_left):
    """Eye orientation and alpha extent share one head/neck coordinate frame."""
    face = np.asarray(face, float)
    right, left = np.asarray(eye_right, float), np.asarray(eye_left, float)
    origin = (right + left) / 2
    tangent = left - right
    span = np.linalg.norm(tangent)
    if span <= 0 or tangent[0] <= 0:
        raise ValueError('Invalid paired eye frame')
    tangent /= span
    down = np.array([-tangent[1], tangent[0]])
    low, high = np.quantile((face-origin) @ down, [.01, .99])
    if high <= low:
        raise ValueError('Degenerate head extent')
    return {'origin':origin.tolist(), 'tangent':tangent.tolist(), 'normal':(-down).tolist(),
            'head_top':(origin+low*down).tolist(), 'head_root':(origin+high*down).tolist(),
            'method':'paired_eye_axis_and_projected_face_extent'}


def infer_neck_base(face, neck, torso, garments=None, head_frame=None):
    """Use the narrow-to-wide change, independently of Part boundaries.

    Input clouds share one declared source coordinate frame. Clothing is used
    only when no skin torso is available; its lower coverage is not a neck joint.
    """
    face, neck, torso = [np.asarray(p, float).reshape(-1, 2) for p in (face, neck, torso)]
    garments = np.asarray([] if garments is None else garments, float).reshape(-1, 2)
    if not len(face):
        raise ValueError('Neck inference needs head support')
    origin = np.asarray(head_frame['head_root']) if head_frame else _section(face, 1.)
    top = np.asarray(head_frame['head_top']) if head_frame else _section(face, 0.)
    down = origin - top
    height = float(np.linalg.norm(down))
    if height <= 0:
        raise ValueError('Degenerate head frame')
    down /= height
    tangent = np.array([down[1], -down[0]])
    face_u = (face-origin) @ tangent
    face_width = float(np.quantile(face_u, .99)-np.quantile(face_u, .01))
    if face_width <= 0:
        raise ValueError('Degenerate head width')
    body = torso if len(torso) else garments
    support = np.concatenate([neck, body])
    if not len(support):
        raise ValueError('Neck inference needs neck or body support')
    def profile(cloud):
        delta = cloud-origin
        t, u = delta @ down, delta @ tangent
        rows, center = [], 0.
        for i in range(129):
            station = height*i/128
            cross = np.sort(u[(np.abs(t-station) <= height*.012) & (np.abs(u) <= face_width*.9)])
            if len(cross) < 3:
                continue
            pieces = np.split(cross, np.flatnonzero(np.diff(cross) > face_width*.06)+1)
            candidates = []
            for piece in pieces:
                if len(piece) < 3:
                    continue
                left, right = np.quantile(piece, [.05, .95])
                mid = (left+right)/2
                if right-left < face_width*.08 or abs(mid) > face_width*.6:
                    continue
                candidates.append((abs(mid-center), left, right, mid))
            if not candidates:
                continue
            _, left, right, center = min(candidates)
            rows.append([float(station), float(right-left), float(center)])
        return np.array(rows).reshape(-1, 3)

    narrow_support = neck if len(neck) else torso
    neck_rows = profile(narrow_support)
    if len(neck_rows) >= 4:
        neck_width = float(np.quantile(neck_rows[:, 1], .2))
        broad_width = float(np.quantile(neck_rows[:, 1], .85))
        if neck_width < face_width*.75 and broad_width < neck_width*1.8 and neck_rows[-1, 0] < height*.7:
            delta = narrow_support-origin
            t, u = delta @ down, delta @ tangent
            station = float(np.quantile(t, .99))
            cross = u[np.abs(t-station) <= height*.025]
            transverse = float(np.median(cross))
            return {
                'xy': (origin+station*down+(0 if head_frame else transverse)*tangent).tolist(),
                'observed_xy': (origin+station*down+transverse*tangent).tolist(),
                'head_axis_constrained': bool(head_frame),
                'method': 'narrow_neck_inferior_attachment',
                'structure': 'separate_narrow_neck_material' if len(neck) else 'narrow_neck_in_body_material',
                'body_support': 'skin' if len(torso) else 'garment',
                'frame': {'origin': origin.tolist(), 'tangent': tangent.tolist(), 'normal': (-down).tolist()},
                'head_height': height, 'head_width': face_width, 'narrow_width': neck_width,
                'width_profile': neck_rows.tolist(), 'fit_mean_squared_error': None, 'provenance': 'measured',
            }
    rows = profile(support)
    if not len(rows):
        raise ValueError('No central neck/body cross sections')
    proximal = rows[rows[:, 0] <= height*.45]
    narrow = float(np.quantile(proximal[:, 1], .2)) if len(proximal) else 0.
    first = next((i for i, r in enumerate(rows) if r[1] <= narrow*1.25), None)
    crossing = None
    if narrow > 0 and narrow < face_width*.75 and first is not None:
        for i in range(first+3, len(rows)-2):
            if np.all(rows[i:i+3, 1] >= narrow*1.5):
                crossing = i
                break
    method, fitted, score = 'occluded_neck_upper_body_support', None, None
    if crossing is not None:
        end = next((i for i in range(crossing, len(rows)) if rows[i, 1] >= narrow*2.2), len(rows)-1)
        sample = rows[first:min(len(rows), end+4)]
        best = None
        for candidate in range(first+2, crossing+1):
            knot = rows[candidate, 0]
            x = np.maximum(0., sample[:, 0]-knot)
            y = sample[:, 1]
            n = len(x)
            sx, sy, sxx, sxy = float(x.sum()), float(y.sum()), float(x@x), float(x@y)
            determinant = n*sxx-sx*sx
            if determinant <= 0:
                continue
            slope = (n*sxy-sx*sy)/determinant
            intercept = (sy-slope*sx)/n
            if slope <= 0 or not narrow*.65 <= intercept <= narrow*1.5:
                continue
            residual = float(np.mean((y-intercept-slope*x)**2))
            if best is None or residual < best[0]:
                best = (residual, knot, candidate, intercept, slope)
        if best is not None:
            score, station, candidate, intercept, slope = best
            transverse = float(np.median(rows[max(first, candidate-2):candidate+3, 2]))
            fitted = origin + station*down + transverse*tangent
            method = 'narrow_neck_to_broad_torso_change'
    if fitted is None:
        # Observe the proximal body attachment when a collar hides the neck.
        # Do not use the bottom of a neck-named layer as an anatomical joint.
        delta_body = body-origin
        bt, bu = delta_body @ down, delta_body @ tangent
        upper = bt[(bt > 0) & (np.abs(bu) < face_width*.45)]
        if not len(upper):
            raise ValueError('Unresolved neck/body attachment')
        station = float(np.quantile(upper, .02))
        station = min(station, height*.55)
        fitted = origin + station*down
    measured = fitted.copy()
    if head_frame:
        fitted = origin + float((fitted-origin) @ down)*down
    return {
        'xy': fitted.tolist(), 'observed_xy': measured.tolist(),
        'head_axis_constrained': bool(head_frame), 'method': method,
        'structure': 'neck_material_includes_body' if len(neck) else 'neck_in_body_material',
        'body_support': 'skin' if len(torso) else 'garment',
        'frame': {'origin': origin.tolist(), 'tangent': tangent.tolist(), 'normal': (-down).tolist()},
        'head_height': height, 'head_width': face_width, 'narrow_width': narrow,
        'width_profile': rows.tolist(), 'fit_mean_squared_error': score,
        'provenance': 'measured' if method == 'narrow_neck_to_broad_torso_change' else 'visual_estimate',
    }
