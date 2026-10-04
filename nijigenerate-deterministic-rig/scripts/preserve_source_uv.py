"""Register source texture placement without editing native AutoMesh arrays.

The import and AutoMesh use different texel conventions. Match their UV-to-parent
maps by changing only the Part transform before authoring displacement bindings.
Native vertices, UVs, origin and triangle indices remain exactly unchanged.
"""
import argparse,re
from pathlib import Path
import numpy as np
from riglib.data import read_json,write_json,json_digest,digest
from riglib.live import Live
from build_native import require_single_rig
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
    if any(key in state for key in ('shape_controls_sha256','shape_corrections_sha256')):
        raise ValueError('Texture placement must be registered before Part deformations are authored')
    n=Live(njc,run/'uv-registration-journal');ids=sorted(p['uuid'] for d in program['domains'] for p in d['parts'])
    observation=read_json(run/'observation.json')
    # Registration already saved, reopened and captured this exact PSD through
    # NJC. Use those signed public UV observations instead of reopening a file
    # that may have acquired an editor autosave lock during a long mesh build.
    source={}
    for row in observation['nodes']:
        if row['uuid'] not in ids:continue
        mesh=row['mesh']
        if not mesh.get('uvs'):raise ValueError('PSD registration must capture native source UVs')
        source[row['uuid']]={'mesh':{'verts':np.asarray(mesh['vertices']).ravel().tolist(),'uvs':mesh['uvs']}}
    require_single_rig(n,state['rig_root'],state['bones'].values())
    n.call('ToolCommand_ModelEditMode');n.call('ViewportCommand_ResetParameters')
    current={uid:n.read(uid)['item']['data'] for uid in ids};ops=[]
    for uid in ids:
        old=current[uid];a=affine(source[uid]['mesh']);b=affine(old['mesh'])
        inverse=np.linalg.inv(a[:2]);linear=b[:2]@inverse;shift=(b[2]-a[2])@inverse
        if not np.isfinite(linear).all() or not np.isfinite(shift).all() or not np.allclose(linear,np.diag(np.diag(linear)),atol=1e-6) or min(np.diag(linear))<=0:
            raise ValueError('UV registration needs an unsupported sheared Part frame')
        if not np.allclose(old['transform']['rot'][:2],0) or not np.allclose(old['mesh']['origin'],0):
            raise ValueError('UV registration needs a resolved non-axis-aligned frame')
        scale=np.diag(linear)
        node_scale=np.asarray(old['transform']['scale'])*scale
        translation=np.asarray(old['transform']['trans'][:2])+(shift*np.asarray(old['transform']['scale']))@rotation(old['transform']['rot'][2]).T
        ops.append({'target':uid,
                    'scale':node_scale.tolist(),'translation':translation.tolist(),
                    'automesh_to_source_scale':scale.tolist(),'automesh_to_source_shift':shift.tolist(),
                    'source_uv_affine':a.tolist(),
                    'native_mesh':{k:old['mesh'][k] for k in ('verts','uvs','indices','origin')},
                    'original_transform':old['transform']})
    for row in n.binding_resources():
        match=re.search(r'target=(\d+)&name=([^&]+)',row['uri'])
        if match and int(match[1]) in ids:
            raise ValueError('Texture placement requires Parts without existing bindings')
    def emit(dry):
        call=n.preflight_call if dry else n.call
        for op in ops:
            ctx={'nodes':[op['target']]}
            for axis,i in [('X',0),('Y',1)]:
                call('Inspector_Apply_Scale'+axis,value=op['scale'][i],context=ctx)
                call('Inspector_Apply_Translation'+axis,value=op['translation'][i],context=ctx)
    report={'generator_sha256':digest(Path(__file__)),'source_program_sha256':program['content_sha256'],
            'method':'source UV-to-parent affine registration through Part TRS only; native AutoMesh arrays unchanged; before Part deformation generation',
            'parts':ops,'bindings':[]}
    report['content_sha256']=json_digest(report);write_json(run/'source-uv-program.json',report)
    emit(True);emit(False);n.call('ViewportCommand_ResetParameters')
    max_position=0.;unchanged=True
    for op in ops:
        actual=n.read(op['target'])['item']['data'];mesh=actual['mesh'];v=np.asarray(mesh['verts']).reshape(-1,2)
        old=op['original_transform'];t=actual['transform'];a=np.asarray(op['source_uv_affine'])
        source_xy=(np.asarray(mesh['uvs']).reshape(-1,2)-a[2])@np.linalg.inv(a[:2])
        position_error=float(np.max(abs((v*np.array(t['scale']))@rotation(t['rot'][2]).T+t['trans'][:2]-((source_xy*np.array(old['scale']))@rotation(old['rot'][2]).T+old['trans'][:2]))))
        unchanged=unchanged and all(mesh[k]==value for k,value in op['native_mesh'].items())
        max_position=max(max_position,position_error)
    check={'max_source_uv_parent_position_error':max_position,'native_mesh_arrays_unchanged':unchanged,'parts':len(ops),
           'passed':max_position<.001 and unchanged}
    write_json(run/'source-uv-applied-check.json',check)
    if not check['passed']:raise ValueError('UV preservation readback failed: '+str(check))
    n.save(state['output']);state['source_uv_program_sha256']=report['content_sha256'];write_json(run/'native-state.json',state)
    print('Source texture placement registered; native AutoMesh preserved:',check,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--njc',required=True)
    a=p.parse_args();apply(a.run,a.njc)
