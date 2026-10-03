"""Error-bounded face sampling and explicit silhouette projection correction.

Depth is the unmodified template field. Projection corrections act along the
projected depth direction at the outer face only; internal features are fixed.
"""
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'.runtime'))
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, hstack, vstack, eye
import osqp


def interpolate_grid(xs, ys, values, points):
    p=np.asarray(points);i=np.clip(np.searchsorted(xs,p[:,0])-1,0,len(xs)-2)
    j=np.clip(np.searchsorted(ys,p[:,1])-1,0,len(ys)-2)
    u=(p[:,0]-xs[i])/(xs[i+1]-xs[i]);v=(p[:,1]-ys[j])/(ys[j+1]-ys[j])
    data=np.asarray(values).reshape(len(ys),len(xs),-1)
    return ((1-u)[:,None]*(1-v)[:,None]*data[j,i]+u[:,None]*(1-v)[:,None]*data[j,i+1]
            +(1-u)[:,None]*v[:,None]*data[j+1,i]+u[:,None]*v[:,None]*data[j+1,i+1])


def cross(a,b):return a[...,0]*b[...,1]-a[...,1]*b[...,0]


def minimum_ratio(q,xs,ys):
    q=np.asarray(q).reshape(len(ys),len(xs),2)
    dx=q[:-1,1:]-q[:-1,:-1];dy=q[1:,:-1]-q[:-1,:-1]
    dx2=q[1:,1:]-q[1:,:-1];dy2=q[1:,1:]-q[:-1,1:]
    den=np.diff(ys)[:,None]*np.diff(xs)[None,:]
    return min(float((cross(a,b)/den).min()) for a,b in ((dx,dy),(dx2,dy2),(dx,dy2),(dx2,dy)))


def jacobian_constraints(points,xs,ys,direction):
    q=np.asarray(points);n=len(q);rr=[];cc=[];vv=[];rhs=[];base=[]
    for j in range(len(ys)-1):
        for i in range(len(xs)-1):
            a=j*len(xs)+i;b=a+1;c=a+len(xs);d=c+1
            area=(xs[i+1]-xs[i])*(ys[j+1]-ys[j])
            for ea,eb,fa,fb in [(a,b,a,c),(c,d,b,d),(a,b,b,d),(c,d,a,c)]:
                e=q[eb]-q[ea];f=q[fb]-q[fa];det=cross(e,f)
                coef={}
                for k,val in [(eb,cross(direction,f)),(ea,-cross(direction,f)),
                              (fb,cross(e,direction)),(fa,-cross(e,direction))]:
                    coef[k]=coef.get(k,0)+val/area
                row=len(rhs)
                for k,val in coef.items():rr.append(row);cc.append(k);vv.append(-val)
                rhs.append(float(det/area-.055));base.append(float(det/area))
    return coo_matrix((vv,(rr,cc)),shape=(len(rhs),n)).tocsr(),np.array(rhs),min(base)


