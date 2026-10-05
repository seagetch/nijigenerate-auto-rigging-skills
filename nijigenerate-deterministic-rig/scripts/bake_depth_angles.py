"""Bake face angles from fixed depth with NJC; never author 2D angle offsets."""
import argparse
import time
from pathlib import Path
import numpy as np
from riglib.data import read_json,write_json,json_digest,digest
from riglib.live import Live
from riglib.reference_fields import DEPTH_ANGLE_PARAMETERS
from riglib.carrier import to_root,to_local,rotation
from build_native import require_single_rig,wait_for_baked_key,apply_registered_fields
def grid_ids(state):return [*state['grids'].values(),*state.get('child_grids',[])]


def angle_bindings(n):
    result=[]
    parameter_ids={p['uuid'] for p in n.find('Parameter')['items'] if p['name'] in DEPTH_ANGLE_PARAMETERS}
    rows=[r for r in n.binding_resources() if any(f'parameter={uid}&' in r['uri'] for uid in parameter_ids)]
    for response in n.read_resources([r['uri'] for r in rows]):
        b=response['item']
        if b['parameter']['name'] in DEPTH_ANGLE_PARAMETERS:result.append(b)
    return result


def settle_native_keys(n,state,save):
    """Wait for native queued ancestor refreshes; never rewrite key values."""
    previous=angle_bindings(n);observations=[];stable=0;deadline=time.monotonic()+300
    while stable<2:
        if save:n.save(state['output'])
        current=angle_bindings(n)
        before={(b['target']['uuid'],b['parameter']['name'],b['name']):b for b in previous}
        changed=[{'target':b['target'],'parameter':b['parameter'],'binding':b['name']}
                 for b in current if json_digest(b)!=json_digest(before.get((b['target']['uuid'],b['parameter']['name'],b['name'])))]
        observations.append({'native_bindings_changed':changed,'save_performed':save})
        stable=stable+1 if not changed else 0
        previous=current
        if time.monotonic()>deadline:raise RuntimeError('Native depth refresh did not become stable; model was not reopened')
    return current,observations


def fixed_inputs(n,state):
    # Hash public NJC static inputs, not the INX file or evaluated pose state.
    n.call('ViewportCommand_ResetParameters')
    ids=[state['rig_root'],*state['bones'].values(),*grid_ids(state),*state['groups'].values()]
    return {str(uid):r['item']['data'] for uid,r in zip(ids,n.read_many(ids))}


def head_projection_checks(program,state,bindings):
    """One affine XYZ projection per pose across every single-Head surface.

    This detects angle-specific vertex fitting even if a stored output manifest
    was changed to match. It does not optimize depth or modify a single vertex.
    """
    heads=[d for d in program['domains'] if d['bone_sources']==['Head']]
    lookup={(b['target']['uuid'],b['parameter']['name']):b for b in bindings if b['name']=='deform'}
    xy=np.concatenate([to_root(np.array([[x,y] for y in d['axis_y'] for x in d['axis_x']]),d['carrier_frame']) for d in heads])
    z=np.concatenate([np.asarray(d['depths'])*program['native_depth_scale'] for d in heads])
    design=np.c_[xy,z,np.ones(len(xy))];checks=[]
    for parameter in DEPTH_ANGLE_PARAMETERS:
        for i in range(5):
            for j in range(5 if parameter.endswith('Yaw-Pitch') else 1):
                off=np.concatenate([np.asarray(lookup[state['grids'][d['id']],parameter]['data']['values'][i][j]).reshape(-1,2)@rotation(d['carrier_frame']['rotation']).T for d in heads])
                matrix=np.linalg.lstsq(design,xy+off,rcond=None)[0]
                error=float(np.max(abs(design@matrix-(xy+off))))
                checks.append({'parameter':parameter,'key':[i,j],'maximum_affine_xyz_residual_model':error,
                               'inspection_note':'affine projection comparison differs' if error>.003 else None,
                               'projection_matrix':matrix.tolist(),'head_surface_count':len(heads)})
    return checks


def head_drive_observation(program,state,bindings):
    """Measure actual NJC-generated head fields for separate Body/Face drives."""
    heads={state['grids'][d['id']] for d in program['domains'] if d['bone_sources']==['Head']}
    rows=[]
    for parameter in DEPTH_ANGLE_PARAMETERS:
        fields=[b for b in bindings if b['target']['uuid'] in heads and b['parameter']['name']==parameter and b['name']=='deform']
        rows.append({'parameter':parameter,'head_grid_count':len(fields),
            'maximum_native_head_grid_displacement':max((float(np.max(abs(np.asarray(b['data']['values'])))) for b in fields),default=0.)})
    bones={b['id']:b for b in program['scaffold']['bones']}
    axis=np.asarray(bones['Head']['head'][:2])-bones['Neck']['head'][:2]
    intended=np.asarray(bones['Head']['tail'][:2])-bones['Head']['head'][:2]
    return {'source':'NJC native Grid binding readback; observation, not a quality acceptance gate',
            'head_grid_scope':'local shape only; world attachment translation is listed separately',
            'terminal_head_axis_model':axis.tolist(),
            'terminal_axis_dot_head_direction':float(axis@intended),
            'attachment_authority':'common Head::Root under body origin Part',
            'head_allow_parent_to_targets':next(b['allow_parent_to_targets'] for b in program['scaffold']['bones'] if b['id']=='Head'),
            'parameters':rows}


