"""Mesh-independent semantic charts shared by every anatomical region.

The same smooth landmark map takes canonical coordinates to observed geometry.
No material vertex index, model identity or fitted per-character coefficient is
part of the chart. A folded correspondence is rejected before model mutation.
"""
import re
from pathlib import Path
import sys
from collections import OrderedDict
import numpy as np
from .assembly import normalized_name

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'.runtime'))
from scipy.spatial import Delaunay

_inverse_cache=OrderedDict()


def affine_to(points,f):
    return (np.asarray(points)-f['origin'])@np.linalg.inv(f['matrix']).T


def affine_from(points,f):
    return np.asarray(points)@np.asarray(f['matrix']).T+f['origin']


def facial_landmarks(materials):
    """Use semantic material envelopes, consistently for reference and PSD.

    materials: normalized role name and neutral root-space geometry. Eye sides
    are spatial, never the opaque suffix in an artist's layer name.
    """
    rows=[]
    for name,xy in materials:
        q=np.asarray(xy);name=normalized_name(name)
        if len(q):rows.append((name,q,np.r_[q.min(0),q.max(0)]))
    eyes=[r for r in rows if re.fullmatch(r'(sclera|eye_white)(_[a-z]+)?',r[0])]
    noses=[r for r in rows if r[0]=='nose']
    mouths=[r for r in rows if r[0] in ('mouth_base','mouth','lips')]
    # A constructed oral cavity and an original hidden mouth are not two mouths.
    bases=[r for r in mouths if r[0]=='mouth_base']
    if bases:mouths=bases
    if len(eyes)!=2 or len(noses)!=1 or len(mouths)!=1:
        raise ValueError('Semantic registration requires two eye whites, one nose and one mouth envelope')
    eyes.sort(key=lambda r:(r[2][0]+r[2][2])/2)
    result={}
    for side,(_,q,b) in zip(('r','l'),eyes):
        result['eye_'+side+'_outer']=[float(b[0] if side=='r' else b[2]),float((b[1]+b[3])/2)]
        result['eye_'+side+'_inner']=[float(b[2] if side=='r' else b[0]),float((b[1]+b[3])/2)]
    for label,(_,q,b) in [('nose',noses[0]),('mouth',mouths[0])]:
        result[label]=((b[:2]+b[2:])/2).tolist()
        if label=='mouth':
            result['mouth_r']=[float(b[0]),float((b[1]+b[3])/2)]
            result['mouth_l']=[float(b[2]),float((b[1]+b[3])/2)]
    return result


def observed_landmarks(bones,face):
    get=lambda name,end='head':np.asarray(bones[name][end])[:2].tolist()
    result={'head':face,'body':{name.lower():get(name) for name in ('Pelvis','Spine','Chest','Neck')}}
    for side in ('L','R'):
        suffix=side.lower()
        result['body']['shoulder_'+suffix]=get('UpperArm.'+side)
        result['body']['hip_'+suffix]=get('Thigh.'+side)
        result['arm/'+suffix]={'root':get('UpperArm.'+side),'joint':get('Forearm.'+side),
                              'end':get('Hand.'+side),'tip':get('Hand.'+side,'tail')}
        result['leg/'+suffix]={'root':get('Thigh.'+side),'joint':get('Shin.'+side),
                              'end':get('Foot.'+side),'tip':get('Foot.'+side,'tail')}
    # The pelvis landmark is the midpoint of anatomical hip attachments. A
    # reference DepthBone pivot may sit above that line and is not equivalent.
    result['body']['pelvis']=((np.array(result['body']['hip_l'])+result['body']['hip_r'])/2).tolist()
    return result


def triangle_areas(points,triangles):
    p=np.asarray(points);t=np.asarray(triangles)
    a=p[t[:,1]]-p[t[:,0]];b=p[t[:,2]]-p[t[:,0]]
    return a[:,0]*b[:,1]-a[:,1]*b[:,0]


