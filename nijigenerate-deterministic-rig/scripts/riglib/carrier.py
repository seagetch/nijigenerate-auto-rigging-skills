"""Rigid anatomical coordinates for sparse native GridDeformers."""
import copy
import math
import numpy as np


def rotation(angle):
    c,s=math.cos(angle),math.sin(angle)
    return np.array([[c,-s],[s,c]])


def make_carrier(owner,frame):
    # Reference Grid axes are aligned with model XY. Anatomical orientation
    # belongs to the semantic sampling frame and DepthBones, not a second
    # rotated Grid frame underneath an artwork Part.
    return {'origin':list(frame['origin']),'rotation':0.}


def to_local(points,carrier):
    return (np.asarray(points)-carrier['origin'])@rotation(carrier['rotation'])


def to_root(points,carrier):
    return np.asarray(points)@rotation(carrier['rotation']).T+carrier['origin']


def local_frames(frames,carrier):
    result=copy.deepcopy(frames);r=rotation(carrier['rotation'])
    for frame in result.values():
        frame['origin']=to_local(frame['origin'],carrier).tolist()
        frame['matrix']=(r.T@np.asarray(frame['matrix'])).tolist()
    return result


def bounds_corners(bounds):
    x0,y0,x1,y1=bounds
    return np.array([[x0,y0],[x1,y0],[x0,y1],[x1,y1]])
