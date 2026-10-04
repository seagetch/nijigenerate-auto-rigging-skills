"""Compile local mechanisms from PSD alpha in declared feature frames."""
from pathlib import Path
import numpy as np
from PIL import Image
from .data import read_json,write_json,json_digest,digest
from .live import Live,created_id
from .model import observe_model
from .face_draw_order import plan as face_order_plan

POLICY={'version':'2.0','closed_height_ratio':.015,'eye_closed_height_ratio':0.,'mouth_open_width_ratio':.20,
        'blink_expression_range':.3,
        'smile_inner_drop_width_ratio':.08,
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
    # A native zero-area triangle has no defined area ratio or orientation.
    # Keep it in the mesh; omit only its undefined ratio from this calculation.
    valid=before!=0
    return after[valid]/before[valid]


def minimum_area_ratio(rest,delta,indices):
    ratios=area_ratios(rest,delta,indices)
    return float(ratios.min()) if ratios.size else None


def preserve_orientation(rest,delta,indices,locked=None):
    """Closest displacement with positive native triangle areas.

    For these local mechanisms the horizontal positions are fixed during the
    solve; each signed triangle area is linear in the vertical coordinates.
    This corrects discretization of curved PSD contours on coarse AutoMesh
    triangles, without changing mesh topology or sampling another model.
    """
    minimum=minimum_area_ratio(rest,delta,indices)
    if minimum is None or minimum>=.002:return delta
    import osqp
    from scipy import sparse
    q=rest+delta;t=np.asarray(indices,int).reshape(-1,3)
    before=np.cross(rest[t[:,1]]-rest[t[:,0]],rest[t[:,2]]-rest[t[:,0]])
    valid=before!=0
    t=t[valid];before=before[valid]
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


def contact_profile(points,basis,origin,width,lower_edge,smooth=True):
    """Measure an alpha edge; optionally fit the painted lash's main curve."""
    p=(points-origin)@basis;axis=np.linspace(-width/2,width/2,65)
    half_step=(axis[1]-axis[0])/2
    values=np.full(len(axis),np.nan)
    for i,u in enumerate(axis):
        section=p[abs(p[:,0]-u)<=half_step,1]
        if len(section):values[i]=section.max() if lower_edge else section.min()
    valid=np.isfinite(values)
    if not valid.any():raise ValueError('No painted lash boundary intersects the eye span')
    if not smooth:return np.interp(axis,axis[valid],values[valid])
    t=axis/(width/2)
    coefficients=np.polynomial.polynomial.polyfit(t[valid],values[valid],min(3,int(valid.sum())-1))
    return np.polynomial.polynomial.polyval(t,coefficients)


def endpoint_cubic(axis,values):
    """Fit one smooth closure curve while retaining both canthus positions."""
    t=(axis-axis[0])/(axis[-1]-axis[0])
    chord=values[0]*(1-t)+values[-1]*t
    basis=np.c_[t*(1-t),t*(1-t)*(2*t-1)]
    coefficients=np.linalg.lstsq(basis,values-chord,rcond=None)[0]
    return chord+basis@coefficients


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
    from .eyelash_shape import detect,report as lash_report
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
    def mechanism(name,axes,parts,field,detail=None,orientation_solve=True):
        if parameters is not None and name not in parameters:return
        if not parts:return
        specs[name]={'axes':axes,'targets':list(dict.fromkeys(parts)),'source':'PSD_shape_field','neutral':[0.,0.]}
        for uid in specs[name]['targets']:
            rest,world,linear,indices=geometry(uid)
            for x in axes[0]:
                for y in axes[1]:
                    displacement=field(uid,world,x,y)@np.linalg.inv(linear).T
                    if orientation_solve:displacement=preserve_orientation(rest,displacement,indices)
                    if detail is not None:
                        extra=detail(uid,world,x,y)@np.linalg.inv(linear).T
                        locked=np.max(abs(extra),axis=1)<1e-12
                        displacement=preserve_orientation(rest,displacement+extra,indices,locked=locked)
                    displacement=np.round(displacement,5)
                    if not np.isfinite(displacement).all():raise ValueError('Nonfinite local mechanism')
                    ratios=area_ratios(rest,displacement,indices)
                    minimum=float(ratios.min()) if ratios.size else None
                    if orientation_solve and minimum is not None and minimum<=0:raise ValueError(f'Local mechanism folds: {name} {x},{y} {uid} {minimum}')
                    if x==0 and y==0 and np.max(abs(displacement))>1e-8:raise ValueError('Local mechanism changes source neutral')
                    ops.append({'parameter':name,'target':uid,'key':[x,y],'values':displacement.ravel().tolist(),
                                'minimum_area_ratio':minimum,
                                'undefined_area_ratio_triangles':len(np.asarray(indices).reshape(-1,3))-ratios.size})
    for eye in eyes:
        origin,basis,width=feature_frame(eye['canthi_model']);groups={k:list(v) for k,v in eye['part_groups'].items()}
        groups['brow']=sorted(set(groups.get('brow',[]))|shared_brows)
        cloud=source_cloud(capture,groups['sclera'],translation)
        ax,top,bottom=profile(cloud,basis,origin,width);height=float(np.median(bottom-top))
        # The first sclera is also the native Iris clipping source. Its open
        # lower alpha boundary, not the shadow or the aperture midpoint,
        # defines the full down-close reference. The authored expression
        # range blends from its straight endpoint chord toward that reference
        # or the reflected smile arch. Lids and white share the same target.
        white_owner=groups['sclera'][0]
        down_close=contact_profile(source_cloud(capture,[white_owner],translation),basis,origin,width,True,smooth=False)
        flat_close=np.linspace(down_close[0],down_close[-1],len(ax))
        expression_offset=POLICY['blink_expression_range']*(down_close-flat_close)
        smile_close=flat_close-expression_offset
        lashes=detect(capture,groups,origin,basis)
        # The white aperture is not the painted lash boundary. Move the
        # lower edge of the upper stroke and the upper edge of the lower
        # stroke to one shared contact curve. The displacement is constant
        # through each stroke's normal cross-section, preserving thickness.
        upper_contact=top
        lower_contact=bottom
        upper_contact_parts=[]
        upper_contains_lower=False
        if groups.get('upper'):
            # The largest painted upper band within the aperture owns the
            # contact curve. Separate colored tips, wings and lid creases
            # follow it; their decorative extrema must not redefine it.
            upper_clouds={u:source_cloud(capture,[u],translation) for u in groups['upper']}
            scores={u:np.count_nonzero(abs(((q-origin)@basis)[:,0])<=width/2)
                *abs(np.linalg.det(np.asarray(capture[u]['source_to_model'])[:2,:2])) for u,q in upper_clouds.items()}
            owner=max(scores,key=scores.get);upper_contact_parts=[owner]
            painted=upper_clouds[owner];q=(painted-origin)@basis
            middle=np.interp(q[:,0],ax,(top+bottom)/2)
            upper_pixels=q[:,1]<=middle
            upper_contact=contact_profile(painted[upper_pixels],basis,origin,width,True,smooth=False)
            lower_pixels=(~upper_pixels)&(abs(q[:,0])<=width/2)
            # One source Part may contain both eyelids and the connecting side.
            # Detect the lower band by its span across the white aperture.
            upper_contains_lower=bool(np.count_nonzero(lower_pixels)>1 and np.ptp(q[lower_pixels,0])>width*.25)
            if upper_contains_lower:
                lower_contact=contact_profile(painted[lower_pixels],basis,origin,width,False,smooth=False)
        if groups.get('lower'):
            lower_contact=contact_profile(source_cloud(capture,groups['lower'],translation),basis,origin,width,False,smooth=False)
        lookup={uid:role for role,ids in groups.items() for uid in ids}
        # Identify the medial endpoint anatomically, independently of Part
        # names and screen side. Fit one cubic arch, then lower its medial
        # endpoint using the cubic Bezier endpoint basis. This moves the end
        # and its tangent continuously, without a separate inner-half bend.
        references=[np.mean(e['canthi_model'],axis=0) for e in eyes if e is not eye]
        if not references and evidence.get('mouth'):
            references=[np.mean(evidence['mouth']['axis_model'],axis=0)]
        inner_index=None;inner_source='unresolved'
        if references:
            inner_index=int(np.argmin(np.linalg.norm(np.asarray(eye['canthi_model'])-np.mean(references,axis=0),axis=1)))
            inner_source='other_eye_or_mouth_center'
        elif lashes and len(lashes['branches'])==1:
            inner_index=int(lashes['branches'][0]['junction_local'][0]<0)
            inner_source='opposite_detected_outer_side'
        inner_drop=np.zeros(len(ax))
        if inner_index is not None:
            medial=(ax-ax[0])/(ax[-1]-ax[0])
            if not inner_index:medial=1-medial
            inner_drop=width*POLICY['smile_inner_drop_width_ratio']*medial**3
        smile_close=endpoint_cubic(ax,smile_close)+inner_drop
        def blink(uid,world,x,y):
            p=(world-origin)@basis;t=np.clip(p[:,0]/(width/2),-1,1)
            target=flat_close+y*(smile_close-flat_close) if y>0 else flat_close-y*expression_offset
            seam=np.interp(p[:,0],ax,target)
            role=lookup[uid];delta=np.zeros_like(p)
            if role=='sclera':
                remaining=1-x*(1-POLICY['eye_closed_height_ratio'])
                chord=flat_close[0]+(p[:,0]-ax[0])*(flat_close[-1]-flat_close[0])/(ax[-1]-ax[0])
                # A curved locus still encloses finite native triangles even
                # when every vertex lies on it. Let the aperture's curvature
                # vanish with its height: fully closed white is one affine
                # line, so every triangle has zero area. Painted lids retain
                # their shared expression curve and original stroke width.
                center=chord+remaining*(seam-chord)
                delta[:,1]=(1-remaining)*(center-p[:,1])
            elif role=='lower':delta[:,1]=x*(seam-np.interp(p[:,0],ax,lower_contact))
            elif role in ('upper','corner'):
                upper=np.interp(p[:,0],ax,upper_contact)
                lower=np.interp(p[:,0],ax,lower_contact)
                # One piecewise-affine closure field. Above the upper contact
                # and below the lower contact the normal derivative stays 1,
                # preserving both painted bands. Only the connecting side
                # inside the aperture contracts, whether joined or separate.
                inside=np.clip(p[:,1]-upper,0,np.maximum(lower-upper,0))
                delta[:,1]=x*(seam-upper-(1-POLICY['eye_closed_height_ratio'])*inside)
            elif role=='fold':delta[:,1]=x*(seam-np.interp(p[:,0],ax,upper_contact))
            return delta@basis.T
        parts=[uid for role,ids in groups.items() if role not in ('iris','brow') for uid in ids]
        blink_name='Eye::'+eye['side']+'::Blink'
        mechanism(blink_name,[[0.,.25,.5,.75,1.],[-1.,0.,1.]],parts,blink,orientation_solve=False)
        if blink_name in specs:
            specs[blink_name]['shape_analysis']=lash_report(lashes)
            specs[blink_name]['shape_analysis']['upper_part_contains_lower_band']=upper_contains_lower
            specs[blink_name]['shape_analysis']['closure_field']='upper and lower bands preserve normal thickness; the intervening side contracts'
            specs[blink_name]['contact_curves']={'frame_origin':origin.tolist(),'frame_basis':basis.tolist(),
                'tangent':ax.tolist(),'upper_lower_edge':upper_contact.tolist(),'lower_upper_edge':lower_contact.tolist(),
                'upper_parts':upper_contact_parts,'lower_parts':groups.get('lower',[]),
                'target':'shared smile / flat / down-close within authored expression range',
                'white_boundary_owner':white_owner,'neutral_target':flat_close.tolist(),
                'open_sclera_lower_reference':down_close.tolist(),
                'expression_range':POLICY['blink_expression_range'],
                'smile_inner_corner':{'endpoint_index':inner_index,'source':inner_source,
                    'drop_model_units':float(inner_drop.max()),'drop_profile':inner_drop.tolist(),
                    'curve':'single endpoint-constrained cubic with lowered medial endpoint'},
                'expression_targets':{'-1':(flat_close+expression_offset).tolist(),'0':flat_close.tolist(),'1':smile_close.tolist()},
                'expression_meanings':{'-1':'down_close','0':'flat','1':'smile'}}
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


def apply_eyes(run,njc):
    """Replace only owned Blink keys on the already-open saved model."""
    from validate_saved_rig import public_snapshot
    from build_native import require_single_rig
    from .model import observe_metadata
    from .shape_validation import validate as validate_shapes
    run=Path(run).resolve();state=read_json(run/'native-state.json')
    evidence=read_json(run/'evidence.json');capture=read_json(run/'capture.json')
    previous=read_json(run/'shape-controls-program.json')
    if previous['content_sha256']!=state['shape_controls_sha256'] or json_digest({k:v for k,v in previous.items() if k!='content_sha256'})!=previous['content_sha256']:
        raise ValueError('Owned shape control identity mismatch')
    selected={'Eye::'+e['side']+'::Blink' for e in evidence.get('eyes',[])}
    if not selected or not selected<=previous['parameters'].keys():raise ValueError('Existing eye control ownership unavailable')
    n=Live(njc,run/'eye-controls-journal')
    require_single_rig(n,state['rig_root'],state['bones'].values())
    n.call('ToolCommand_ModelEditMode');n.call('ViewportCommand_ResetParameters')
    before,identity=public_snapshot(n)
    observed=observe_metadata(before['nodes'],identity)
    nodes={row['uuid']:row for row in observed['nodes']}
    specs,ops=compile_controls(evidence,capture,nodes,parameters=selected)
    if set(specs)!=selected:raise ValueError('Not every existing eye was compiled')
    for op in ops:n.preflight_call('ModelCommand_SetDeformBinding',bindingName='deform',values=op['values'],
        context={'parameters':[state['parameters'][op['parameter']]],'nodes':[op['target']],'parameterValue':op['key']})
    for name in sorted(selected):
        if specs[name]['axes']!=previous['parameters'][name]['axes']:raise ValueError('Eye-only refresh cannot change parameter axes')
        n.call('BindingCommand_RemoveBinding',context={'parameters':[state['parameters'][name]],
            'bindings':[{'target':uid,'name':'deform'} for uid in previous['parameters'][name]['targets']]})
    for op in sorted(ops,key=lambda o:not np.any(o['values'])):
        n.call('ModelCommand_SetDeformBinding',bindingName='deform',values=op['values'],
            context={'parameters':[state['parameters'][op['parameter']]],'nodes':[op['target']],'parameterValue':op['key']})
    n.call('ViewportCommand_ResetParameters');n.save(state['output'])
    after,_=public_snapshot(n)
    def outside(snapshot):
        return {'nodes':snapshot['nodes'],'bindings':{k:v for k,v in snapshot['bindings'].items()
            if v['parameter']['name'] not in selected}}
    before_hash=json_digest(outside(before));after_hash=json_digest(outside(after))
    if before_hash!=after_hash:raise ValueError('Eye refresh changed state outside the selected Blink bindings')
    bindings={(v['parameter']['name'],v['target']['uuid'],v['name']):v for v in after['bindings'].values()}
    verified=0
    for op in ops:
        b=bindings.get((op['parameter'],op['target'],'deform'))
        if b is None:
            if np.any(op['values']):raise ValueError('Eye binding was not saved')
            continue
        i,j=[next(k for k,v in enumerate(a) if abs(v-q)<1e-6) for a,q in zip(b['axisValues'],op['key'])]
        if not b['data']['isSet'][i][j] or np.max(abs(np.asarray(b['data']['values'][i][j]).ravel()-op['values']))>.0003:
            raise ValueError('Saved eye key differs from the generated value')
        verified+=1
    report={k:v for k,v in previous.items() if k!='content_sha256'}
    report['parameters']={**previous['parameters'],**specs}
    report['operations']=[op for op in previous['operations'] if op['parameter'] not in selected]+ops
    report['eye_generation']={'policy':POLICY,'generator_sha256':digest(Path(__file__)),
        'eyelash_shape_sha256':digest(Path(__file__).with_name('eyelash_shape.py')),
        'scope':sorted(selected),'outside_blink_state_sha256':after_hash}
    report['content_sha256']=json_digest(report)
    write_json(run/'shape-controls-program.json',report)
    state['shape_controls_sha256']=report['content_sha256'];state['control_specs']=report['parameters']
    write_json(run/'native-state.json',state)
    findings=validate_shapes(run,state,after);write_json(run/'shape-readback.json',findings)
    write_json(run/'shape-controls-readback.json',{'passed':True,'verified_keys':findings['verified_keys'],
        'program_sha256':report['content_sha256'],'scope':'current saved keys; non-Blink model state preserved'})
    write_json(run/'eye-controls-readback.json',{'selected_parameters':sorted(selected),'verified_eye_keys':verified,
        'other_model_state_unchanged':True,'before_outside_blink_sha256':before_hash,'after_outside_blink_sha256':after_hash,
        'numerical_findings':findings['findings'],'program_sha256':report['content_sha256']})
    print('Saved eyes only:',len(selected),'parameters,',verified,'keys; all other model state unchanged',flush=True)
