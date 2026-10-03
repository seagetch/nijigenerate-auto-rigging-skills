"""Bake face angles from fixed depth with NJC; never author 2D angle offsets."""
import argparse
from pathlib import Path
import numpy as np
from riglib.data import read_json,write_json,json_digest,digest
from riglib.live import Live
from riglib.reference_fields import DEPTH_ANGLE_PARAMETERS
from build_native import require_single_rig,wait_for_baked_key,apply_registered_fields


def angle_bindings(n):
    result=[]
    parameter_ids={p['uuid'] for p in n.find('Parameter')['items'] if p['name'] in DEPTH_ANGLE_PARAMETERS}
    for r in n.binding_resources():
        if not any(f'parameter={uid}&' in r['uri'] for uid in parameter_ids):continue
        b=n.invoke(['resources','read',r['uri']])['item']
        if b['parameter']['name'] in DEPTH_ANGLE_PARAMETERS:result.append(b)
    return result


def fixed_inputs(n,state):
    # Hash public NJC static inputs, not the INX file or evaluated pose state.
    n.call('ViewportCommand_ResetParameters')
    ids=[state['rig_root'],*state['bones'].values(),*state['grids'].values()]
    return {str(uid):n.read(uid)['item']['data'] for uid in ids}


def head_projection_checks(program,state,bindings):
    """One affine XYZ projection per pose across every single-Head surface.

    This detects angle-specific vertex fitting even if a stored output manifest
    was changed to match. It does not optimize depth or modify a single vertex.
    """
    heads=[d for d in program['domains'] if d['bone_sources']==['Head']]
    lookup={(b['target']['uuid'],b['parameter']['name']):b for b in bindings if b['name']=='deform'}
    xy=np.concatenate([np.array([[x,y] for y in d['axis_y'] for x in d['axis_x']]) for d in heads])
    z=np.concatenate([np.asarray(d['depths'])*program['native_depth_scale'] for d in heads])
    design=np.c_[xy,z,np.ones(len(xy))];checks=[]
    for parameter in DEPTH_ANGLE_PARAMETERS:
        for i in range(5):
            for j in range(5 if parameter.endswith('Yaw-Pitch') else 1):
                off=np.concatenate([np.asarray(lookup[state['grids'][d['id']],parameter]['data']['values'][i][j]).reshape(-1,2) for d in heads])
                matrix=np.linalg.lstsq(design,xy+off,rcond=None)[0]
                error=float(np.max(abs(design@matrix-(xy+off))))
                if error>.003:raise ValueError('Face angle contains a non-depth displacement: '+parameter+' '+str((i,j,error)))
                checks.append({'parameter':parameter,'key':[i,j],'maximum_affine_xyz_residual_model':error,
                               'projection_matrix':matrix.tolist(),'head_surface_count':len(heads)})
    return checks


def check_bindings(state,bindings,part_bindings=()):
    bones=set(state['bones'].values());grids=set(state['grids'].values())
    for b in bindings:
        uid=b['target']['uuid']
        if (uid,b['parameter']['name']) in part_bindings and b['name']=='deform':continue
        if uid not in bones and (uid not in grids or b['name']!='deform'):
            raise ValueError('Unaccounted face angle binding on artwork: '+str(b['target']))
        if b['name']=='deform' and uid not in grids:
            raise ValueError('Part-level face angle deformation is forbidden')
        if not np.asarray(b['data']['isSet']).all():raise ValueError('Incomplete native angle keys')
    for parameter in DEPTH_ANGLE_PARAMETERS:
        found={b['target']['uuid'] for b in bindings if b['parameter']['name']==parameter and b['name']=='deform' and b['target']['uuid'] in grids}
        if found!=grids:raise ValueError('Native angle bake did not cover all carriers')


