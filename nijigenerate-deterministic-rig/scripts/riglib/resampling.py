"""Construct landmark Grid axes and evaluate template values at their vertices."""
import numpy as np
from .reference_fields import sample,to_frame,evaluate_component

POLICY={'axis_count_authority':'maximum observed reference resolution',
        'landmark_vertex_tolerance_model':.0001,
        'value_authority':'direct evaluation after anatomical calibration; no per-vertex value fitting'}


def native_axis_distinct(axis):
    """GridDeformer normalizes float32 axes with 1e-4 relative/absolute tolerance."""
    a=np.asarray(axis,dtype=np.float32).astype(float)
    tolerance=np.maximum(1e-4,1e-4*np.maximum(abs(a[:-1]),abs(a[1:])))
    return bool(np.all(np.diff(a)>tolerance))


def anchored_axis(lower,upper,count,coordinates):
    """Move grid lines through semantic landmarks within the reference budget."""
    axis=np.unique(np.round(np.r_[lower,coordinates,upper],4))
    if len(axis)>count:raise ValueError('Semantic grid lines exceed reference division budget')
    while len(axis)<count:
        k=int(np.argmax(np.diff(axis)))
        midpoint=round(float((axis[k]+axis[k+1])/2),4)
        if midpoint in axis:raise ValueError('Reference grid budget cannot be allocated without duplicate lines')
        axis=np.sort(np.r_[axis,midpoint])
    return axis


def quantize_deformation(values,unit):
    """Bounded precision for NJC transport.

    Four significant digits keep fine grids within NJC's literal JSON limit.
    This rounds transmitted values without fitting a different field.
    """
    original=np.asarray(values)
    a=np.round(original,2)
    out=np.array([float(format(float(v),'.4g')) for v in a.ravel()]).reshape(a.shape)
    if np.max(np.linalg.norm(out-original,axis=-1))>unit*.001:
        raise ValueError('NJC wire quantization exceeds the geometric precision budget')
    return out


def calibrated_depth(template, name, registration, points, unit):
    """Evaluate the unchanged field AFTER the target's semantic calibration.

    Neither neighbour averaging nor independent vertex displacement is allowed.
    Registration retains the measured eye/nose/mouth/joint correspondence.
    """
    component = template['components'][name]
    query = to_frame(points, registration)
    return (component['depth']['plane_offset'] + sample(
        component['axis_x'], component['axis_y'], component['depth']['relief'], query)[:, 0]) * unit


def choose_grid(template,name,frames,lower,upper,unit,initial_counts,landmarks):
    """Place landmark lines and sample vertices, without a posed-point score."""
    c=template['components'][name];f=frames[c['frame']]
    anchors=np.asarray(landmarks,dtype=float).reshape(-1,2)
    anchors=anchors[np.all((anchors>=lower)&(anchors<=upper),axis=1)]
    nx,ny=initial_counts
    xs=anchored_axis(lower[0],upper[0],nx,anchors[:,0])
    ys=anchored_axis(lower[1],upper[1],ny,anchors[:,1])
    if not native_axis_distinct(xs) or not native_axis_distinct(ys):
        raise ValueError('Required semantic lines collapse under native Grid axis tolerance')
    landmark_distances=[float(np.hypot(np.min(abs(xs-p[0])),np.min(abs(ys-p[1])))) for p in anchors]
    if max(landmark_distances,default=0.)>POLICY['landmark_vertex_tolerance_model']:
        raise ValueError('Semantic landmark is not a grid vertex')
    xy=np.array([[x,y] for y in ys for x in xs])
    z=calibrated_depth(template,name,f,xy,unit)
    fields={(p,i,j):evaluate_component(template,name,p,i,j,xy,frames)
            for p,spec in c['deformations'].items()
            for i in range(len(spec['axes'][0])) for j in range(len(spec['axes'][1]))}
    if not np.isfinite(z).all() or any(not np.isfinite(v).all() for v in fields.values()):
        raise ValueError('Non-finite generated Grid values')
    return xs,ys,xy,z,fields,{'policy':POLICY,'unit_model':float(unit),
        'reference_axis_budget':list(initial_counts),'axis_counts':[len(xs),len(ys)],
        'maximum_landmark_vertex_error_model':max(landmark_distances,default=0.),
        'landmark_vertices':len(anchors)}
