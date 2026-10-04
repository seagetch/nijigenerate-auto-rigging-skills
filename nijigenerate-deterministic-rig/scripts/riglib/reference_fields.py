"""Registered reference fields in anatomical frames, independent of model identity.

Static grid inheritance is evaluated before fitting. Runtime carriers contain
the resulting absolute displacement once, so identity grouping cannot double it.
"""
import numpy as np
from .semantic_registration import affine_to,affine_from,map_chart

CORE_PARAMETERS = ('Face::Yaw-Pitch', 'Face::Roll', 'Body::Yaw-Pitch', 'Body::Roll')
DEPTH_ANGLE_PARAMETERS = CORE_PARAMETERS
TRANSFER_PARAMETERS = tuple(p for p in CORE_PARAMETERS if p not in DEPTH_ANGLE_PARAMETERS)


def sample(xs, ys, values, query):
    xs, ys = np.asarray(xs), np.asarray(ys)
    q = np.clip(np.asarray(query), [xs[0], ys[0]], [xs[-1], ys[-1]])
    a = np.asarray(values).reshape(len(ys), len(xs), -1)
    i = np.clip(np.searchsorted(xs, q[:, 0], side='right')-1, 0, len(xs)-2)
    j = np.clip(np.searchsorted(ys, q[:, 1], side='right')-1, 0, len(ys)-2)
    u = ((q[:, 0]-xs[i])/(xs[i+1]-xs[i]))[:, None]
    v = ((q[:, 1]-ys[j])/(ys[j+1]-ys[j]))[:, None]
    return (1-u)*(1-v)*a[j,i]+u*(1-v)*a[j,i+1]+(1-u)*v*a[j+1,i]+u*v*a[j+1,i+1]


def frame(origin, horizontal, vertical):
    matrix = np.column_stack((horizontal, vertical))
    if np.linalg.det(matrix) <= 0:
        raise ValueError('Anatomical registration reverses orientation')
    return {'origin': np.asarray(origin).tolist(), 'matrix': matrix.tolist()}


def to_frame(points, registration):
    q=affine_to(points,registration)
    return map_chart(q,registration['semantic_chart'],True) if 'semantic_chart' in registration else q


def from_frame(points, registration):
    q=map_chart(points,registration['semantic_chart']) if 'semantic_chart' in registration else points
    return affine_from(q,registration)


def delta_to_frame(points,offset,registration):
    return to_frame(np.asarray(points)+offset,registration)-to_frame(points,registration)


def delta_from_frame(points,offset,registration):
    q=to_frame(points,registration)
    return from_frame(q+offset,registration)-np.asarray(points)


def make_frames(bones, face_bounds):
    """The same face bounds and bone endpoints are observed in references/PSD."""
    get = lambda name, end='head': np.asarray(bones[name][end])[:2]
    pelvis, neck = get('Pelvis'), get('Neck')
    vertical = pelvis-neck
    length = np.linalg.norm(vertical)
    down = vertical/length
    across = np.array([down[1], -down[0]])
    width = abs((get('UpperArm.L')-get('UpperArm.R'))@across)
    frames = {'body': frame(pelvis, across*width, vertical)}
    b = np.asarray(face_bounds)
    frames['head'] = frame((b[:2]+b[2:])/2, [b[2]-b[0], 0], [0, b[3]-b[1]])
    for side in ('L','R'):
        for family, proximal, distal in [('arm','UpperArm','Hand'),('leg','Thigh','Foot')]:
            start = get(proximal+'.'+side)
            end = get(distal+'.'+side)
            axis = end-start
            down = axis/np.linalg.norm(axis)
            across = np.array([down[1], -down[0]])
            frames[family+'/'+side.lower()] = frame(start, across*length, axis)
    return frames


def frame_role(role):
    if role == 'face' or role.startswith(('hair_', 'headwear')): return 'head'
    family = role.split('/')[0]
    if family in ('arm','sleeve','leg'):
        return ('arm' if family == 'sleeve' else family)+'/'+role.split('/')[-1]
    return 'body'