def bake(run,njc,*,save=True):
    run=Path(run);p=read_json(run/'program.json');state=read_json(run/'native-state.json')
    for name in DEPTH_ANGLE_PARAMETERS:
        spec=next(s for s in p['parameters'] if s['name']==name)
        if spec['deformation_authority']!='native_depth_projection':raise ValueError('Wrong face angle authority')
    if any(name in d['reference_deformations'] for d in p['domains'] for name in DEPTH_ANGLE_PARAMETERS):
        raise ValueError('Compiled face angle residuals must not exist')
    n=Live(njc,run/'depth-angle-journal');reader=Live(njc)
    n.call('ToolCommand_ModelEditMode');n.call('ViewportCommand_ResetParameters')
    require_single_rig(n,state['rig_root'],state['bones'].values())
    existing=angle_bindings(reader)
    grids=set(state['grids'].values());bones=set(state['bones'].values())
    if any(b['target']['uuid'] not in bones and
           (b['target']['uuid'] not in grids or b['name']!='deform') for b in existing):
        raise ValueError('Grid bake must precede separate Part angle corrections')
    # NJC may have auto-refreshed native Grid keys while installing bone
    # drivers. Remove those bindings through the public API before the explicit
    # bake; never let an already-set key count as proof of a new writeback.
    removals=[]
    for parameter in DEPTH_ANGLE_PARAMETERS:
        descriptors=[{'target':b['target']['uuid'],'name':'deform'} for b in existing
                     if b['parameter']['name']==parameter and b['target']['uuid'] in grids]
        if descriptors:removals.append({'parameters':[state['parameters'][parameter]],'bindings':descriptors})
    for context in removals:n.preflight_call('BindingCommand_RemoveBinding',context=context)
    for context in removals:n.call('BindingCommand_RemoveBinding',context=context)
    before=fixed_inputs(n,state)
    for parameter in DEPTH_ANGLE_PARAMETERS:
        uid=state['parameters'][parameter]
        for x in [-1,-.5,0,.5,1]:
            for y in ([-1,-.5,0,.5,1] if parameter.endswith('Yaw-Pitch') else [0]):
                n.call('ViewportCommand_ResetParameters')
                n.call('ParameditCommand_SetArmedParameterAndKeypoint',context={'armedParameters':[uid],'parameterValue':[x,y]})
                n.call('DepthBoneCommand_ApplyDepthBoneDeform',root=state['rig_root'],targets='',context={'armedParameters':[uid]})
                wait_for_baked_key(reader,uid,state['grids'].values(),[x,y])
                print('Native depth angle',parameter,x,y,flush=True)
    n.call('ToolCommand_ModelEditMode');n.call('ViewportCommand_ResetParameters')
    after=fixed_inputs(n,state)
    if json_digest(before)!=json_digest(after):raise ValueError('Native bake changed fixed depth or rig inputs')
    apply_registered_fields(n,p,state)
    bindings=angle_bindings(reader);check_bindings(state,bindings)
    checks=head_projection_checks(p,state,bindings)
    result={'program_sha256':p['content_sha256'],'generator_sha256':digest(Path(__file__)),
            'method':'Grid angle keys: NJC DepthBoneCommand_ApplyDepthBoneDeform only; Part residuals are applied separately afterward',
            'fixed_public_inputs_sha256':json_digest(before),'fixed_inputs_unchanged':True,
            'bindings':bindings,'head_projection_checks':checks,'part_angle_binding_count_at_grid_bake':0,
            'preexisting_grid_bindings_replaced':sum(len(c['bindings']) for c in removals)}
    result['content_sha256']=json_digest(result);write_json(run/'depth-angle-program.json',result)
    state['depth_angle_program_sha256']=result['content_sha256'];write_json(run/'native-state.json',state)
    if save:n.save(state['output'])
    print(('Saved' if save else 'Generated')+' depth-only face angles; affine XYZ residual',max(c['maximum_affine_xyz_residual_model'] for c in checks),flush=True)


def validate(run,n,available):
    run=Path(run);p=read_json(run/'program.json');state=read_json(run/'native-state.json')
    expected=read_json(run/'depth-angle-program.json')
    signed=dict(expected);sig=signed.pop('content_sha256')
    if json_digest(signed)!=sig or sig!=state['depth_angle_program_sha256'] or expected['program_sha256']!=p['content_sha256']:
        raise ValueError('Native depth angle evidence mismatch')
    actual=[b for b in available.values() if b['parameter']['name'] in DEPTH_ANGLE_PARAMETERS]
    materials=read_json(run/'reference-material-program.json') if 'reference_material_program_sha256' in state else {'operations':[]}
    part_bindings={(op['part'],op['parameter_name']) for op in materials['operations'] if op['parameter_name'] in DEPTH_ANGLE_PARAMETERS}
    check_bindings(state,actual,part_bindings)
    lookup={(b['target']['uuid'],b['parameter']['name'],b['name']):b for b in actual}
    maximum=0.;keys=0
    for b in expected['bindings']:
        a=lookup[b['target']['uuid'],b['parameter']['name'],b['name']]
        if a['axisValues']!=b['axisValues']:raise ValueError('Native depth angle axes changed')
        error=float(np.max(abs(np.asarray(a['data']['values'])-np.asarray(b['data']['values']))))
        if error>.0003:raise ValueError('Saved angle differs from native depth bake')
        maximum=max(maximum,error)
        if b['name']=='deform':keys+=int(np.asarray(b['data']['isSet']).sum())
    if json_digest(fixed_inputs(n,state))!=expected['fixed_public_inputs_sha256']:
        raise ValueError('Saved fixed depth or rig differs from native bake inputs')
    checks=head_projection_checks(p,state,actual)
    return {'passed':True,'native_surface_keys_verified':keys,'maximum_saved_error':maximum,
            'separate_part_angle_binding_count':len(part_bindings),'fixed_inputs_unchanged':True,
            'maximum_affine_xyz_residual_model':max(c['maximum_affine_xyz_residual_model'] for c in checks)}


