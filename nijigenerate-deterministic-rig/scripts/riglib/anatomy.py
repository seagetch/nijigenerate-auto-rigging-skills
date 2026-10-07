"""Joint scaffold and shared front-chart depth from semantic observations.

All image-specific measurements are input data. Neither UUIDs nor source labels
are read here. This is a weighted landmark/attachment solver, not image AI.
"""
import numpy as np
from pathlib import Path
from .data import json_digest, digest


def torso_basis(roles, source, prior):
    """Reduce torso joints to one connected axis before the global solve.

    Neck and paired hip observations determine the rest axis, including lean.
    Garment centers supply station positions, never transverse spine targets.
    The pelvis is exactly attached to the paired hip midpoint. These are
    structural equalities, not a large soft penalty or a post-fit pivot edit.
    """
    policy = prior['torso_axis']
    start, end = policy['start'], policy['end']
    stations, hips = policy['stations'], policy['end_attachment']
    index = {role:i for i,role in enumerate(roles)}
    origin = source[index[start]]
    tip = np.mean([source[index[role]] for role in hips], axis=0)
    direction = tip-origin
    length2 = float(direction@direction)
    if length2 <= 0:
        raise ValueError('Degenerate torso anatomical axis')
    fractions = {role:float((source[index[role]]-origin)@direction/length2)
                 for role in stations}
    if min(np.diff([0, *fractions.values(), 1])) < policy['minimum_station_gap']:
        raise ValueError('Torso observations violate anatomical station order')
    independent = [role for role in roles if role not in [end, *stations]]
    basis = np.zeros((len(roles),len(independent)))
    for col,role in enumerate(independent):
        basis[index[role],col] = 1
    basis[index[end]] = np.mean([basis[index[role]] for role in hips],axis=0)
    for role,t in fractions.items():
        basis[index[role]] = (1-t)*basis[index[start]]+t*basis[index[end]]
    axis = direction/np.sqrt(length2)
    transverse = np.array([axis[1],-axis[0]])
    report = {'policy':policy,'station_fractions':fractions,
              'observed_axis_model':[origin.tolist(),tip.tolist()],
              'discarded_garment_transverse_offsets':{
                  role:float((source[index[role]]-origin)@transverse) for role in stations}}
    return basis, set(stations), report


