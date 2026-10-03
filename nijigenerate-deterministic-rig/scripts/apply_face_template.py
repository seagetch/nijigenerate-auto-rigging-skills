"""Calibrate, compile and apply an error-bounded face template through NJC."""
import argparse
from pathlib import Path
import numpy as np
from riglib.data import read_json,write_json,json_digest
from riglib.live import Live
from riglib.face_transfer import minimum_ratio
from build_native import require_single_rig


def verify_face_program(n,face):
    grid=face['grid'];node=n.read(grid['target'])['item']['data']
    for source,target in [('axis_x','grid_axis_x'),('axis_y','grid_axis_y'),('depths','depths')]:
        a=np.asarray(grid[source]);b=np.asarray(node[target])
        if a.shape!=b.shape or not np.allclose(a,b,rtol=0,atol=.0003):raise ValueError('Live face grid differs from its source program')
    resources={};maximum=0.
    for op in face['operations']:
        pid=op['parameter']
        if pid not in resources:
            uri=f'resource://nijigenerate/bindings/get?parameter={pid}&target={grid["target"]}&name=deform'
            resources[pid]=n.invoke(['resources','read',uri])['item']
        item=resources[pid];key=op['key']+[0] if len(op['key'])==1 else op['key']
        indices=[next(i for i,v in enumerate(axis) if abs(v-value)<1e-6) for axis,value in zip(item['axisValues'],key)]
        i,j=indices
        if not item['data']['isSet'][i][j]:raise ValueError('Missing face key')
        actual=np.asarray(item['data']['values'][i][j]).reshape(-1);expected=np.asarray(op['values'])
        if actual.shape!=expected.shape:raise ValueError('Face binding shape mismatch')
        error=float(max(abs(actual-expected)));maximum=max(maximum,error)
        if error>.0003:raise ValueError('Live face key differs from its source program')
    return {'passed':True,'max_binding_coordinate_error':maximum,'keys':len(face['operations'])}


def calibration_seed(run,n,state,program):
    if 'face_template_program_sha256' in state:
        previous=read_json(run/'face-template-program.json')
        if previous['content_sha256']!=state['face_template_program_sha256']:raise ValueError('Face program identity mismatch')
        if previous.get('source_program_sha256',program['content_sha256'])!=program['content_sha256']:raise ValueError('Stale face calibration')
        verify_face_program(n,previous)
        return previous
    gid=state['grids']['head/face'];node=n.read(gid)['item']['data']
    xs=np.array(node['grid_axis_x']);ys=np.array(node['grid_axis_y'])
    points=np.array([[x,y] for y in ys for x in xs]);z=np.array(node['depths'])*program['native_depth_scale']
    design=np.c_[points,z,np.ones(len(points))];calibration=[]
    for spec in program['parameters']:
        pid=state['parameters'][spec['name']]
        item=n.invoke(['resources','read',f'resource://nijigenerate/bindings/get?parameter={pid}&target={gid}&name=deform'])['item']
        if item is None:raise ValueError('Missing native face calibration binding')
        for i,col in enumerate(item['data']['values']):
            for j,values in enumerate(col):
                if not item['data']['isSet'][i][j]:raise ValueError('Missing native calibration key')
                key=[item['axisValues'][0][i]]+([item['axisValues'][1][j]] if spec['vec2'] else [])
                target=points+np.asarray(values).reshape(-1,2)
                matrix=np.linalg.lstsq(design,target,rcond=None)[0]
                residual=float(np.max(abs(design@matrix-target)))
                if residual>.003:raise ValueError('Native head projection is not affine in XYZ')
                calibration.append({'name':spec['name'],'parameter':pid,'key':key,'matrix':matrix.tolist(),'residual':residual})
    def sign(key,component,factor):
        cal=next(c for c in calibration if c['name']=='Face::Yaw-Pitch' and c['key']==key)
        return float(factor*np.sign(cal['matrix'][2][component]))
    seed={'grid':{'target':gid,'axis_x':xs.tolist(),'axis_y':ys.tolist()},'calibration':calibration,
          'axis_calibration':{'yaw_sign':sign([1,0],0,1),'pitch_sign':sign([0,1],1,-1)},
          'source_program_sha256':program['content_sha256']}
    seed['content_sha256']=json_digest(seed)
    return seed


def compile_face(run,n):
    from refine_face_transfer import compile_transfer
    state=read_json(run/'native-state.json');program=read_json(run/'program.json')
    if 'reference_template' in program:
        raise ValueError('The common reference template owns face geometry and motion; independent face-template overwrite is not permitted')
    require_single_rig(n,state['rig_root'],state['bones'].values())
    seed=calibration_seed(run,n,state,program)
    write_json(run/'face-native-calibration.json',seed)
    return compile_transfer(run,seed)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--njc',required=True);p.add_argument('--apply',action='store_true')
    args=p.parse_args();run=Path(args.run).resolve();n=Live(args.njc,run/'face-transfer-journal')
    result,state=compile_face(run,n);grid=result['grid']
    def emit(op,dry):
        method=n.preflight_call if dry else n.call
        return method('ModelCommand_SetDeformBinding',bindingName='deform',values=op['values'],
                      context={'parameters':[op['parameter']],'nodes':[op['target']],'parameterValue':op['key']})
    for op in result['operations']:emit(op,True)
    n.preflight_call('VertexCommand_DefineGrid',axisX=grid['axis_x'],axisY=grid['axis_y'],context={'nodes':[grid['target']]})
    n.preflight_call('DepthMapCommand_SetDepths',target=grid['target'],depths=grid['depths'])
    for mesh in result['meshes']:n.preflight_call('VertexCommand_DefineMesh',vertices=mesh['vertices'],indices=mesh['indices'],context={'nodes':[mesh['target']]})
    if args.apply:
        n.call('ViewportCommand_ResetParameters')
        for pid in sorted({op['parameter'] for op in result['operations']}):
            n.call('BindingCommand_RemoveBinding',context={'parameters':[pid],'bindings':[{'target':grid['target'],'name':'deform'}]})
        n.call('VertexCommand_DefineGrid',axisX=grid['axis_x'],axisY=grid['axis_y'],context={'nodes':[grid['target']]})
        n.call('DepthMapCommand_SetDepths',target=grid['target'],depths=grid['depths'])
        for mesh in result['meshes']:n.call('VertexCommand_DefineMesh',vertices=mesh['vertices'],indices=mesh['indices'],context={'nodes':[mesh['target']]})
        for op in sorted(result['operations'],key=lambda op:all(k==0 for k in op['key'])):emit(op,False)
        n.call('ViewportCommand_ResetParameters');n.save(state['output'])
        write_json(run/'face-transfer-applied-check.json',verify_face_program(n,result))
        write_json(run/'face-template-program.json',result)
        state['face_template_program_sha256']=result['content_sha256'];write_json(run/'native-state.json',state)
    print('Template depth preserved;', 'applied' if args.apply else 'preflighted',flush=True)