def resample_depth(run,njc):
    """Re-evaluate calibrated depth at existing grid vertices, then native bake.

    This removes obsolete per-vertex fit offsets for every generated carrier.
    It retains the measured semantic charts, grid topology, and bone drivers.
    """
    import copy
    from riglib.resampling import calibrated_depth
    from riglib.carrier import to_root
    from riglib.reference_fields import sample
    run=Path(run).resolve();p=read_json(run/'program.json');state=read_json(run/'native-state.json')
    template=read_json(Path(__file__).resolve().parents[1]/'structures/reference-humanoid.registered.json')
    evidence=read_json(run/'evidence.json');signed=dict(template);signature=signed.pop('content_sha256')
    if json_digest(signed)!=signature:raise ValueError('Template signature mismatch')
    if state['program_sha256']!=p['content_sha256']:raise ValueError('Live state does not match generated program')
    out=run/'depth-resampling-repair';out.mkdir(exist_ok=True)
    revised=copy.deepcopy(p);scale=p['native_depth_scale'];changes=[]
    for d in revised['domains']:
        c=template['components'][d['reference_component']]
        xy=np.array([[x,y] for y in d['axis_y'] for x in d['axis_x']])
        root=to_root(xy,d['carrier_frame'])
        values=calibrated_depth(template,d['reference_component'],d['registration_frame'],root,d['resampling']['unit_model'])
        values+=template['bone_z'][c['depth']['origin']]*p['reference_template']['torso_length']
        changes.append({'domain':d['id'],'maximum_removed_fit_offset_model':float(np.max(abs(values-np.asarray(d['depth_model_units']))))})
        d['depth_model_units']=values.tolist();d.pop('placement_offset_model_units',None)
        d['resampling']['value_authority']='direct evaluation after semantic calibration'
    domains={d['id']:d for d in revised['domains']};order=[]
    for constraint in evidence.get('depth_order_constraints',[]):
        front=domains[constraint['front']];back=domains[constraint['back']];q=constraint['xy_model']
        zf=sample(front['axis_x'],front['axis_y'],front['depth_model_units'],q)[:,0]
        zb=sample(back['axis_x'],back['axis_y'],back['depth_model_units'],q)[:,0]
        gap=domains[constraint['back']]['resampling']['unit_model']*.001
        shift=max(0.,float(np.max(zb-zf))+gap)
        front['depth_model_units']=(np.asarray(front['depth_model_units'])+shift).tolist()
        front['placement_offset_model_units']=shift
        order.append({'front':front['id'],'back':back['id'],'plane_offset_model_units':shift,
                      'minimum_after':float(np.min(zf+shift-zb)),'relief_changed':False})
    for d in revised['domains']:d['depths']=np.round(np.asarray(d['depth_model_units'])/scale,6).tolist()
    revised['reference_template'].update(sha256=signature,depth_order_fit=order)
    revised['depth_sampling_revision']={
        'sampler_sha256':digest(Path(__file__).parent/'riglib/resampling.py'),
        'method':'unchanged semantic calibration; direct depth samples; no vertex-depth optimization'}
    revised.pop('content_sha256');revised['content_sha256']=json_digest(revised)
    n=Live(njc,out/'journal');require_single_rig(n,state['rig_root'],state['bones'].values())
    n.call('ToolCommand_ModelEditMode');n.call('ViewportCommand_ResetParameters')
    def bindings():
        result={}
        for row in n.binding_resources():
            b=n.invoke(['resources','read',row['uri']])['item']
            result[b['parameter']['uuid'],b['target']['uuid'],b['name']]=b
        return result
    before=bindings();grids=set(state['grids'].values())
    allowed={(state['parameters'][name],uid,'deform') for name in DEPTH_ANGLE_PARAMETERS for uid in grids}
    protected={str(k):v for k,v in before.items() if k not in allowed}
    old_static=fixed_inputs(n,state)
    for d in p['domains']:
        live=old_static[str(state['grids'][d['id']])]
        if not np.allclose(live['depths'],d['depths'],atol=1e-7,rtol=0):raise ValueError('Depth changed outside recorded program')
    for d in revised['domains']:n.preflight_call('DepthMapCommand_SetDepths',target=state['grids'][d['id']],depths=d['depths'])
    write_json(out/'before-program.json',p);write_json(out/'before-state.json',state)
    write_json(out/'before-bindings.json',list(before.values()))
    write_json(out/'before-static.json',old_static)
    for d in revised['domains']:
        n.call('DepthMapCommand_SetDepths',target=state['grids'][d['id']],depths=d['depths'])
    state['program_sha256']=revised['content_sha256']
    write_json(run/'program.json',revised);write_json(run/'native-state.json',state)
    bake(run,njc,save=False)
    complete_depth_resample(run,njc)