def solve_scaffold(evidence, prior):
    definitions = prior["bone_graph"]
    roles = sorted({role for _, _, h, t in definitions for role in (h, t)})
    supplied = evidence["landmarks"]
    missing = set(roles) - set(supplied)
    if missing:
        raise ValueError(f"Unresolved scaffold observations: {sorted(missing)}")
    transform = np.asarray(evidence["source_to_model"], float)
    if transform.shape != (3, 3) or not np.isfinite(transform).all():
        raise ValueError("source_to_model must be finite 3x3")
    linear = transform[:2,:2]
    if not np.allclose(transform[2], [0,0,1]) or np.linalg.det(linear) <= 0 or not np.allclose(linear.T@linear, np.eye(2)*np.linalg.det(linear)):
        raise ValueError("source_to_model must be an orientation-preserving similarity")
    source, weights, rows, target = [], [], [], []
    index = {r:i for i,r in enumerate(roles)}
    for role in roles:
        entry = supplied[role]
        if entry["provenance"] not in {"visual_estimate", "measured", "prior"}:
            raise ValueError("invalid anatomical evidence provenance")
        xy = np.asarray(entry["xy"], float)
        weight = float(entry.get("weight", 1))
        if xy.shape != (2,) or not np.isfinite(xy).all() or not np.isfinite(weight) or weight<=0:
            raise ValueError("invalid landmark")
        xy = (transform @ np.r_[xy,1])[:2]
        source.append(xy)
        weights.append(weight)
    source = np.asarray(source)
    # A garment's upper alpha section can be above the jaw. It is coverage,
    # not the inferior neck joint. Native terminal-bone axes are inferred
    # from parent node positions, so this mistake reverses Head yaw.
    down = source[index['head_root']] - source[index['head_top']]
    down /= np.linalg.norm(down)
    neck_order = {'observed_neck_base':source[index['neck_base']].tolist(),
                  'method':'observed neck joint retained'}
    if (source[index['neck_base']]-source[index['head_root']])@down <= 0:
        source[index['neck_base']] = np.mean([source[index['shoulder.L']],source[index['shoulder.R']]],axis=0)
        neck_order['method']='paired PSD shoulder roots; upper garment alpha is not the neck base'
    neck_order['neck_base_used']=source[index['neck_base']].tolist()
    basis, station_roles, axis_report = torso_basis(roles, source, prior)
    for role,xy,weight in zip(roles,source,weights):
        if role in station_roles:
            # The observation already supplied its axial fraction. Including
            # its transverse residual here would drag the common axis sideways.
            continue
        row = np.zeros(len(roles)); row[index[role]] = np.sqrt(weight)
        rows.append(row); target.append(xy*np.sqrt(weight))
    for constraint in prior["joint_constraints"]:
        row = np.zeros(len(roles))
        for role, value in constraint["terms"].items():
            row[index[role]] = value*np.sqrt(constraint["weight"])
        rows.append(row); target.append([0,0])
    fitted = basis @ np.linalg.lstsq(np.asarray(rows) @ basis, target, rcond=None)[0]
    # Terminal Head orientation is inferred from Neck -> Head node positions.
    # The shoulder observation must not pull that axis off the facial frame.
    head_root, head_top = fitted[index['head_root']], fitted[index['head_top']]
    head_down = head_root-head_top
    head_down /= np.linalg.norm(head_down)
    station = float((fitted[index['neck_base']]-head_root) @ head_down)
    if station <= 0:
        raise ValueError('Neck attachment must be below Head along the facial axis')
    fitted[index['neck_base']] = head_root+station*head_down
    axis_policy=prior['torso_axis']
    origin, tip=fitted[index[axis_policy['start']]], fitted[index[axis_policy['end']]]
    for role, fraction in axis_report['station_fractions'].items():
        fitted[index[role]]=(1-fraction)*origin+fraction*tip
    points = {r:fitted[index[r]].tolist() for r in roles}
    height = float(np.linalg.norm(fitted[index['head_top']] - (fitted[index['foot_tip.L']]+fitted[index['foot_tip.R']])/2))
    residual = np.linalg.norm(fitted-np.asarray(source),axis=1)
    if height <= 0 or max(residual)/height > prior["acceptance"]["joint_fit_max_relative_residual"]:
        worst=sorted(zip(roles,(residual/max(height,1e-12)).tolist(),source.tolist(),fitted.tolist()),key=lambda v:-v[1])[:4]
        raise ValueError("joint fit residual exceeds declared tolerance: "+str(worst))
    axis_policy = prior['torso_axis']
    axial_roles = [axis_policy['start'], *axis_policy['stations'], axis_policy['end']]
    axial_points = np.array([points[role] for role in axial_roles])
    direction = axial_points[-1]-axial_points[0]
    direction /= np.linalg.norm(direction)
    transverse = np.array([direction[1],-direction[0]])
    deviations = (axial_points-axial_points[0])@transverse
    if max(abs(deviations)) > height*1e-9 or min(np.diff(axial_points@direction)) <= 0:
        raise ValueError('Solved torso axis violates collinearity or joint order')
    axis_report.update({'roles':axial_roles,'fitted_axis_model':axial_points.tolist(),
                        'max_transverse_deviation':float(max(abs(deviations))),
                        'anatomical_order_valid':True})
    bones=[]
    for name,parent,h,t in definitions:
        a,b = points[h],points[t]
        if np.linalg.norm(np.array(a)-b)<height*1e-5:
            raise ValueError("zero-length bone")
        bones.append({"id":name,"parent":parent,"head":[*a,0.0],"tail":[*b,0.0],
                      "lock_to_root":name.startswith('Foot.'),"rest_roll":0.0})
    shape = {}
    for name, spec in evidence["volumes"].items():
        center = (transform @ np.r_[spec['center'],1])[:2]
        scale = np.sqrt(np.linalg.det(linear))
        axis=(np.asarray(points['head_root'])-points['head_top']) if name=='head' else (np.asarray(points['pelvis'])-points['neck_base'])
        axis=axis/np.linalg.norm(axis)
        frame=np.column_stack(([axis[1],-axis[0]],axis))
        radii = np.asarray(spec['radii'])*scale
        if name == 'torso':
            top = np.asarray(points[axis_policy['start']]); bottom = np.asarray(points[axis_policy['end']])
            center = (top+bottom)/2
            radii[1] = np.linalg.norm(bottom-top)/2
        shape[name] = {"center":center.tolist(),"radii":radii.tolist(),
                       "frame":frame.tolist(),
                       "source":"visual contour and declared thickness prior"}
    result={"schema_version":"rig-scaffold/1","status":"fitted_landmark_scaffold","landmarks":points,
            "bones":bones,"volumes":shape,"body_height":height,
            "torso_axis_fit":axis_report,"generator_sha256":digest(Path(__file__)),
            "neck_joint_observation":neck_order,
            "residual_model_units":dict(zip(roles,residual.tolist())),
            "evidence_sha256":json_digest(evidence),"prior_sha256":json_digest(prior),
            "limitations":["visible landmarks plus declared shape priors; hidden anatomy is estimated",
                           "front charts; no full backside synthesis or collision solver"]}
    result['content_sha256']=json_digest(result)
    return result


