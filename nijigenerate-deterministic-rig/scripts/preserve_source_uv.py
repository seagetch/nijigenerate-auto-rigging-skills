"""Preserve imported UVs when the native mesh editor uses texel-centre UVs.

Derive an affine change of Part-local coordinates from NJC source/current UVs.
Cancel it in the Part transform and apply its linear part to local displacement
bindings. Parent-space geometry and motion stay fixed; source UVs are restored.
"""
import argparse,re
from pathlib import Path
import numpy as np
from riglib.data import read_json,write_json,json_digest,digest
from riglib.live import Live
from build_native import model_structure,require_single_rig
from riglib.carrier import rotation


def affine(mesh):
    v=np.asarray(mesh['verts']).reshape(-1,2);uv=np.asarray(mesh['uvs']).reshape(-1,2)
    a=np.linalg.lstsq(np.c_[v,np.ones(len(v))],uv,rcond=None)[0]
    if np.max(abs(np.c_[v,np.ones(len(v))]@a-uv))>1e-6:
        raise ValueError('Source UVs require non-affine registration')
    return a


def apply(run,njc):
    run=Path(run).resolve();state=read_json(run/'native-state.json');program=read_json(run/'program.json')
    if state.get('source_uv_program_sha256'):raise ValueError('UV registration is already applied')
    n=Live(njc,run/'uv-registration-journal');ids=sorted(p['uuid'] for d in program['domains'] for p in d['parts'])
    observation=read_json(run/'observation.json');expected=sorted((r['uuid'],r['type'],r['parent']) for r in observation['nodes'])
    try:
        n.open(run/'imported.inx')
        if model_structure(n)!=(expected,[]):raise ValueError('UV source structure differs from PSD import')
        source={uid:n.read(uid)['item']['data'] for uid in ids}
    finally:
        n.open(state['output']);require_single_rig(n,state['rig_root'],state['bones'].values())
    n.call('ToolCommand_ModelEditMode');n.call('ViewportCommand_ResetParameters')
    current={uid:n.read(uid)['item']['data'] for uid in ids};ops=[];bindings=[];scales={}
    for uid in ids:
        old=current[uid];a=affine(source[uid]['mesh']);b=affine(old['mesh'])
        inverse=np.linalg.inv(b[:2]);linear=a[:2]@inverse;shift=(a[2]-b[2])@inverse
        if not np.allclose(linear,np.diag(np.diag(linear)),atol=1e-6) or min(np.diag(linear))<=0:
            raise ValueError('UV registration needs an unsupported sheared Part frame')
        if not np.allclose(old['transform']['rot'][:2],0) or not np.allclose(old['mesh']['origin'],0):
            raise ValueError('UV registration needs a resolved non-axis-aligned frame')
        scale=np.diag(linear);scales[uid]=scale
        vertices=np.asarray(old['mesh']['verts']).reshape(-1,2)
        # Small contour Parts amplify model-space rounding into UV error.
        # Preserve the affine result and let the native float32 mesh store it.
        new_vertices=vertices*scale+shift
        node_scale=np.asarray(old['transform']['scale'])/scale
        translation=np.asarray(old['transform']['trans'][:2])-(shift*node_scale)@rotation(old['transform']['rot'][2]).T
        ops.append({'target':uid,'vertices':new_vertices.ravel().tolist(),'indices':old['mesh']['indices'],
                    'scale':node_scale.tolist(),'translation':translation.tolist(),
                    'local_coordinate_scale':scale.tolist(),'local_coordinate_shift':shift.tolist(),
                    'source_uv_affine':a.tolist(),'original_vertices':vertices.tolist(),
                    'original_transform':old['transform']})
    for row in n.binding_resources():
        uri=row['uri'];match=re.search(r'target=(\d+)&name=([^&]+)',uri)
        if not match or int(match[1]) not in scales:continue
        if match[2]!='deform':raise ValueError('UV registration requires explicit handling of non-deform Part bindings')
        item=n.invoke(['resources','read',uri])['item'];uid=int(match[1]);pid=item['parameter']['uuid']
        for i,col in enumerate(item['data']['values']):
            for j,values in enumerate(col):
                if not item['data']['isSet'][i][j]:continue
                key=[item['axisValues'][0][i],item['axisValues'][1][j]]
                value=np.asarray(values).reshape(-1,2)*scales[uid]
                bindings.append({'parameter':pid,'target':uid,'key':key,'values':np.round(value,5).ravel().tolist()})
    def emit(dry):
        call=n.preflight_call if dry else n.call
        for op in ops:
            ctx={'nodes':[op['target']]}
            call('VertexCommand_DefineMesh',vertices=op['vertices'],indices=op['indices'],context=ctx)
            for axis,i in [('X',0),('Y',1)]:
                call('Inspector_Apply_Scale'+axis,value=op['scale'][i],context=ctx)
                call('Inspector_Apply_Translation'+axis,value=op['translation'][i],context=ctx)
        for op in sorted(bindings,key=lambda o:all(k==0 for k in o['key'])):
            call('ModelCommand_SetDeformBinding',bindingName='deform',values=op['values'],
                 context={'parameters':[op['parameter']],'nodes':[op['target']],'parameterValue':op['key']})
    report={'generator_sha256':digest(Path(__file__)),'source_program_sha256':program['content_sha256'],
            'method':'source/current UV affine registration; inverse Part transform; conjugated displacement bindings',
            'parts':ops,'bindings':bindings}
    report['content_sha256']=json_digest(report);write_json(run/'source-uv-program.json',report)
    emit(True);emit(False);n.call('ViewportCommand_ResetParameters')
    max_uv=0.;max_position=0.
    for op in ops:
        actual=n.read(op['target'])['item']['data'];mesh=actual['mesh'];v=np.asarray(mesh['verts']).reshape(-1,2)
        original=np.asarray(op['original_vertices']);old=op['original_transform'];t=actual['transform']
        position_error=float(np.max(abs((v*np.array(t['scale']))@rotation(t['rot'][2]).T+t['trans'][:2]-((original*np.array(old['scale']))@rotation(old['rot'][2]).T+old['trans'][:2]))))
        wanted=np.c_[original,np.ones(len(original))]@np.array(op['source_uv_affine'])
        uv_error=float(np.max(abs(np.asarray(mesh['uvs']).reshape(-1,2)-wanted)))
        max_position=max(max_position,position_error);max_uv=max(max_uv,uv_error)
    check={'max_parent_position_error':max_position,'max_uv_error':max_uv,'parts':len(ops),
           'passed':max_position<.001 and max_uv<1e-6}
    write_json(run/'source-uv-applied-check.json',check)
    if not check['passed']:raise ValueError('UV preservation readback failed: '+str(check))
    n.save(state['output']);state['source_uv_program_sha256']=report['content_sha256'];write_json(run/'native-state.json',state)
    print('Source UV registration restored:',check,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--njc',required=True)
    a=p.parse_args();apply(a.run,a.njc)
