"""Verify PSD-shape keys authored in the registered, immutable AutoMesh frame."""
import numpy as np
from .data import read_json,json_digest
from .shape_controls import area_ratios
from .part_mesh import verify_mesh


def validate(run,state,snapshot):
    uv=read_json(run/'source-uv-program.json')
    bindings={(b['parameter']['name'],b['target']['uuid'],b['name']):b for b in snapshot['bindings'].values()}
    nodes={}
    def visit(v):
        nodes[v['uuid']]=v
        for child in v.get('children',[]):visit(child)
    visit(snapshot['nodes']['nodes']);verified=0;minimum=1.;maximum=0.;findings=[]
    if json_digest({k:v for k,v in uv.items() if k!='content_sha256'})!=uv['content_sha256'] or uv['content_sha256']!=state['source_uv_program_sha256']:
        raise ValueError('Source UV registration identity mismatch')
    evidence=read_json(run/'evidence.json')
    composites=state.get('composite_automesh',[])
    for row in composites:
        verify_mesh({'mesh':nodes[row['target']]['mesh']},row['mesh'])
    for op in uv['parts']:
        mesh=nodes[op['target']]['mesh'];record=evidence['part_meshes'][str(op['target'])]
        if not op.get('native_mesh') or any(mesh[k]!=v for k,v in op['native_mesh'].items()):
            raise ValueError('Saved native AutoMesh arrays changed during UV registration')
        if mesh['verts']!=record['vertices'] or mesh['indices']!=record['indices']:
            raise ValueError('Saved Part mesh differs from original native AutoMesh readback')
        for key in ('uvs','origin'):
            if key in record and mesh[key]!=record[key]:
                raise ValueError('Saved Part '+key+' differs from original native AutoMesh readback')
    from .cheek_correction import load_owned
    correction=load_owned(run,state)
    for filename,signature in [('shape-controls-program.json','shape_controls_sha256'),
                               ('shape-corrections-program.json','shape_corrections_sha256')]:
        if signature not in state:continue
        program=read_json(run/filename);signed={k:v for k,v in program.items() if k!='content_sha256'}
        if json_digest(signed)!=program['content_sha256'] or program['content_sha256']!=state[signature]:raise ValueError('PSD-shape program identity mismatch')
        if program.get('source_uv_program_sha256')!=uv['content_sha256']:raise ValueError('Part deformation was not authored in the registered AutoMesh frame')
        for op in program['operations']:
            name=op['parameter'];uid=op['target']
            if name in ('Face::Yaw-Pitch','Face::Roll','Body::Yaw-Pitch','Body::Roll'):
                if correction is None or filename!='shape-corrections-program.json':
                    raise ValueError('Part angle correction has no dedicated PSD-shape provenance')
            expected=np.asarray(op['values']).reshape(-1,2)
            b=bindings.get((name,uid,'deform'))
            if b is None:
                if np.any(expected):raise ValueError('Missing PSD-shape binding')
                continue
            i,j=[next(k for k,v in enumerate(a) if abs(v-q)<1e-6) for a,q in zip(b['axisValues'],op['key'])]
            actual=np.asarray(b['data']['values'][i][j]).reshape(-1,2)
            error=float(abs(actual-expected).max());maximum=max(maximum,error)
            if not b['data']['isSet'][i][j] or error>.0003:
                findings.append({'part':uid,'parameter':name,'key':op['key'],'saved_difference':error,
                                 'key_set':b['data']['isSet'][i][j]})
            mesh=nodes[uid]['mesh'];rest=np.asarray(mesh['verts']).reshape(-1,2)
            ratio=float(area_ratios(rest,actual,mesh['indices']).min());minimum=min(minimum,ratio)
            if ratio<=0:findings.append({'part':uid,'parameter':name,'key':op['key'],'minimum_area_ratio':ratio})
            verified+=1
    return {'passed':not findings,'findings':findings,'native_automesh_parts_verified':len(uv['parts']),
            'cheek_correction_verified':correction is not None,
            'native_automesh_composites_verified':len(composites),
            'verified_keys':verified,'maximum_saved_error':maximum,'minimum_part_area_ratio':minimum}