def preserve_orientation(q,xs,ys,uv,depth_direction,width,protected=None):
    """Smooth minimum-norm contour correction under linear Jacobian constraints.

    For q'=q+s*b, each cell-corner determinant is linear in s because b is
    shared and cross(b,b)=0. Thus the quadratic program constrains the complete bilinear cell,
    without changing Z or multiplying down the authored pose.
    """
    direction=np.asarray(depth_direction,float);norm=np.linalg.norm(direction)
    if norm<1e-9:return q,{'maximum_correction':0.,'corrected':False}
    direction/=norm
    A,rhs,minimum=jacobian_constraints(q,xs,ys,direction)
    if minimum>=.055:return q,{'maximum_correction':0.,'corrected':False,'raw_minimum_jacobian':minimum}
    n=len(q);allowed=(uv[:,0]<.3)|(uv[:,0]>.7)|(uv[:,1]<.2)|(uv[:,1]>.8)
    if protected is not None:allowed &= ~np.asarray(protected,bool)
    # A smooth quadratic objective avoids the sparse kinks of an L1 solution.
    rows=[];cols=[];vals=[];edge=0
    for j in range(len(ys)):
        for i in range(len(xs)):
            a=j*len(xs)+i
            for b,distance in ([(a+1,xs[i+1]-xs[i])] if i+1<len(xs) else [])+([(a+len(xs),ys[j+1]-ys[j])] if j+1<len(ys) else []):
                rows.extend([edge,edge]);cols.extend([a,b]);vals.extend([-1/distance,1/distance]);edge+=1
    D=coo_matrix((vals,(rows,cols)),shape=(edge,n)).tocsr()
    H=eye(n,format='csc')+(width*.04)**2*(D.T@D)
    identity=eye(n,format='csc');matrix=vstack([A,identity],format='csc')
    bound=np.where(allowed,width*.04,0.)
    solver=osqp.OSQP();solver.setup(P=H.tocsc(),q=np.zeros(n),A=matrix,
        l=np.r_[np.full(len(rhs),-np.inf),-bound],u=np.r_[rhs,bound],
        verbose=False,eps_abs=1e-7,eps_rel=1e-7,max_iter=50000,polishing=True,adaptive_rho=False)
    result=solver.solve()
    if result.info.status_val not in (1,2):
        k=int(np.argmin(rhs))//4;j,i=divmod(k,len(xs)-1)
        cell=uv.reshape(len(ys),len(xs),2)[j:j+2,i:i+2]
        raise ValueError('No bounded contour projection preserving template depth: '+str({'minimum':minimum,'uv':cell.tolist(),'message':result.info.status}))
    scalar=result.x;corrected=q+scalar[:,None]*direction
    _,_,after=jacobian_constraints(corrected,xs,ys,direction)
    if after<.0549:raise ValueError('Contour projection failed its Jacobian constraints')
    return corrected,{'maximum_correction':float(max(abs(scalar))),'corrected':True,
                      'raw_minimum_jacobian':minimum,'corrected_minimum_jacobian':after,
                      'protected_interior_max_correction':float(max(abs(scalar[~allowed]))),
                      'policy':'smooth minimum squared displacement along projected depth; outer UV ring excluding template eye/mouth patches; central nose region fixed; maximum 4% width'}


def fit_grid_depth(xs,ys,base,query,truth,tolerance,anchor_count):
    p=np.asarray(query);i=np.clip(np.searchsorted(xs,p[:,0])-1,0,len(xs)-2);j=np.clip(np.searchsorted(ys,p[:,1])-1,0,len(ys)-2)
    u=(p[:,0]-xs[i])/(xs[i+1]-xs[i]);v=(p[:,1]-ys[j])/(ys[j+1]-ys[j]);a=j*len(xs)+i
    cols=np.c_[a,a+1,a+len(xs),a+len(xs)+1].ravel();weights=np.c_[(1-u)*(1-v),u*(1-v),(1-u)*v,u*v].ravel()
    n=len(base);A=coo_matrix((weights,(np.repeat(np.arange(len(p)),4),cols)),shape=(len(p),n)).tocsr()
    residual=truth-A@base;zero=coo_matrix(A.shape).tocsr();identity=eye(n,format='csr')
    matrix=vstack([hstack([A,zero]),hstack([-A,zero]),hstack([identity,-identity]),hstack([-identity,-identity])],format='csr')
    limit=tolerance*.98
    bounds=[(max(-float(z),-limit),limit) for z in base]+[(0,None)]*n
    anchors=hstack([A[-anchor_count:],coo_matrix((anchor_count,n))],format='csr')
    result=linprog(np.r_[np.zeros(n),np.ones(n)],A_ub=matrix,
                   b_ub=np.r_[residual+limit,-residual+limit,np.zeros(2*n)],
                   A_eq=anchors,b_eq=residual[-anchor_count:],bounds=bounds,method='highs')
    if not result.success:return None
    return base+result.x[:n]


