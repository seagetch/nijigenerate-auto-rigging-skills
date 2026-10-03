"""Compile shared leg displacements with anatomical stations and fixed feet.

The native nearest-bone field can fold between a moving knee and a locked foot.
This longitudinal Hermite field uses the same authored joint rotations and
rest scaffold, and shares one field across all material charts of each leg.
"""
import argparse,math
from pathlib import Path
import numpy as np
from riglib.data import read_json,write_json,json_digest,digest
from riglib.live import Live
from build_native import require_single_rig
from riglib.carrier import to_root,rotation as carrier_rotation


def rotation(degrees):
    a=math.radians(degrees)
    return np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])


def compile_fields(program,state):
    landmarks={k:np.array(v) for k,v in program['scaffold']['landmarks'].items()}
    operations=[];checks=[]
    for spec in program['parameters']:
        if spec.get('deformation_authority')=='registered_reference_fields':continue
        if spec['name']!='Body::Roll' and not spec['name'].startswith(('Leg::','Knee::')):continue
        binding=spec['bindings'][0]
        for domain in program['domains']:
            if not domain['owner'].startswith('leg:'):continue
            side=domain['side'];p=np.array([landmarks[k+'.'+side] for k in ('hip','knee','ankle')])
            axis=p[2]-p[0];axis/=np.linalg.norm(axis)
            stations=(p-p[0])@axis
            if min(np.diff(stations))<=0:raise ValueError('Nonmonotone anatomical stations')
            xs=np.array(domain['axis_x']);ys=np.array(domain['axis_y'])
            xy=np.array([[x,y] for y in ys for x in xs]);t=(to_root(xy,domain['carrier_frame'])-p[0])@axis
            for key in (-1,-.5,.5,1,0):
                angle=binding['degrees']*key;posed=p.copy()
                if spec['name']=='Body::Roll':
                    center=landmarks['pelvis'];posed=(p-center)@rotation(angle).T+center
                elif binding['bone']=='Thigh.'+side:
                    posed=(p-p[0])@rotation(angle).T+p[0]
                elif binding['bone']=='Shin.'+side:
                    posed[2]=(p[2]-p[1])@rotation(angle).T+p[1]
                    # With a fixed ankle, the knee receives the opposite bend
                    # from the knee driver; the foot station stays invariant.
                    posed[1]=(p[1]-p[2])@rotation(-angle).T+p[2]
                posed[2]=p[2]
                delta=posed-p;off=np.zeros_like(xy)
                for idx,value in enumerate(t):
                    if value<=stations[0]:off[idx]=delta[0]
                    elif value>=stations[2]:off[idx]=delta[2]
                    else:
                        segment=0 if value<=stations[1] else 1
                        u=(value-stations[segment])/(stations[segment+1]-stations[segment])
                        w=u*u*(3-2*u)
                        off[idx]=(1-w)*delta[segment]+w*delta[segment+1]
                if domain['bone_sources']==['Foot.'+side]:off[:]=0
                off=np.round(off@carrier_rotation(domain['carrier_frame']['rotation']),4);q=(xy+off).reshape(len(ys),len(xs),2)
                dx=q[:-1,1:]-q[:-1,:-1];dy=q[1:,:-1]-q[:-1,:-1]
                dx2=q[1:,1:]-q[1:,:-1];dy2=q[1:,1:]-q[:-1,1:]
                den=np.diff(ys)[:,None]*np.diff(xs)[None,:]
                minimum=min(float(((a[:,:,0]*b[:,:,1]-a[:,:,1]*b[:,:,0])/den).min())
                            for a,b in ((dx,dy),(dx2,dy2),(dx,dy2),(dx2,dy)))
                if not np.isfinite(off).all() or minimum<.05:raise ValueError('Fixed foot field folds')
                operations.append({'parameter':state['parameters'][spec['name']],
                    'target':state['grids'][domain['id']],'key':[key],'values':off.ravel().tolist()})
                checks.append({'parameter':spec['name'],'domain':domain['id'],'key':key,'minimum_area_ratio':minimum})
    result={'generator_sha256':digest(Path(__file__)),'source_program_sha256':program['content_sha256'],
        'method':'shared longitudinal cubic Hermite displacements between fitted hip/knee/locked ankle',
        'knee_policy':'fixed-ankle inverse bend; preserves foot position',
        'operations':operations,'checks':checks}
    result['content_sha256']=json_digest(result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--njc',required=True)
    a=p.parse_args();run=Path(a.run);state=read_json(run/'native-state.json');program=read_json(run/'program.json')
    result=compile_fields(program,state);write_json(run/'fixed-foot-program.json',result)
    n=Live(a.njc,run/'fixed-foot-journal');require_single_rig(n,state['rig_root'],state['bones'].values())
    def emit(op,dry):
        method=n.preflight_call if dry else n.call
        return method('ModelCommand_SetDeformBinding',bindingName='deform',values=op['values'],
            context={'parameters':[op['parameter']],'nodes':[op['target']],'parameterValue':op['key']})
    for op in result['operations']:emit(op,True)
    n.call('ViewportCommand_ResetParameters')
    for op in result['operations']:emit(op,False)
    n.call('ViewportCommand_ResetParameters');n.save(state['output'])
    state['fixed_foot_program_sha256']=result['content_sha256'];write_json(run/'native-state.json',state)
    print('Applied shared fixed-foot fields; min area ratio',min(c['minimum_area_ratio'] for c in result['checks']),flush=True)
