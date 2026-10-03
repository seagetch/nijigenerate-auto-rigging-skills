"""Refresh generated depth on the designated live rig without adding nodes."""
import argparse,itertools
from pathlib import Path
from riglib.data import read_json,write_json,json_digest
from riglib.live import Live
from build_native import require_single_rig,wait_for_baked_key,apply_registered_fields


def refresh(program,state,executable,journal):
    signed=dict(program);signed.pop('content_sha256',None)
    if json_digest(signed)!=program['content_sha256']:raise ValueError('program hash mismatch')
    if program['source'].get('transport')!='njc':
        raise ValueError('Surface source observation must be captured through NJC')
    n=Live(executable,journal);reader=Live(executable)
    require_single_rig(reader,state['rig_root'],state['bones'].values())
    roots=n.find('DepthRigRoot')['items']
    if [r['uuid'] for r in roots]!=[state['rig_root']]:raise RuntimeError('Wrong live rig')
    if set(state['grids'])!={d['id'] for d in program['domains']}:raise RuntimeError('Surface set changed; rebuild required')
    for d in program['domains']:
        n.preflight_call('DepthMapCommand_SetDepths',target=state['grids'][d['id']],depths=d['depths'])
    for spec in program['parameters']:
        if any(b['axis'] in ('x','y') for b in spec['bindings']):
            n.preflight_call('BindingCommand_RemoveBinding',context={'parameters':[state['parameters'][spec['name']]],
                             'bindings':[{'target':g,'name':'deform'} for g in state['grids'].values()]})
    n.call('ViewportCommand_ResetParameters')
    for d in program['domains']:
        n.call('DepthMapCommand_SetDepths',target=state['grids'][d['id']],depths=d['depths'])
    for spec in program['parameters']:
        # Depth affects X/Y rotations. A pure planar rotation is depth invariant.
        if not any(b['axis'] in ('x','y') for b in spec['bindings']):continue
        uid=state['parameters'][spec['name']]
        n.call('ViewportCommand_ResetParameters')
        n.call('BindingCommand_RemoveBinding',context={'parameters':[uid],'bindings':[{'target':g,'name':'deform'} for g in state['grids'].values()]})
        keys=itertools.product([-1,-.5,0,.5,1],repeat=2 if spec['vec2'] else 1)
        for key in keys:
            n.call('ParameditCommand_SetArmedParameterAndKeypoint',context={'armedParameters':[uid],'parameterValue':list(key)})
            n.call('DepthBoneCommand_ApplyDepthBoneDeform',root=state['rig_root'],targets='',context={'armedParameters':[uid]})
            wait_for_baked_key(reader,uid,state['grids'].values(),key)
        print('Refreshed '+spec['name'],flush=True)
    apply_registered_fields(n,program,state)
    n.call('ViewportCommand_ResetParameters');n.save(state['output'])
    require_single_rig(reader,state['rig_root'],state['bones'].values())
    state['program_sha256']=program['content_sha256']


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--program',required=True);p.add_argument('--state',required=True);p.add_argument('--njc',required=True);p.add_argument('--journal',required=True)
    a=p.parse_args();s=read_json(a.state);refresh(read_json(a.program),s,a.njc,a.journal);write_json(a.state,s)
