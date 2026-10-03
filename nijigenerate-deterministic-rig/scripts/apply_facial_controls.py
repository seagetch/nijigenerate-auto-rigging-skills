"""Apply the common reference's independent two-axis facial controls via NJC."""
import argparse
from pathlib import Path
import numpy as np
from riglib.data import read_json,write_json,json_digest
from riglib.live import Live,created_id
from riglib.reference_fields import sample
from riglib.reference_materials import fit_mesh_projection
from riglib.facial_controls import control_role
from riglib.carrier import rotation
from build_native import require_single_rig
from build_face import frame


def apply(run,njc):
    run=Path(run).resolve();state=read_json(run/'native-state.json');evidence=read_json(run/'evidence.json')
    observation=read_json(run/'observation.json')
    template=read_json(Path(__file__).resolve().parents[1]/'structures/reference-humanoid.registered.json')
    controls=template['facial_controls'];specs=controls['parameters']
    if json_digest(specs)!=controls['content_sha256']:raise ValueError('Facial controls signature mismatch')
    n=Live(njc,run/'facial-controls-journal');require_single_rig(n,state['rig_root'],state['bones'].values())
    n.call('ToolCommand_ModelEditMode');n.call('ViewportCommand_ResetParameters')
    eyes={eye['side']:eye for eye in evidence['eyes']};targets={};geometry={};operations=[];checks=[]
    brow_nodes=[d for d in observation['nodes'] if d['type']=='Part' and control_role(d['name'])=='brow']
    if len(brow_nodes)!=2:raise ValueError('PSD needs two observed eyebrow Parts')
    eye_centers={side:np.mean(eye['canthi_model'],axis=0) for side,eye in eyes.items()}
    brow_ids={}
    for d in brow_nodes:
        b=np.asarray(d['bounds']['nominal_world_xy']);center=(b[:2]+b[2:])/2
        side=min(eyes,key=lambda side:np.linalg.norm(center-eye_centers[side]))
        if side in brow_ids:raise ValueError('Ambiguous eyebrow side registration')
        brow_ids[side]=d['uuid']
    for name,spec in specs.items():
        if name=='Mouth::Open':
            ids={'mouth':evidence['mouth']['part']};points=evidence['mouth']['axis_model']
        else:
            side=name.split('::')[1];eye=eyes[side];points=eye['canthi_model']
            if name.startswith('Eyebrow::'):ids={'brow':brow_ids[side]}
            elif name.endswith('::X-Y'):ids={'iris':eye['parts']['iris']}
            else:ids={k:v for k,v in eye['parts'].items() if k!='iris'}
        _,basis=frame(points);width=float(np.linalg.norm(np.diff(np.asarray(points),axis=0)))
        targets[name]=list(ids.values())
        for role,uid in ids.items():
            if role not in spec['fields']:raise ValueError('Missing common reference facial role '+name+' '+role)
            if uid not in geometry:
                d=n.read(uid)['item']['data'];t=d['transform']
                if any(t['rot'][:2]) or any(d['mesh']['origin']):raise ValueError('Unsupported facial Part frame')
                linear=rotation(t['rot'][2])@np.diag(t['scale']);v=np.asarray(d['mesh']['verts']).reshape(-1,2)
                root=v@linear.T+np.asarray(t['trans'])[:2]
                geometry[uid]=(root,linear,d['mesh']['indices'])
            root,linear,tri=geometry[uid];uv=(root-root.min(0))/np.ptp(root,axis=0);field=spec['fields'][role]
            for i,x in enumerate(spec['axes'][0]):
                for j,y in enumerate(spec['axes'][1]):
                    delta=sample(field['axis_x'],field['axis_y'],field['values'][i][j],uv)*width@basis.T
                    posed,check=fit_mesh_projection(root,root+delta,tri,
                        directions=[basis[:,1]] if name.endswith('::Blink') else None)
                    local=np.round((posed-root)@np.linalg.inv(linear).T,5)
                    operations.append({'parameter':name,'target':uid,'key':[x,y],'values':local.ravel().tolist()})
                    checks.append({'parameter':name,'role':role,'key':[x,y],**check})
    for kind in ('Blink','X-Y'):
        if set(targets['Eye::L::'+kind])&set(targets['Eye::R::'+kind]):
            raise ValueError('Independent eye controls share a Part target')
    existing={p['name']:p['uuid'] for p in n.find('Parameter')['items']}
    legacy={name for name in state['parameters'] if name.startswith(('Arm::','Elbow::','Leg::','Knee::','Eye::Blink::')) or name=='Eye::Gaze'}
    replace=legacy|set(specs)
    removed=[existing[name] for name in replace if name in existing]
    for op in operations:n.preflight_call('ModelCommand_SetDeformBinding',bindingName='deform',values=op['values'],
        context={'parameters':[4294967295],'nodes':[op['target']],'parameterValue':op['key']})
    report={'template_sha256':template['content_sha256'],'facial_controls_sha256':controls['content_sha256'],
        'program_sha256':state['program_sha256'],'operations':operations,'checks':checks,
        'uv_program_at_application':state.get('source_uv_program_sha256'),
        'targets':targets,'removed_unreferenced_parameters':sorted(legacy),'rig_complete':False}
    write_json(run/'facial-controls-program.json',report)
    if removed:n.call('ParamCommand_RemoveParameter',context={'parameters':removed})
    for name in replace:state['parameters'].pop(name,None)
    for name,spec in specs.items():
        axes=spec['axes'];lo=[a[0] for a in axes];hi=[a[-1] for a in axes]
        uid=created_id(n.call('ParamCommand_Add2DParameter',min=-1,max=1));state['parameters'][name]=uid
        n.call('ParamPropCommand_SetParameterName',newName=name,context={'parameters':[uid]})
        n.call('ParamPropCommand_ApplyParameterPropsAxes',min=lo,max=hi,
            axisX=((np.asarray(axes[0])-lo[0])/(hi[0]-lo[0])).tolist(),
            axisY=((np.asarray(axes[1])-lo[1])/(hi[1]-lo[1])).tolist(),context={'parameters':[uid]})
    # The native API omits new all-zero bindings; create nonzero keys first.
    for op in sorted(operations,key=lambda op:not np.any(op['values'])):
        n.call('ModelCommand_SetDeformBinding',bindingName='deform',values=op['values'],
            context={'parameters':[state['parameters'][op['parameter']]],'nodes':[op['target']],'parameterValue':op['key']})
    for eye in eyes.values():
        iris=eye['parts']['iris'];sclera=eye['parts']['sclera']
        masks=n.read(iris)['item']['data'].get('masks',[])
        if not any(m['source']==sclera and m['mode']=='Mask' for m in masks):
            n.call('NodeMaskCommand_AddMask',maskSrc=sclera,mode='Mask',context={'nodes':[iris]})
    n.call('ViewportCommand_ResetParameters');n.save(state['output'])
    state['facial_controls_sha256']=controls['content_sha256'];state['facial_controls_template_sha256']=template['content_sha256']
    write_json(run/'native-state.json',state)
    n.open(state['output']);require_single_rig(n,state['rig_root'],state['bones'].values())
    expected={}
    for op in operations:expected.setdefault((op['parameter'],op['target']),[]).append(op)
    readback=[]
    for (name,target),ops in expected.items():
        pid=state['parameters'][name]
        b=n.invoke(['resources','read',f'resource://nijigenerate/bindings/get?parameter={pid}&target={target}&name=deform'])['item']
        if b['axisValues']!=specs[name]['axes']:raise ValueError('Saved facial axes differ from references')
        if b['interpolateMode']!='Linear':raise ValueError('Saved facial interpolation differs from references')
        error=0.
        for op in ops:
            i,j=[axis.index(value) for axis,value in zip(b['axisValues'],op['key'])]
            if not b['data']['isSet'][i][j]:raise ValueError('Missing facial expression key')
            error=max(error,float(np.max(abs(np.asarray(b['data']['values'][i][j]).ravel()-op['values']))))
        if error>.0003:raise ValueError('Saved facial field differs from compiled reference transfer')
        readback.append({'parameter':name,'target':target,'maximum_error':error,'axes':b['axisValues']})
    actual={p['name'] for p in n.find('Parameter')['items']}
    if actual&legacy:raise ValueError('Unreferenced legacy parameters remain')
    report.update(saved_readback=readback,left_right_target_sets_disjoint=True,passed=True)
    write_json(run/'facial-controls-applied.json',report)
    print('NJC saved/reopened: 7 reference facial controls, independent eyes, two axes; '+str(len(operations))+' keys verified',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--njc',required=True)
    a=p.parse_args();apply(a.run,a.njc)
