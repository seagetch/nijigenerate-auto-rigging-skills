"""Compile local mechanisms from PSD alpha in declared feature frames."""
from pathlib import Path
import numpy as np
from PIL import Image
from .data import read_json,write_json,json_digest,digest
from .live import Live,created_id
from .model import observe_model
from .face_draw_order import plan as face_order_plan

POLICY={'version':'1.3','closed_height_ratio':.015,'mouth_open_width_ratio':.20,
        'eye_gaze_width_ratio':.18,'expression_width_ratio':.035,
        'brow_width_ratio':.08,'local_bend_radians':.55,
        'axes':[-1.,-.5,0.,.5,1.],
        'interpretation':'motion ranges are shared priors; neutral geometry and contours come from this PSD'}


def feature_frame(points):
    a,b=np.asarray(points,float);u=b-a;width=float(np.linalg.norm(u))
    if width<1e-6:raise ValueError('Degenerate observed feature axis')
    u/=width;return (a+b)/2,np.column_stack((u,[-u[1],u[0]])),width


def area_ratios(rest,delta,indices):
    t=np.asarray(indices,int).reshape(-1,3);q=rest+delta
    cross=lambda a,b:a[:,0]*b[:,1]-a[:,1]*b[:,0]
    before=cross(rest[t[:,1]]-rest[t[:,0]],rest[t[:,2]]-rest[t[:,0]])
    after=cross(q[t[:,1]]-q[t[:,0]],q[t[:,2]]-q[t[:,0]])
    return after/before


def preserve_orientation(rest,delta,indices,locked=None):
    """Closest displacement with positive native triangle areas.

    For these local mechanisms the horizontal positions are fixed during the
    solve; each signed triangle area is linear in the vertical coordinates.
    This corrects discretization of curved PSD contours on coarse AutoMesh
    triangles, without changing mesh topology or sampling another model.
    """
    if float(area_ratios(rest,delta,indices).min())>=.002:return delta
    import osqp
    from scipy import sparse
    q=rest+delta;t=np.asarray(indices,int).reshape(-1,3)
    before=np.cross(rest[t[:,1]]-rest[t[:,0]],rest[t[:,2]]-rest[t[:,0]])
    x=q[:,0];a,b,c=t.T
    coefficients=np.c_[x[c]-x[b],x[a]-x[c],x[b]-x[a]]/before[:,None]
    A=sparse.csc_matrix((coefficients.ravel(),(np.repeat(np.arange(len(t)),3),t.ravel())),shape=(len(t),len(q)))
    lower=np.full(len(t),.004);upper=np.full(len(t),np.inf)
    if locked is not None and np.any(locked):
        A=sparse.vstack([A,sparse.eye(len(q),format='csc')[np.flatnonzero(locked)]],format='csc')
        lower=np.r_[lower,q[locked,1]];upper=np.r_[upper,q[locked,1]]
    solver=osqp.OSQP();solver.setup(P=sparse.eye(len(q),format='csc'),q=-q[:,1],A=A,
        l=lower,u=upper,verbose=False,eps_abs=1e-7,eps_rel=1e-8,max_iter=30000,polishing=True)
    result=solver.solve()
    if result.info.status_val not in (1,2):raise ValueError('PSD contour orientation solve failed: '+result.info.status)
    q[:,1]=result.x
    return q-rest


