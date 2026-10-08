"""Real-model authored-key, protected-body and time-based physics verification."""
import argparse
import time
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from riglib.data import read_json,write_json,json_digest
from riglib.live import Live


def set_value(n,pid,value):
    n.call('ParameditCommand_SetParameterKeypoint',context={'parameters':[pid],'parameterValue':list(value)})


def capture(n,path,targets=()):
    """Wait for an evaluated overlay to converge, then save an engine render."""
    overlays=[{'uuid':u,'overlay':'mesh'} for u in targets]
    last=None;meta=None
    for _ in range(8):
        n.call('ViewCommand_CaptureLiveScreenshot',overlayObjects=overlays)
        meta=n.last_envelope['result'].get('_meta',{})
        current=meta.get('overlayMappings',[])
        if current and last is not None and json_digest(current)==json_digest(last):break
        last=current
    else:
        if targets:raise ValueError('Authored pose did not converge')
    path=Path(path).resolve();path.parent.mkdir(parents=True,exist_ok=True)
    n.call('ViewCommand_SaveScreenshot',filename=str(path))
    with Image.open(path) as image:
        image.verify()
    return meta


def render_keys(n,groups,identities,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    n.call('ViewportCommand_FitViewportToModel');n.call('ViewportCommand_ResetParameters')
    capture(n,out/'physics-key-neutral-before.png')
    for index,g in enumerate(groups):
        pid=identities[g['id']]['parameter'];tiles=[]
        for y in (-1,0,1):
            for x in (-1,0,1):
                set_value(n,pid,(x,y));path=out/f'physics-key-{index:02d}-{x}-{y}.png'
                capture(n,path,g['targets']);tiles.append((path,(x,y)))
        set_value(n,pid,(0,0))
        neutral=np.asarray(Image.open(out/'physics-key-neutral-before.png').convert('RGBA'))
        boxes=[]
        for path,key in tiles:
            current=np.asarray(Image.open(path).convert('RGBA'))
            changed=np.max(abs(current.astype(int)-neutral.astype(int)),axis=2)>2
            yy,xx=np.nonzero(changed)
            if len(xx):boxes.append((xx.min(),yy.min(),xx.max()+1,yy.max()+1))
        crop=None
        if boxes:
            b=np.asarray(boxes);crop=(max(0,int(b[:,0].min())-24),max(0,int(b[:,1].min())-24),
                                     min(neutral.shape[1],int(b[:,2].max())+24),min(neutral.shape[0],int(b[:,3].max())+24))
        sheet=Image.new('RGB',(900,1080),'#303030');draw=ImageDraw.Draw(sheet)
        for k,(path,key) in enumerate(tiles):
            im=Image.open(path).convert('RGBA')
            if crop:im=im.crop(crop)
            scale=min(300/im.width,330/im.height)
            im=im.resize((max(1,round(im.width*scale)),max(1,round(im.height*scale))),Image.Resampling.LANCZOS)
            xx=k%3*300;yy=k//3*360;sheet.paste(im,(xx+(300-im.width)//2,yy),im)
            draw.text((xx+4,yy+334),str(key),fill='white')
        sheet.save(out/f'physics-key-{index:02d}-sheet.png')
        print('Verified authored keys',index+1,g['name'],flush=True)
    n.call('ViewportCommand_ResetParameters');capture(n,out/'physics-key-neutral-after.png')
    a=np.asarray(Image.open(out/'physics-key-neutral-before.png'));b=np.asarray(Image.open(out/'physics-key-neutral-after.png'))
    if a.shape!=b.shape or not np.array_equal(a,b):raise ValueError('Physics authored keys did not restore neutral pixels')
    write_json(out/'physics-key-verification.json',{'groups':len(groups),'nine_keys_per_group':True,'neutral_pixels_equal':True,
                                      'visual_review_required':True})


def mapping(n,targets):
    n.call('ViewCommand_CaptureLiveScreenshot',overlayObjects=[{'uuid':u,'overlay':'mesh'} for u in targets])
    meta=n.last_envelope['result'].get('_meta',{})
    rows={int(r['uuid']):np.asarray([p['image'] for p in r['points']],float) for r in meta.get('overlayMappings',[])}
    if set(rows)!=set(targets):raise ValueError('Capture omitted requested verification mesh')
    return rows


def verify(run,njc,out=None,overlay=False):
    from apply_physics import pause,verify_keys,bindings,census
    run=Path(run).resolve();dest=Path(out).resolve() if out else run
    report=read_json(dest/'physics-applied.json')
    if report.get('status')=='no_supported_group':
        result={'passed':True,'status':'no_supported_group','unresolved':report['unresolved'],'rig_complete':False}
        write_json(dest/'physics-verification.json',result);return result
    plan=read_json(dest/'physics-program.json');state=read_json(run/'native-state.json')
    structure=read_json(dest/'physics-structure.json');n=Live(njc,dest/'physics-verification-journal')
    owned={v['parameter'] for v in report['identities'].values()}
    try:
        pause(n,next(iter(owned)));n.call('ViewportCommand_ResetParameters')
        outdir=dest;outdir.mkdir(exist_ok=True)
        # Procedural render surfaces are evaluated only after the loaded model is
        # drawn. Snapshot every node after neutral rendering, not during loading.
        capture(n,outdir/'physics-runtime-startup-neutral.png')
        before=bindings(n)
        nodes_before,parents=census(n);solver_checks=[]
        setting_fields={'Gravity':'gravity','Length':'length','Frequency':'frequency',
                        'AngleDamping':'angle_damping','LengthDamping':'length_damping'}
        for g in plan['groups']:
            identity=report['identities'][g['id']];sid=identity['simple_physics'];data=nodes_before[sid]
            if (parents[sid]!=state['bones'][g['parent_bone']] or data['param']!=identity['parameter']
                    or data['model_type']!='SpringPendulum' or data['map_mode']!='XY' or data['local_only']):
                raise ValueError('Saved physics ownership or solver mode differs')
            for requested,field in setting_fields.items():
                expected=identity['settings'][requested]
                tolerance=max(1e-4,float(np.spacing(np.float32(abs(expected))))*2)
                if not np.isclose(data[field],expected,rtol=0,atol=tolerance):
                    raise ValueError('Saved physics setting differs: '+field)
            if not np.allclose(data['output_scale'],plan['policy']['settings']['output_scale'],rtol=0,atol=1e-4):
                raise ValueError('Saved physics output scale differs')
            solver_checks.append({'group':g['id'],'solver':sid,'saved_settings_verified':True,'parent_verified':True})
        pause(n,next(iter(owned)));n.call('ViewportCommand_ResetParameters')
        body=[r['target'] for r in structure['inventory'] if r['decision']=='exclude' and ('Human body' in r['reason'])]
        moving=sorted({u for g in plan['groups'] for u in g['targets']});targets=body+moving
        baseline=mapping(n,targets);checks=[];outdir=dest;outdir.mkdir(exist_ok=True)
        capture(n,outdir/'physics-runtime-neutral.png',targets)
        for g in plan['groups']:
            pid=report['identities'][g['id']]['parameter']
            # NJC keypoint context accepts only existing axis keys. Do not add
            # artificial midpoint keys just to make a verification command work.
            for key in ((-1,0),(0,1),(-1,-1),(1,1)):
                set_value(n,pid,key);observed=mapping(n,targets)
                errors=[float(np.max(np.linalg.norm(observed[u]-baseline[u],axis=1))) for u in body]
                if max(errors,default=0)>.05:raise ValueError('Secondary motion moved an anatomical Part')
                checks.append({'group':g['id'],'key':list(key),'max_body_pixel_error':max(errors,default=0)})
            set_value(n,pid,(0,0))
        # Composite pose baseline: only the added Physics input differs, so body
        # motion caused by its own authored pose is not mistaken for secondary sway.
        for name,value in [('Body::Yaw-Pitch',[.5,-.5]),('Face::Yaw-Pitch',[-.5,.5])]:
            if name in state['parameters']:set_value(n,state['parameters'][name],value)
        compound=mapping(n,targets)
        for pid in owned:set_value(n,pid,(1,1))
        observed=mapping(n,targets)
        error=max((float(np.linalg.norm(observed[u]-compound[u],axis=1).max()) for u in body),default=0)
        if error>.05:raise ValueError('Compound physics pose moved anatomy')
        capture(n,outdir/'physics-runtime-compound.png',targets)
        n.call('ViewportCommand_ResetParameters')
        # Explicit arm established a disabled state. Toggle once to enable; reset
        # is separate from pause. Playback uses measured time rather than a claim of
        # fixed-timestep determinism.
        pause(n,next(iter(owned)));n.call('ViewportCommand_TogglePhysics');n.call('ViewportCommand_ResetPhysics')
        driver=state['parameters'].get('Body::Roll')
        if driver is None:raise ValueError('No authored Body::Roll playback driver')
        set_value(n,driver,(.5,));time.sleep(.3);set_value(n,driver,(0,))
        start=time.perf_counter();samples=[]
        while time.perf_counter()-start<6:
            rows=mapping(n,moving)
            samples.append({'seconds':time.perf_counter()-start,'max_px':{
                str(u):float(np.linalg.norm(rows[u]-baseline[u],axis=1).max()) for u in moving}})
            if len(samples) in (1,5,10):
                path=(outdir/f'physics-runtime-playback-{len(samples):02d}.png').resolve()
                n.call('ViewCommand_SaveScreenshot',filename=str(path))
                with Image.open(path) as image:image.verify()
        if not samples or not all(np.isfinite(v) for r in samples for v in r['max_px'].values()):raise ValueError('Invalid physics playback')
        peaks={str(u):max(r['max_px'][str(u)] for r in samples) for u in moving}
        if max(peaks.values())<=.05:raise ValueError('No visible physics response')
        pause(n,next(iter(owned)));n.call('ViewportCommand_ResetPhysics');n.call('ViewportCommand_ResetParameters')
        reset=mapping(n,targets)
        reset_error=max(float(np.linalg.norm(reset[u]-baseline[u],axis=1).max()) for u in targets)
        if reset_error>.05:raise ValueError('Physics reset did not restore neutral geometry')
        capture(n,outdir/'physics-runtime-reset.png',targets)
        after=bindings(n)
        if json_digest(list(before.values()))!=json_digest(list(after.values())):raise ValueError('Verification changed authored bindings')
        nodes_after,_=census(n)
        runtime_equal=nodes_before==nodes_after;generated_updates=[]
        differences={str(u):{'before':nodes_before.get(u),'after':nodes_after.get(u)}
                     for u in set(nodes_before)|set(nodes_after) if nodes_before.get(u)!=nodes_after.get(u)}
        if differences:
            write_json(dest/'physics-node-state-differences.json',differences)
            for uid,row in differences.items():
                a,b=row['before'],row['after']
                # Auto-resized DynamicComposite meshes are generated render bounds,
                # not authored Part deformation. Never exempt a name or UUID.
                if not (a and b and a.get('type')=='DynamicComposite' and a.get('auto_resized') is True
                        and b.get('auto_resized') is True
                        and {k:v for k,v in a.items() if k!='mesh'}=={k:v for k,v in b.items() if k!='mesh'}):
                    raise ValueError('Verification changed authored node state; differences recorded')
                if {k:v for k,v in a['mesh'].items() if k!='verts'}!={k:v for k,v in b['mesh'].items() if k!='verts'}:
                    raise ValueError('Generated surface topology changed')
                if not np.isfinite(b['mesh']['verts']).all():raise ValueError('Invalid generated surface')
                generated_updates.append({'target':int(uid),'type':'DynamicComposite','auto_resized':True,
                                          'change':'Generated render bounds; raw differences retained'})
        verify_keys(n,plan['groups'],report['identities'])
        capture(n,outdir/'physics-runtime-reset.png',targets)
        result={'passed':True,'solver_checks':solver_checks,'protected_anatomy_checks':checks,'compound_body_error_px':error,
                'playback_samples':samples,'peak_motion_px':peaks,'reset_error_px':reset_error,
                'binding_state_unchanged':True,'authored_node_state_unchanged':True,
                'runtime_nodes_equal':runtime_equal,'generated_surface_updates':generated_updates,
                'final_drivers':'paused by explicit arm',
                'time_basis':'measured wall time; no fixed-timestep guarantee','visual_review_required':True,
                'intermediate_pose_limit':'NJC keypoint context accepts existing axis keys only; arbitrary midpoint capture unavailable',
                'unresolved':report['unresolved'],'rig_complete':False}
        if overlay:
            from overlay_physics import overlay_plan
            from riglib.physics_structure import psd_materials
            from apply_physics import matrices
            assets=psd_materials(run,read_json(run/'evidence.json'))
            overlay_plan(n,plan,assets,dest,nodes_after,matrices(nodes_after,parents))
            result['applied_overlay']='physics-overlay-overview.png'
        write_json(dest/'physics-verification.json',result);return result
    finally:
        pause(n,next(iter(owned)))
        n.call('ViewportCommand_ResetPhysics')
        n.call('ViewportCommand_ResetParameters')



if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--njc',required=True);p.add_argument('--out')
    p.add_argument('--overlay',action='store_true')
    a=p.parse_args();verify(a.run,a.njc,a.out,a.overlay);print('Physics runtime verification passed',flush=True)
