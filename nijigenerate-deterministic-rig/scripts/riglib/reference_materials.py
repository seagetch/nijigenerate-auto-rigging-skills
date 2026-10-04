"""Mesh helpers and the Part-stage availability contract.

Reference-authored per-model displacement transfer is withdrawn. Geometric
helpers are not themselves the required shape-based correction procedure.
"""
import re
import numpy as np
from .assembly import normalized_name, _classification
from .reference_fields import to_frame, from_frame, delta_to_frame, CORE_PARAMETERS


def fit_mesh_projection(rest,posed,indices,*,directions=None):
    """Bounded minimum projection correction with the original triangle signs."""
    from .face_transfer import cross
    from scipy.sparse import coo_matrix,eye,vstack
    import osqp
    rest=np.asarray(rest);posed=np.asarray(posed);tri=np.asarray(indices).reshape(-1,3)
    den=cross(rest[tri[:,1]]-rest[tri[:,0]],rest[tri[:,2]]-rest[tri[:,0]])
    valid=abs(den)>1e-8;tri=tri[valid];den=den[valid]
    if not len(tri):raise ValueError('Material mesh contains no valid triangles')
    ratios=cross(posed[tri[:,1]]-posed[tri[:,0]],posed[tri[:,2]]-posed[tri[:,0]])/den
    before=float(ratios.min())
    if before>=.055:return posed,{'corrected':False,'minimum_triangle_area_ratio':before}
    limit=np.linalg.norm(np.ptp(rest,axis=0))*.05;n=len(rest);solutions=[]
    if directions is None:directions=(np.array([1.,0.]),np.array([0.,1.]),np.array([1.,1.])/np.sqrt(2),np.array([-1.,1.])/np.sqrt(2))
    for direction in directions:
        direction=np.asarray(direction,float);direction/=np.linalg.norm(direction)
        e=posed[tri[:,1]]-posed[tri[:,0]];f=posed[tri[:,2]]-posed[tri[:,0]]
        b=cross(direction,f)/den;c=cross(e,direction)/den;a=-b-c
        A=coo_matrix((np.c_[a,b,c].ravel(),(np.repeat(np.arange(len(tri)),3),tri.ravel())),shape=(len(tri),n)).tocsc()
        solver=osqp.OSQP();solver.setup(P=eye(n,format='csc'),q=np.zeros(n),A=vstack([A,eye(n)],format='csc'),
            l=np.r_[.055-ratios,np.full(n,-limit)],u=np.r_[np.full(len(tri),np.inf),np.full(n,limit)],
            verbose=False,eps_abs=1e-7,eps_rel=1e-7,max_iter=50000,polishing=True)
        result=solver.solve()
        if result.info.status_val not in (1,2):continue
        out=posed+result.x[:,None]*direction
        after=float(np.min(cross(out[tri[:,1]]-out[tri[:,0]],out[tri[:,2]]-out[tri[:,0]])/den))
        if after<.0549:continue
        solutions.append((float(result.x@result.x),out,{'corrected':True,'minimum_triangle_area_ratio':after,
            'before_minimum_triangle_area_ratio':before,'maximum_projection_correction':float(max(abs(result.x))),
            'maximum_allowed_projection_correction':float(limit)}))
    if not solutions:raise ValueError('Common material correction cannot preserve mesh orientation within the projection bound')
    _,out,report=min(solutions,key=lambda x:x[0]);return out,report


def material_key(name,center,frames,rules):
    name=normalized_name(name)
    if name.startswith('hair_ear_back'):return 'hair_ear_back','head'
    if name.startswith('earring'):
        return 'earring/'+('l' if center[0]>frames['head']['origin'][0] else 'r'),'head'
    if name in ('mouth_tongue','mouth_teeth_upper','mouth_teeth_lower'):
        return 'oral/'+name.removeprefix('mouth_'),'head'
    if name in ('mouth_composite','mouth_base'):return 'mouth','head'
    semantic,_=_classification(name,rules)
    if semantic is None:return None
    rule=semantic['rule'];owner=semantic['owner']
    if semantic['usage']=='decoration':
        if owner=='torso' and semantic['chart'] in ('neck','body'):return 'decoration/torso_skin','body'
        if owner=='head' and semantic['chart']=='face':return 'decoration/face_skin','head'
    if rule in ('torso','neck'):return 'torso_skin','body'
    if rule=='face':return 'face_skin','head'
    if rule=='face_feature':
        for label,pattern in rules['facial_feature_patterns'].items():
            if re.search(pattern,name):return ('mouth' if label=='mouth' else 'feature/'+label),'head'
        return None
    if owner.startswith(('arm:','leg:')):
        family=owner.split(':')[0]
        distances={side:np.linalg.norm(np.asarray(center)-frames[family+'/'+side]['origin']) for side in ('l','r')}
        side=min(distances,key=distances.get);f=family+'/'+side
        if rule in ('arm','hand','leg','foot'):return family+'_skin/'+side,f
        return rule+'/'+side,f
    if rule=='bodice':return ('collar' if name.startswith('collar') else 'bodice'),'body'
    if rule=='waistwear':return 'corset','body'
    if rule=='hair_side':
        side='l' if center[0]>frames['head']['origin'][0] else 'r'
        return 'hair_side/'+side,'head'
    if rule.startswith('hair_'):return rule,'head'
    if rule in ('skirt','skirt_back','apron','tail'):return rule,'body'
    if rule in ('headwear','ear'):return rule,'head'
    return None


def mesh_weights(vertices,indices,query):
    """Barycentric sampling inside the real mesh; nearest vertex outside it."""
    v=np.asarray(vertices);q=np.asarray(query);tris=np.asarray(indices).reshape(-1,3)
    nearest=np.argmin(np.sum((q[:,None,:]-v[None,:,:])**2,axis=-1),axis=1)
    ids=np.repeat(nearest[:,None],3,axis=1);weights=np.zeros((len(q),3));weights[:,0]=1
    distance=np.linalg.norm(q-v[nearest],axis=1);found=np.zeros(len(q),bool)
    for tri in tris:
        a,b,c=v[tri];M=np.column_stack((b-a,c-a));det=np.linalg.det(M)
        if abs(det)<1e-10:continue
        uv=(q-a)@np.linalg.inv(M).T;w=np.c_[1-uv.sum(1),uv]
        valid=(w.min(1)>=-1e-7)&~found
        ids[valid]=tri;weights[valid]=w[valid];distance[valid]=0;found|=valid
    return ids,weights,distance


def compile_materials(sources, rules):
    raise RuntimeError('Reference-specific Part displacement compilation has been withdrawn')