def source_cloud(capture,ids,translation):
    result=[]
    for uid in ids:
        material=capture[uid];a=np.asarray(Image.open(material['file']).convert('RGBA'))[:,:,3]
        y,x=np.nonzero(a>32);stride=max(1,len(x)//20000)
        p=np.c_[x[::stride],y[::stride]]+np.asarray(material['source_bbox'][:2])+.5
        a=np.asarray(material.get('source_to_model',[[1,0,translation[0]],[0,1,translation[1]],[0,0,1]]))
        result.append(p@a[:2,:2].T+a[:2,2])
    if not result:raise ValueError('Mechanism has no observed alpha')
    return np.concatenate(result)


def profile(points,basis,origin,width):
    p=(points-origin)@basis;axis=np.linspace(-width/2,width/2,65);low=[];high=[]
    for x in axis:
        q=p[abs(p[:,0]-x)<=width/32,1]
        if not len(q):q=p[np.argsort(abs(p[:,0]-x))[:max(1,len(p)//100)],1]
        low.append(float(np.quantile(q,.02)));high.append(float(np.quantile(q,.98)))
    return axis,np.asarray(low),np.asarray(high)


def shared_brow_support(eyes,capture,translation):
    """Detect one PSD Part containing substantial alpha on both eye sides."""
    if len(eyes)!=2:return set()
    centers=np.array([np.mean(e['canthi_model'],axis=0) for e in eyes])
    candidates={uid for eye in eyes for uid in eye['part_groups'].get('brow',[])}
    shared=set()
    for uid in candidates:
        cloud=source_cloud(capture,[uid],translation)
        nearest=np.argmin(np.linalg.norm(cloud[:,None]-centers[None],axis=2),axis=1)
        # Ignore isolated alpha specks. This identifies shared artwork; it is
        # not a geometry quality gate and never rejects a model.
        if all(float(np.mean(nearest==i))>=.05 for i in range(2)):shared.add(uid)
    return shared


def compile_controls(evidence,capture,nodes,parameters=None):
    from .eyelash_shape import detect,side_compression,report as lash_report
    capture={m['part']:m for m in capture['materials']};translation=np.asarray(evidence['source_to_model'])[:2,2]
    eyes=evidence.get('eyes',[]);shared_brows=shared_brow_support(eyes,capture,translation)
    geometries={};specs={};ops=[]
    def geometry(uid):
        if uid not in geometries:
            node=nodes[uid];matrix=np.asarray(node['nominal_world_matrix'])
            if matrix.shape!=(4,4):raise ValueError('Unresolved neutral Part frame')
            mesh=node['mesh'];rest=np.asarray(mesh['vertices']);linear=matrix[:2,:2]
            geometries[uid]=(rest,rest@linear.T+matrix[:2,3],linear,mesh['indices'])
        return geometries[uid]
    def mechanism(name,axes,parts,field,detail=None):
        if parameters is not None and name not in parameters:return
        if not parts:return
        specs[name]={'axes':axes,'targets':list(dict.fromkeys(parts)),'source':'PSD_shape_field','neutral':[0.,0.]}
        for uid in specs[name]['targets']:
            rest,world,linear,indices=geometry(uid)
            for x in axes[0]:
                for y in axes[1]:
                    displacement=field(uid,world,x,y)@np.linalg.inv(linear).T
                    displacement=preserve_orientation(rest,displacement,indices)
                    if detail is not None:
                        extra=detail(uid,world,x,y)@np.linalg.inv(linear).T
                        locked=np.max(abs(extra),axis=1)<1e-12
                        displacement=preserve_orientation(rest,displacement+extra,indices,locked=locked)
                    displacement=np.round(displacement,5)
                    if not np.isfinite(displacement).all():raise ValueError('Nonfinite local mechanism')
                    minimum=float(area_ratios(rest,displacement,indices).min())
                    if minimum<=0:raise ValueError(f'Local mechanism folds: {name} {x},{y} {uid} {minimum}')
                    if x==0 and y==0 and np.max(abs(displacement))>1e-8:raise ValueError('Local mechanism changes source neutral')
                    ops.append({'parameter':name,'target':uid,'key':[x,y],'values':displacement.ravel().tolist(),'minimum_area_ratio':minimum})
    for eye in eyes:
        origin,basis,width=feature_frame(eye['canthi_model']);groups={k:list(v) for k,v in eye['part_groups'].items()}
        groups['brow']=sorted(set(groups.get('brow',[]))|shared_brows)
        cloud=source_cloud(capture,groups['sclera'],translation)
        ax,top,bottom=profile(cloud,basis,origin,width);height=float(np.median(bottom-top))
        # The white aperture is not the painted lash boundary. Move the
        # lower edge of the upper stroke and the upper edge of the lower
        # stroke to one shared contact curve. The displacement is constant
        # through each stroke's normal cross-section, preserving thickness.
        upper_contact=top
        lower_contact=bottom
        if groups.get('upper'):
            _,_,upper_contact=profile(source_cloud(capture,groups['upper'],translation),basis,origin,width)
        if groups.get('lower'):
            _,lower_contact,_=profile(source_cloud(capture,groups['lower'],translation),basis,origin,width)
        lookup={uid:role for role,ids in groups.items() for uid in ids}
        lashes=detect(capture,groups,origin,basis)
        def blink(uid,world,x,y):
            p=(world-origin)@basis;t=np.clip(p[:,0]/(width/2),-1,1)
            upper=np.interp(p[:,0],ax,top);lower=np.interp(p[:,0],ax,bottom)
            seam=(upper+lower)/2+y*width*POLICY['expression_width_ratio']*(1-t*t)
            role=lookup[uid];delta=np.zeros_like(p)
            if role=='sclera':delta[:,1]=x*(1-POLICY['closed_height_ratio'])*(seam-p[:,1])
            elif role=='lower':delta[:,1]=x*(seam-np.interp(p[:,0],ax,lower_contact))
            elif role in ('upper','fold','corner'):delta[:,1]=x*(seam-np.interp(p[:,0],ax,upper_contact))
            return delta@basis.T
        parts=[uid for role,ids in groups.items() if role not in ('iris','brow') for uid in ids]
        blink_name='Eye::'+eye['side']+'::Blink'
        def lash_detail(uid,world,x,y):
            normal=side_compression(lashes,uid,world,x,POLICY['closed_height_ratio'])
            return np.c_[np.zeros(len(world)),normal]@basis.T
        mechanism(blink_name,[[0.,.25,.5,.75,1.],[-1.,0.,1.]],parts,blink,detail=lash_detail)
        if blink_name in specs:
            specs[blink_name]['shape_analysis']=lash_report(lashes)
            specs[blink_name]['contact_curves']={'frame_origin':origin.tolist(),'frame_basis':basis.tolist(),
                'tangent':ax.tolist(),'upper_lower_edge':upper_contact.tolist(),'lower_upper_edge':lower_contact.tolist(),
                'upper_parts':groups.get('upper',[]),'lower_parts':groups.get('lower',[]),
                'target':'shared sclera midpoint plus expression curvature'}
        mechanism('Eye::'+eye['side']+'::X-Y',[POLICY['axes'],[-1.,0.,1.]],groups.get('iris',[]),
                  lambda uid,w,x,y:np.tile(np.array([x*width*.18,y*height*.18])@basis.T,(len(w),1)))
        def brow(uid,world,x,y):
            delta=np.c_[np.zeros(len(world)),x*width*.08+y*((world-origin)@basis)[:,0]*.15]@basis.T
            if uid in shared_brows:
                other=np.mean(next(e for e in eyes if e['side']!=eye['side'])['canthi_model'],axis=0)
                axis=origin-other;distance=float(np.linalg.norm(axis));axis/=distance
                weight=np.clip(.5+2*((world-(origin+other)/2)@axis)/distance,0.,1.)
                delta*=weight[:,None]
            return delta
        mechanism('Eyebrow::'+eye['side'],[POLICY['axes'],[-1.,0.,1.]],groups.get('brow',[]),brow)
    mouth=evidence.get('mouth')
    if mouth:
        origin,basis,width=feature_frame(mouth['axis_model']);groups=mouth['part_groups']
        envelope=groups.get('mouth',[]) or groups.get('mouth_outline',[]) or mouth['parts']
        cloud=source_cloud(capture,envelope,translation);local=(cloud-origin)@basis
        height=max(float(np.ptp(local[:,1])),width*.01)
        lookup={uid:role for role,ids in groups.items() for uid in ids}
        rigid={'mouth_tongue','mouth_upper_teeth','mouth_lower_teeth'}
        centers={uid:float(np.median((source_cloud(capture,[uid],translation)-origin)@basis,axis=0)[1]) for uid in mouth['parts']}
        def mouth_field(uid,world,x,y):
            q=(world-origin)@basis;t=np.clip(q[:,0]/(width/2),-1,1)
            factor=1+x*(1-POLICY['closed_height_ratio']) if x<0 else 1+x*width*.20/height
            delta=np.zeros_like(q)
            base=np.full(len(q),centers[uid]) if lookup[uid] in rigid and x>=0 else q[:,1]
            delta[:,1]=(factor-1)*base+y*width*.035*(1-t*t)
            return delta@basis.T
        mechanism('Mouth::Open',[POLICY['axes'],[-1.,0.,1.]],mouth['parts'],mouth_field)
    if evidence['kind']=='local':
        ids=[m['part'] for m in evidence['semantic_materials']]
        cloud=source_cloud(capture,ids,translation);origin=cloud.mean(0)
        _,_,vh=np.linalg.svd(cloud-origin,full_matrices=False);u=vh[0]
        if u[np.argmax(abs(u))]<0:u=-u
        basis=np.column_stack((u,[-u[1],u[0]]));q=(cloud-origin)@basis;span=max(np.ptp(q[:,0]),1.)
        def bend(uid,world,x,y):
            p=(world-origin)@basis;k=x*POLICY['local_bend_radians']/span
            q=p.copy()
            if abs(k)>1e-12:
                angle=p[:,0]*k;q[:,0]=(1/k-p[:,1])*np.sin(angle)
                q[:,1]=1/k-(1/k-p[:,1])*np.cos(angle)
            q[:,1]+=y*.1*p[:,0]
            return (q-p)@basis.T
        mechanism('Local::Bend',[POLICY['axes'],[-1.,0.,1.]],ids,bend)
    return specs,ops


def apply(run,njc,replace_owned=False):
    run=Path(run).resolve();evidence=read_json(run/'evidence.json');state=read_json(run/'native-state.json')
    if not state.get('source_uv_program_sha256'):raise ValueError('Register native AutoMesh texture placement before compiling local mechanisms')
    n=Live(njc,run/'shape-controls-journal');n.call('ToolCommand_ModelEditMode');n.call('ViewportCommand_ResetParameters')
    observation=observe_model(client=n,require_parameters=False)
    nodes={row['uuid']:row for row in observation['nodes']}
    capture=read_json(run/'capture.json')
    specs,ops=compile_controls(evidence,capture,nodes)
    face_order=face_order_plan(evidence,capture,nodes)
    if not specs:raise ValueError('No local mechanism was compiled from the PSD')
    existing={p['name']:p['uuid'] for p in n.find('Parameter')['items']}
    previous=None
    if set(specs)&set(existing):
        if not replace_owned:raise ValueError('Local controls already exist; use the owned-control refresh explicitly')
        previous=read_json(run/'shape-controls-program.json')
        if previous['content_sha256']!=state.get('shape_controls_sha256') or json_digest({k:v for k,v in previous.items() if k!='content_sha256'})!=previous['content_sha256']:
            raise ValueError('Owned local control identity mismatch')
        if not set(previous['parameters']).issubset(specs):raise ValueError('Refresh would remove an existing local mechanism')
        if any(existing[name]!=state['parameters'].get(name) for name in set(specs)&set(existing)):
            raise ValueError('Local control parameter ownership mismatch')
    for op in ops:n.preflight_call('ModelCommand_SetDeformBinding',bindingName='deform',values=op['values'],context={'parameters':[4294967295],'nodes':[op['target']],'parameterValue':op['key']})
    report={'program_sha256':state['program_sha256'],'policy':POLICY,'parameters':specs,'operations':ops,'face_draw_order':face_order,
            'source_uv_program_sha256':state['source_uv_program_sha256'],
            'evidence_sha256':json_digest(evidence),'generator_sha256':digest(Path(__file__)),
            'eyelash_shape_sha256':digest(Path(__file__).with_name('eyelash_shape.py'))}
    report['content_sha256']=json_digest(report);write_json(run/'shape-controls-pending.json',report)
    if previous:
        for name,spec in previous['parameters'].items():
            n.call('BindingCommand_RemoveBinding',context={'parameters':[state['parameters'][name]],
                'bindings':[{'target':uid,'name':'deform'} for uid in spec['targets']]})
    for name,spec in specs.items():
        axes=spec['axes'];lo=[a[0] for a in axes];hi=[a[-1] for a in axes]
        uid=existing[name] if name in existing else created_id(n.call('ParamCommand_Add2DParameter',min=-1,max=1))
        state['parameters'][name]=uid
        write_json(run/'native-state.json',state)
        n.call('ParamPropCommand_SetParameterName',newName=name,context={'parameters':[uid]})
        n.call('ParamPropCommand_ApplyParameterPropsAxes',min=lo,max=hi,axisX=((np.asarray(axes[0])-lo[0])/(hi[0]-lo[0])).tolist(),axisY=((np.asarray(axes[1])-lo[1])/(hi[1]-lo[1])).tolist(),context={'parameters':[uid]})
    for op in sorted(ops,key=lambda o:not np.any(o['values'])):
        n.call('ModelCommand_SetDeformBinding',bindingName='deform',values=op['values'],context={'parameters':[state['parameters'][op['parameter']]],'nodes':[op['target']],'parameterValue':op['key']})
    for eye in evidence.get('eyes',[]):
        sclera=eye['part_groups']['sclera'][0]
        for iris in eye['part_groups'].get('iris',[]):
            masks=n.read(iris)['item']['data'].get('masks',[])
            if not any(m['source']==sclera and m['mode']=='Mask' for m in masks):n.call('NodeMaskCommand_AddMask',maskSrc=sclera,mode='Mask',context={'nodes':[iris]})
    for op in face_order['operations']:
        n.call('Inspector_Apply_ZSort',value=op['relative_zsort'],context={'nodes':[op['target']]})
    # Mouth clipping is inherited from the PSD. Adding a second alpha mask
    # multiplies its antialiased edges and changes the supplied neutral art.
    # Unmasked interiors close with the shared aperture field instead.
    n.call('ViewportCommand_ResetParameters');n.save(state['output'])
    for op in face_order['operations']:
        if abs(n.read(op['target'])['item']['data']['zsort']-op['relative_zsort'])>.0001:
            raise ValueError('Static facial draw order did not survive save/readback')
    verified=0
    for name,spec in specs.items():
        for uid in spec['targets']:
            pid=state['parameters'][name]
            b=n.invoke(['resources','read',f'resource://nijigenerate/bindings/get?parameter={pid}&target={uid}&name=deform'])
            expected=[o for o in ops if o['parameter']==name and o['target']==uid]
            if not any(np.any(o['values']) for o in expected):continue
            b=b['item']
            if b['axisValues']!=spec['axes']:raise ValueError('Shape control axis readback differs')
            for op in expected:
                i,j=[a.index(v) for a,v in zip(spec['axes'],op['key'])]
                if not b['data']['isSet'][i][j] or np.max(abs(np.asarray(b['data']['values'][i][j]).ravel()-op['values']))>.0003:raise ValueError('Shape control key readback differs')
                verified+=1
    write_json(run/'shape-controls-program.json',report)
    (run/'shape-controls-pending.json').unlink()
    state['control_specs']=specs;state['shape_controls_sha256']=report['content_sha256']
    write_json(run/'native-state.json',state)
    write_json(run/'shape-controls-readback.json',{'passed':True,'verified_keys':verified,'program_sha256':report['content_sha256']})
    print('Saved and read back PSD-shape controls:',len(specs),'parameters',verified,'keys',flush=True)