def adaptive_mesh(bounds,seeds,query,field,tolerance,max_vertices=680,axes=None):
    """Conforming rectangular refinement with shared edge vertices.

    Each leaf is triangulated as a centre fan. Neighbouring leaves share all
    edge samples, including T junctions. Refinement on carrier axes eventually
    produces triangles inside one bilinear cell, whose orientation is certified.
    """
    bounds=np.round(np.asarray(bounds,float),4)
    query=np.asarray(query);query=query[np.all((query>=bounds[:2])&(query<=bounds[2:]),axis=1)]
    truth=field(query);leaves=[tuple(bounds)];trials=[]
    axes=[np.asarray(a) for a in axes] if axes is not None else None
    def evaluate(rects):
        corners=np.unique(np.array([(x,y) for l,t,r,b in rects for x,y in [(l,t),(r,t),(r,b),(l,b)]]),axis=0)
        vertices=list(map(tuple,corners));lookup={p:i for i,p in enumerate(vertices)};triangles=[];owners=[]
        for k,(l,t,r,b) in enumerate(rects):
            edge=[]
            for axis,value,lo,hi,reverse in [(1,t,l,r,False),(0,r,t,b,False),(1,b,l,r,True),(0,l,t,b,True)]:
                pts=corners[(abs(corners[:,axis]-value)<1e-7)&(corners[:,1-axis]>=lo)&(corners[:,1-axis]<=hi)]
                pts=pts[np.argsort(pts[:,1-axis])]
                if reverse:pts=pts[::-1]
                edge.extend(map(tuple,pts[:-1]))
            center=(round((l+r)/2,4),round((t+b)/2,4));ci=len(vertices);vertices.append(center)
            for a,bp in zip(edge,edge[1:]+edge[:1]):
                triangles.append((ci,lookup[a],lookup[bp]));owners.append(k)
        vertices=np.array(vertices);triangles=np.array(triangles);owners=np.array(owners)
        values=field(vertices);p=vertices[triangles];rest=cross(p[:,1]-p[:,0],p[:,2]-p[:,0])
        if min(rest)<=1e-9:raise ValueError('Degenerate conforming mesh')
        posed=vertices[:,None,:]+values[:,1:].reshape(len(vertices),-1,2)
        ratios=cross(posed[triangles[:,1]]-posed[triangles[:,0]],posed[triangles[:,2]]-posed[triangles[:,0]])/rest[:,None]
        leaf_error=np.zeros(len(rects));leaf_ratio=np.ones(len(rects));covered=np.zeros(len(query),bool)
        for k,(l,t,r,b) in enumerate(rects):
            ix=np.flatnonzero((query[:,0]>=l)&(query[:,0]<=r)&(query[:,1]>=t)&(query[:,1]<=b))
            tids=np.flatnonzero(owners==k);leaf_ratio[k]=ratios[tids].min()
            if not len(ix):continue
            q=query[ix]
            for ti in tids:
                a,bp,c=p[ti];den=rest[ti]
                w1=cross(q-a,c-a)/den;w2=cross(bp-a,q-a)/den
                inside=(w1>=-1e-8)&(w2>=-1e-8)&(w1+w2<=1+1e-8)
                if not inside.any():continue
                bary=np.c_[1-w1[inside]-w2[inside],w1[inside],w2[inside]]
                err=np.max(abs(bary@values[triangles[ti]]-truth[ix[inside]]))
                leaf_error[k]=max(leaf_error[k],err);covered[ix[inside]]=True
        if not covered.all():raise ValueError('Mesh excludes opaque samples')
        return vertices,triangles,leaf_error,leaf_ratio
    current=evaluate(leaves)
    for iteration in range(1000):
        vertices,triangles,errors,ratios=current
        trial={'vertices':len(vertices),'triangles':len(triangles),'max_error':float(max(errors)),
               'minimum_triangle_ratio':float(min(ratios)),'leaves':len(leaves)}
        trials.append(trial)
        if max(errors)<=tolerance and min(ratios)>=.03:
            return vertices,triangles[:,[0,2,1]],trials
        # Certify orientation first, then refine the largest rendered residual.
        bad=np.flatnonzero(ratios<.03)
        k=int(bad[np.argmin(ratios[bad])]) if len(bad) else int(np.argmax(errors))
        rect=np.array(leaves[k]);candidates=[]
        for axis in range(2):
            lo,hi=rect[axis],rect[axis+2];mid=(lo+hi)/2
            if axes is not None:
                cuts=axes[axis][(axes[axis]>lo+.01)&(axes[axis]<hi-.01)]
                if len(cuts):mid=float(cuts[np.argmin(abs(cuts-mid))])
            mid=round(mid,4)
            if min(mid-lo,hi-mid)<.01:continue
            first=rect.copy();second=rect.copy();first[axis+2]=mid;second[axis]=mid
            new=leaves[:k]+[tuple(first),tuple(second)]+leaves[k+1:]
            result=evaluate(new)
            if len(result[0])>max_vertices:continue
            e=result[2][k:k+2];r=result[3][k:k+2]
            score=(float(np.maximum(.03-r,0).sum()),float(max(e)),float(sum(e)),axis)
            candidates.append((score,new,result))
        if not candidates:raise ValueError('Conforming mesh exceeds native payload budget: '+str(trial))
        _,leaves,current=min(candidates,key=lambda x:x[0])
    raise ValueError('Conforming mesh did not converge')