def depth_field(xy, domain, scaffold, prior):
    """One registered field per physical owner, sampled by all material charts."""
    xy=np.asarray(xy,float)
    kind=domain['kind']
    owner=domain['owner']
    if owner in ('head','torso'):
        v=scaffold['volumes'][owner]
        center=np.asarray(v['center']); radii=np.asarray(v['radii'])
        if (radii<=0).any(): raise ValueError('volume radii must be positive')
        uv=((xy-center)@np.asarray(v['frame']))/radii
        cross=np.clip(1-uv[:,0]**2,0,1)
        if owner=='head':
            # A front cap with bounded silhouette slope. A square-root
            # ellipsoid has unbounded edge slope and can fold a 2.5D chart
            # under yaw/pitch without a hidden-side visibility mechanism.
            z=prior['depth_ratios'][owner]*radii[0]*np.clip(1-(uv**2).sum(axis=1),0,1)
        else:
            z=prior['depth_ratios'][owner]*radii[0]*np.sqrt(cross)
    else:
        side=domain['side']
        kind_limb=owner.split(':')[0]
        roles=['shoulder','elbow','wrist'] if kind_limb=='arm' else ['hip','knee','ankle']
        pts=[np.asarray(scaffold['landmarks'][f'{r}.{side}']) for r in roles]
        distances=[]
        for a,b in zip(pts[:-1],pts[1:]):
            t=np.clip(((xy-a)@(b-a))/np.dot(b-a,b-a),0,1)
            distances.append(np.linalg.norm(xy-(a+t[:,None]*(b-a)),axis=1))
        d=np.min(distances,axis=0)
        radius=domain['radius']
        z=prior['depth_ratios']['limb']*radius*np.sqrt(np.clip(1-(d/radius)**2,0,1))
    if kind=='neck':
        a=np.asarray(scaffold['landmarks']['head_root']); b=np.asarray(scaffold['landmarks']['neck_base'])
        t=np.clip(((xy-a)@(b-a))/np.dot(b-a,b-a),0,1)
        distance=np.linalg.norm(xy-(a+t[:,None]*(b-a)),axis=1)
        width=np.linalg.norm(np.asarray(scaffold['landmarks']['shoulder.L'])-scaffold['landmarks']['shoulder.R'])*.14
        z=width*np.sqrt(np.clip(1-(distance/width)**2,0,1))
    elif kind in ('skirt_front','skirt_back','free_cloth'):
        b=np.asarray(domain['support_bounds'])
        t=np.clip((xy[:,1]-b[1])/max(b[3]-b[1],1),0,1)
        radius=(b[2]-b[0])/2*(.45+.55*t)
        q=(xy[:,0]-(b[0]+b[2])/2)/np.maximum(radius,1)
        z=prior['depth_ratios']['skirt']*radius*np.sqrt(np.clip(1-q*q,0,1))
        if kind=='skirt_back': z=-z
        z+=domain.get('offset',0.0)
    elif kind=='back_hair':
        z=-z-domain.get('offset',0)
    elif kind=='appendage':
        z=np.full(len(xy),domain.get('offset',0.0))
    else:
        z=z+domain.get('offset',0.0)
    if not np.isfinite(z).all(): raise ValueError('nonfinite depth field')
    return z


def regular_mesh(bounds, step, minimum=2, maximum=80):
    b=np.asarray(bounds,float)
    if b.shape!=(4,) or not np.isfinite(b).all() or step<=0 or (b[2:]<=b[:2]).any():
        raise ValueError('invalid mesh bounds/step')
    nx,ny=np.clip(np.ceil((b[2:]-b[:2])/step).astype(int),minimum,maximum)
    xs=np.linspace(b[0],b[2],nx+1); ys=np.linspace(b[1],b[3],ny+1)
    xy=np.array([[x,y] for y in ys for x in xs])
    faces=[]
    for j in range(ny):
        for i in range(nx):
            a=j*(nx+1)+i
            faces.extend([[a,a+nx+1,a+1],[a+1,a+nx+1,a+nx+2]])
    return xy,np.asarray(faces),xs,ys