def build_charts(sources):
    charts={}
    for region in sources[0]['frames']:
        labels=sorted(sources[0]['landmarks'][region])
        if any(sorted(s['landmarks'][region])!=labels for s in sources):
            raise ValueError('Reference semantic landmarks disagree: '+region)
        observations=[affine_to([s['landmarks'][region][k] for k in labels],s['frames'][region]) for s in sources]
        canonical=np.round(np.mean(observations,axis=0),12)
        if region.startswith(('arm/','leg/')):
            # Canonical limbs have one longitudinal axis. Averaging slightly
            # bent reference joints would create narrow centerline triangles
            # and amplify tiny differences in elbow/knee placement.
            canonical[:,0]=0.
        # Shared stationary cage restrains extrapolation. TPS gives a smooth
        # extension, never nearest-point clamping of correspondence.
        extent=max(2.,float(np.max(np.abs(observations)))+1.)
        cage=np.array([[-extent,-extent],[0,-extent],[extent,-extent],[extent,0],
                       [extent,extent],[0,extent],[-extent,extent],[-extent,0]])
        points=np.vstack([canonical,cage]);tri=Delaunay(points).simplices
        charts[region]={'labels':labels,'canonical':points.tolist(),'triangles':tri.tolist(),
                        'cage_count':len(cage),'method':'shared thin plate spline semantic chart'}
    for s in sources:install_charts(s['frames'],s['landmarks'],charts)
    return charts


def install_charts(frames,landmarks,charts):
    for region,spec in charts.items():
        f=frames[region];canonical=np.asarray(spec['canonical']);labels=spec['labels']
        observed=affine_to([landmarks[region][k] for k in labels],f)
        points=np.vstack([observed,canonical[len(labels):]])
        ratios=triangle_areas(points,spec['triangles'])/triangle_areas(canonical,spec['triangles'])
        if not np.isfinite(ratios).all() or min(ratios)<=1e-4:
            raise ValueError('Folded semantic correspondence: '+region+'; no model-specific fallback')
        delta=canonical[:,None,:]-canonical[None,:,:];r2=np.sum(delta*delta,axis=-1)
        kernel=r2*np.log(np.maximum(r2,1e-30));poly=np.c_[np.ones(len(canonical)),canonical]
        system=np.block([[kernel,poly],[poly.T,np.zeros((3,3))]])
        coefficients=np.linalg.solve(system,np.vstack([points-canonical,np.zeros((3,2))]))
        chart={**spec,'observed':points.tolist(),'minimum_area_ratio':float(min(ratios)),
               'coefficients':coefficients.tolist()}
        extent=np.max(abs(canonical));probe=np.array([[x,y] for y in np.linspace(-extent,extent,41)
                                                     for x in np.linspace(-extent,extent,41)])
        _,jac=_forward(probe,chart,True);minimum=float(np.linalg.det(jac).min())
        if minimum<=.05:raise ValueError('Noninvertible smooth semantic correspondence: '+region)
        chart['minimum_sampled_jacobian']=minimum
        f['semantic_chart']=chart
    return frames


def map_chart(points,chart,inverse=False):
    q=np.asarray(points);shape=q.shape;q=q.reshape(-1,2)
    if not inverse:return _forward(q,chart).reshape(shape)
    key=(id(chart),q.shape,q.tobytes())
    if key in _inverse_cache:
        cached,owner=_inverse_cache.pop(key);_inverse_cache[key]=(cached,owner)
        return cached.reshape(shape)
    out=q.copy()
    for iteration in range(20):
        value,jac=_forward(out,chart,True);error=value-q
        if np.max(abs(error),initial=0)<1e-10:
            _inverse_cache[key]=(out.copy(),chart)
            if len(_inverse_cache)>128:_inverse_cache.popitem(last=False)
            return out.reshape(shape)
        if np.any(np.linalg.det(jac)<=.01):raise ValueError('Semantic chart inverse leaves its invertible domain')
        step=np.linalg.solve(jac,error[...,None])[...,0]
        out-=step
    raise ValueError('Semantic correspondence inverse did not converge')


def _forward(q,chart,derivative=False):
    centers=np.asarray(chart['canonical']);coef=np.asarray(chart['coefficients']);n=len(centers)
    delta=q[:,None,:]-centers[None,:,:];r2=np.sum(delta*delta,axis=-1)
    log=np.log(np.maximum(r2,1e-30));kernel=r2*log
    value=q+kernel@coef[:n]+np.c_[np.ones(len(q)),q]@coef[n:]
    if not derivative:return value
    gradient=2*delta*(log+1)[:,:,None]
    jac=np.eye(2)[None,:,:]+np.einsum('nki,kj->nji',gradient,coef[:n])+coef[n+1:].T[None,:,:]
    return value,jac