def check_bindings(state,bindings,part_program=None):
    bones=set(state['bones'].values());grids=set(grid_ids(state))
    owned=set() if part_program is None else {
        (op['target'],op['parameter'],'deform') for op in part_program['operations']
        if op['target'] in part_program['bound_targets']}
    for b in bindings:
        uid=b['target']['uuid']
        if (uid,b['parameter']['name'],b['name']) in owned:
            if not np.asarray(b['data']['isSet']).all():raise ValueError('Incomplete PSD Part correction keys')
            continue
        if uid not in bones and (uid not in grids or b['name']!='deform'):
            raise ValueError('Unaccounted face angle binding on artwork: '+str(b['target']))
        if b['name']=='deform' and uid not in grids:
            raise ValueError('Part angle deformation has no matching PSD-shape provenance')
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
    grids=set(grid_ids(state));bones=set(state['bones'].values())
    if any(b['target']['uuid'] not in bones and
           (b['target']['uuid'] not in grids or b['name']!='deform') for b in existing):
        raise ValueError('PSD-shape Face/Body Part correction integration is not implemented')
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
                wait_for_baked_key(reader,uid,grid_ids(state),[x,y])
                print('Native depth angle',parameter,x,y,flush=True)
    n.call('ToolCommand_ModelEditMode');n.call('ViewportCommand_ResetParameters')
    bindings,refresh_observations=settle_native_keys(reader,state,save)
    after=fixed_inputs(n,state)
    if json_digest(before)!=json_digest(after):raise ValueError('Native bake changed fixed depth or rig inputs')
    apply_registered_fields(n,p,state)
    write_json(run/'native-depth-bake-observed.json',{
        'program_sha256':p['content_sha256'],'fixed_inputs':after,
        'bindings':bindings,'validation_complete':False})
    check_bindings(state,bindings)
    checks=head_projection_checks(p,state,bindings)
    write_json(run/'head-drive-observation.json',head_drive_observation(p,state,bindings))
    result={'program_sha256':p['content_sha256'],'generator_sha256':digest(Path(__file__)),
            'method':'Grid angle keys: NJC DepthBoneCommand_ApplyDepthBoneDeform only; PSD Part residuals authored in the following separate stage',
            'fixed_public_inputs_sha256':json_digest(before),'fixed_inputs_unchanged':True,
            'bindings':bindings,'head_projection_checks':checks,'part_angle_binding_count_at_grid_bake':0,
            'native_refresh_observations':refresh_observations,
            'preexisting_grid_bindings_replaced':sum(len(c['bindings']) for c in removals)}
    result['content_sha256']=json_digest(result);write_json(run/'depth-angle-program.json',result)
    state['depth_angle_program_sha256']=result['content_sha256'];write_json(run/'native-state.json',state)
    print(('Saved' if save else 'Generated')+' native depth/bone Face and Body angles; observed affine XYZ residual',max(c['maximum_affine_xyz_residual_model'] for c in checks),flush=True)


def validate(run,n,available):
    run=Path(run);p=read_json(run/'program.json');state=read_json(run/'native-state.json')
    expected=read_json(run/'depth-angle-program.json')
    signed=dict(expected);sig=signed.pop('content_sha256')
    if json_digest(signed)!=sig or sig!=state['depth_angle_program_sha256'] or expected['program_sha256']!=p['content_sha256']:
        raise ValueError('Native depth angle evidence mismatch')
    actual=[b for b in available.values() if b['parameter']['name'] in DEPTH_ANGLE_PARAMETERS]
    from riglib.cheek_correction import load_owned
    part_program=load_owned(run,state)
    check_bindings(state,actual,part_program)
    lookup={(b['target']['uuid'],b['parameter']['name'],b['name']):b for b in actual}
    maximum=0.;keys=0;differences=[]
    for b in expected['bindings']:
        a=lookup[b['target']['uuid'],b['parameter']['name'],b['name']]
        if a['axisValues']!=b['axisValues']:raise ValueError('Native depth angle axes changed')
        error=float(np.max(abs(np.asarray(a['data']['values'])-np.asarray(b['data']['values']))))
        if error>.0003:
            differences.append({'target':b['target'],'parameter':b['parameter'],'binding':b['name'],'maximum_error':error})
        maximum=max(maximum,error)
        if b['name']=='deform':keys+=int(np.asarray(b['data']['isSet']).sum())
    write_json(run/'native-bake-binding-differences.json',{'program_sha256':p['content_sha256'],'differences':differences})
    if json_digest(fixed_inputs(n,state))!=expected['fixed_public_inputs_sha256']:
        raise ValueError('Saved fixed depth or rig differs from native bake inputs')
    checks=head_projection_checks(p,state,actual)
    write_json(run/'head-drive-observation.json',head_drive_observation(p,state,actual))
    return {'passed':not differences,'binding_differences':differences,'native_surface_keys_verified':keys,'maximum_saved_error':maximum,
            'separate_part_angle_binding_count':len(part_program['bound_targets']) if part_program else 0,'fixed_inputs_unchanged':True,
            'maximum_affine_xyz_residual_model':max(c['maximum_affine_xyz_residual_model'] for c in checks)}



if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--run',required=True);a.add_argument('--njc',required=True)
    args=a.parse_args();bake(args.run,args.njc)
