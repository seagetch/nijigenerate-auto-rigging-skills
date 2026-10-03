"""Read and validate actual native rest bones against the shared scaffold."""
import numpy as np
from .data import json_digest


def validate_rest_scaffold(client, state, program):
    if state['program_sha256'] != program['content_sha256']:
        raise ValueError('Scaffold program and native state differ')
    spec = program['scaffold']
    axis = spec['torso_axis_fit']
    tolerance = max(1e-5, spec['body_height']*1e-6)
    observed, joints, errors = {}, {}, []
    expected_points = {tuple(bone[end]):role for role,p in spec['landmarks'].items()
                       for bone in spec['bones'] for end in ('head','tail')
                       if np.allclose(bone[end][:2],p,rtol=0,atol=1e-9)}
    for bone in spec['bones']:
        uid = state['bones'][bone['id']]
        item = client.read(uid).get('item',{})
        data = item.get('data',{})
        if item.get('uuid') != uid or data.get('type') != 'DepthBone' or data.get('boneId') != bone['id']:
            raise ValueError('Unexpected native bone identity')
        observed[bone['id']] = data
        for field,key in [('restHead','head'),('restTail','tail')]:
            value = np.asarray(data[field],float)
            if value.shape != (3,) or not np.isfinite(value).all():
                raise ValueError('Invalid native rest joint')
            error = float(np.max(abs(value-np.asarray(bone[key]))))
            errors.append(error)
            if error > tolerance:
                raise ValueError('Saved rest joint differs from compiled anatomy')
            role = expected_points.get(tuple(bone[key]))
            if role is None:continue  # Auxiliary support endpoints are not anatomical landmarks.
            # PSD landmarks are XY joints. Auxiliary reference rest-Z is an
            # independent support datum; its exact XYZ value was checked above.
            if role in joints and np.linalg.norm(value[:2]-joints[role][:2]) > tolerance:
                raise ValueError('Disconnected shared rest joint: '+role)
            joints[role] = value
    points = np.array([joints[role][:2] for role in axis['roles']])
    direction = points[-1]-points[0]
    direction /= np.linalg.norm(direction)
    transverse = np.array([direction[1],-direction[0]])
    deviation = float(max(abs((points-points[0])@transverse)))
    order = bool(min(np.diff(points@direction))>0)
    policy = axis['policy']
    hip_mid = np.mean([joints[role] for role in policy['end_attachment']],axis=0)
    attachment_error = float(np.linalg.norm(joints[policy['end']]-hip_mid))
    if deviation > tolerance or not order or attachment_error > tolerance:
        raise ValueError('Saved skeleton violates torso axis or pelvis attachment')
    return {'native_bones':observed,'bone_count':len(observed),
            'rest_bone_readback_sha256':json_digest(observed),
            'max_program_coordinate_error':max(errors),
            'torso_axis_max_transverse_deviation':deviation,
            'torso_anatomical_order_valid':order,
            'pelvis_attachment_error':attachment_error,
            'tolerance_model_units':tolerance,'passed':True}