def complete_depth_resample(run,njc):
    """Verify a depth generation; snapshots are comparison evidence only."""
    run=Path(run).resolve();out=run/'depth-resampling-repair'
    p=read_json(out/'before-program.json');revised=read_json(run/'program.json')
    state=read_json(run/'native-state.json');old_static=read_json(out/'before-static.json')
    n=Live(njc,out/'completion-journal');require_single_rig(n,state['rig_root'],state['bones'].values())
    def bindings():
        values={}
        for row in n.binding_resources():
            b=n.invoke(['resources','read',row['uri']])['item']
            values[b['parameter']['uuid'],b['target']['uuid'],b['name']]=b
        return values
    before={(b['parameter']['uuid'],b['target']['uuid'],b['name']):b for b in read_json(out/'before-bindings.json')}
    grids=set(state['grids'].values())
    generated_names=set(DEPTH_ANGLE_PARAMETERS)|{s['name'] for s in revised['parameters']
                         if s.get('deformation_authority')=='registered_reference_fields'}
    allowed={(state['parameters'][name],uid,'deform') for name in generated_names for uid in grids}
    protected={k:v for k,v in before.items() if k not in allowed};after=bindings()
    if {k for k in after if k not in allowed}!=set(protected):
        raise ValueError('Unexpected binding topology change outside generated fields')
    if json_digest({str(k):after[k] for k in protected})!=json_digest({str(k):v for k,v in protected.items()}):
        raise ValueError('Unowned bindings changed; do not save')
    actual=fixed_inputs(n,state);maximum=0.
    for d in revised['domains']:
        uid=str(state['grids'][d['id']]);node=actual[uid];old=old_static[uid]
        maximum=max(maximum,float(np.max(abs(np.asarray(node['depths'])-d['depths']))))
        if {k:v for k,v in node.items() if k!='depths'}!={k:v for k,v in old.items() if k!='depths'}:
            raise ValueError('Non-depth Grid input changed')
    for uid in [state['rig_root'],*state['bones'].values()]:
        if actual[str(uid)]!=old_static[str(uid)]:raise ValueError('Bone/rig input changed')
    if maximum>1e-7:raise ValueError('Calibrated depth readback mismatch')
    baked=read_json(run/'depth-angle-program.json')
    for b in baked['bindings']:
        key=(b['parameter']['uuid'],b['target']['uuid'],b['name'])
        if json_digest(after[key])!=json_digest(b):raise ValueError('Native Face key differs from generated depth projection')
    n.call('ViewportCommand_ResetParameters');n.save(state['output'])
    changes=[{'domain':d['id'],'maximum_depth_change_model':float(np.max(abs(np.asarray(d['depth_model_units'])-np.asarray(old['depth_model_units']))))}
             for d,old in zip(revised['domains'],p['domains'])]
    report={'source_program_sha256':p['content_sha256'],'program_sha256':revised['content_sha256'],
            'changes':changes,'depth_order':revised['reference_template']['depth_order_fit'],
            'maximum_depth_readback_error':maximum,'protected_bindings_unchanged':True,
            'protected_binding_count':len(protected),'body_authority':'absolute compiled fields, reapplied after every native bake',
            'calibration_unchanged':True,'grid_axes_unchanged':True,'saved':True,'rig_complete':False,
            'repair_code_sha256':digest(Path(__file__))}
    write_json(out/'result.json',report)
    print('Saved direct calibrated depth for',len(changes),'Grids; protected bindings unchanged:',len(protected),flush=True)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--run',required=True);a.add_argument('--njc',required=True)
    a.add_argument('--resample-depth',action='store_true')
    args=a.parse_args()
    if args.resample_depth:resample_depth(args.run,args.njc)
    else:bake(args.run,args.njc)