def evaluate_component(template,name,parameter,i,j,root_points,frames):
    """Compose the single template's parent support in the target anatomy."""
    c=template['components'][name];f=frames[c['frame']]
    q=to_frame(root_points,f)
    values=c['deformations'][parameter]['values'][i][j]
    if c.get('vector_transport')!='anatomical_basis_linear':
        raise ValueError('Body Grid motion must declare its anatomical vector basis')
    result=sample(c['axis_x'],c['axis_y'],values,q)@np.asarray(f['matrix']).T
    attachment=c['attachment'];parent=c['parent_surface']
    if parent is not None:
        if attachment['mode']=='translation_at_node_origin':
            point=from_frame([attachment['point_in_child_frame']],f)
            result+=evaluate_component(template,parent,parameter,i,j,point,frames)
        elif attachment['mode']=='parent_grid_field':
            result+=evaluate_component(template,parent,parameter,i,j,root_points,frames)
        else:raise ValueError('Unsupported registered parent support')
    return result


def fit_positive_cells(*args, **kwargs):
    raise ValueError('Angle-specific Grid vertex fitting is forbidden; repair common depth and skeletal support')


class StaticReference:
    """Evaluate captured static grids, including propagation stopping at Nodes.

    Part is a propagating drawable; Grid/ordinary Node stop propagation.
    A stopped ordinary Node inherits translation at its origin. A nested Grid
    inherits the parent field at its vertices. Dynamic grids are rejected.
    """
    def __init__(self, snapshot, nodes, parents, world):
        self.nodes, self.parents, self.world = nodes, parents, world
        self.bindings = {}
        for b in snapshot['bindings']:
            if b['parameter']['name'] not in CORE_PARAMETERS: continue
            uid = b['target']['uuid']
            if uid not in nodes or nodes[uid]['type']=='DepthBone': continue
            if b['name'] != 'deform':
                raise ValueError('Unresolved artwork transform binding: '+nodes[uid]['name'])
            self.bindings[uid,b['parameter']['name']] = b
        self.cache = {}

    def ancestors(self, uid):
        path=[]; p=self.parents[uid]
        while p is not None:
            if self.nodes[p]['type']=='GridDeformer': return p, list(reversed(path))
            path.append(p); p=self.parents[p]
        return None, []

    def grid_values(self, uid, parameter, i, j):
        key=(uid,parameter,i,j)
        if key in self.cache:return self.cache[key]
        d=self.nodes[uid]
        if d.get('dynamic'): raise ValueError('Dynamic reference grid needs a separate evaluator')
        matrix=self.world(uid)
        xy=np.array([[x,y] for y in d['grid_axis_y'] for x in d['grid_axis_x']])
        root=xy@matrix[:2,:2].T+matrix[:2,3]
        b=self.bindings.get((uid,parameter))
        values=np.zeros_like(root)
        if b is not None:
            if not np.asarray(b['data']['isSet']).all():
                raise ValueError('Reference has uncommitted deformation keys')
            values=np.asarray(b['data']['values'][i][j]).reshape(-1,2)@matrix[:2,:2].T
        parent,path=self.ancestors(uid)
        if parent is not None:
            stopper=next((p for p in path if self.nodes[p]['type']!='Part'),None)
            if stopper is None:
                values += self.at(parent,parameter,i,j,root)
            elif self.nodes[stopper]['type']=='Node':
                # TranslateChildren is serialized as translate_children.
                if self.nodes[parent].get('translate_children',True):
                    origin=self.world(stopper)[:2,3]
                    values += self.at(parent,parameter,i,j,origin[None,:])
            else:
                raise ValueError('Unsupported reference propagation boundary: '+self.nodes[stopper]['type'])
        self.cache[key]=values
        return values

    def at(self, uid, parameter, i, j, root_points):
        d=self.nodes[uid]; m=self.world(uid)
        local=(np.asarray(root_points)-m[:2,3])@np.linalg.inv(m[:2,:2]).T
        return sample(d['grid_axis_x'],d['grid_axis_y'],self.grid_values(uid,parameter,i,j),local)

    def local_at(self, uid, parameter, i, j, root_points):
        d=self.nodes[uid];m=self.world(uid)
        b=self.bindings.get((uid,parameter))
        if b is None:return np.zeros((len(root_points),2))
        if not np.asarray(b['data']['isSet']).all():raise ValueError('Uncommitted reference keys')
        local=(np.asarray(root_points)-m[:2,3])@np.linalg.inv(m[:2,:2]).T
        return sample(d['grid_axis_x'],d['grid_axis_y'],b['data']['values'][i][j],local)@m[:2,:2].T