def adaptive_axes(initial_x,initial_y,sample_depth,query,truth,width,max_points=1600,anchor_count=9):
    """Refine the largest measured depth error; never average semantic curves."""
    xs=np.array(initial_x);ys=np.array(initial_y);trials=[]
    tolerance=width*.005
    for iteration in range(150):
        points=np.array([[x,y] for y in ys for x in xs]);z=sample_depth(points)
        approx=interpolate_grid(xs,ys,z,query)[:,0];errors=abs(approx-truth)
        worst=int(np.argmax(errors));score=float(errors[worst])
        trials.append({'points':[len(xs),len(ys)],'maximum_error':score,'mean_error':float(np.mean(errors))})
        if score<=tolerance:return xs,ys,z,trials
        if len(points)>=1200:
            fitted=fit_grid_depth(xs,ys,z,query,truth,tolerance,anchor_count)
            if fitted is not None:
                errors=abs(interpolate_grid(xs,ys,fitted,query)[:,0]-truth)
                trials.append({'points':[len(xs),len(ys)],'maximum_error':float(max(errors)),
                               'mean_error':float(np.mean(errors)),
                               'maximum_nodal_adjustment':float(max(abs(fitted-z))),
                               'method':'minimum L1 resampling correction; exact feature anchors; nodal and opaque error bounded by template tolerance'})
                return xs,ys,fitted,trials
        p=query[worst];ix=np.clip(np.searchsorted(xs,p[0])-1,0,len(xs)-2);iy=np.clip(np.searchsorted(ys,p[1])-1,0,len(ys)-2)
        candidates=[]
        for axis,index in [(0,ix),(1,iy)]:
            a=xs if axis==0 else ys
            if (len(xs)+(axis==0))*(len(ys)+(axis==1))>max_points:continue
            value=round(float((a[index]+a[index+1])/2),4)
            if min(value-a[index],a[index+1]-value)<.01:continue
            xx=np.sort(np.r_[xs,value]) if axis==0 else xs;yy=np.sort(np.r_[ys,value]) if axis==1 else ys
            zz=sample_depth(np.array([[x,y] for y in yy for x in xx]))
            ee=abs(interpolate_grid(xx,yy,zz,query)[:,0]-truth)
            candidates.append((float(np.max(ee)),float(np.mean(ee)),axis,xx,yy))
        if not candidates:raise ValueError(f'Face transfer tolerance not reached within NJC point budget: {trials[-1]}')
        _,_,_,xs,ys=min(candidates,key=lambda t:t[:3])
    raise ValueError('Face sampling did not converge')
