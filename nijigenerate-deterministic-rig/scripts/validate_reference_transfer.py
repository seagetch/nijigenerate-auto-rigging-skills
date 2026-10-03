"""Read back the common template's depth and all core deformation keys via NJC."""
import argparse
from pathlib import Path
import numpy as np
from riglib.data import read_json, write_json, json_digest
from riglib.live import Live
from riglib.reference_fields import sample, CORE_PARAMETERS
from build_native import require_single_rig, model_structure


def validate(run,njc):
    run=Path(run);p=read_json(run/'program.json');state=read_json(run/'native-state.json')
    evidence=read_json(run/'evidence.json');n=Live(njc,run/'reference-readback-journal')
    require_single_rig(n,state['rig_root'],state['bones'].values())
    structure,_=model_structure(n);parents={uid:parent for uid,kind,parent in structure}
    for bone in p['scaffold']['bones']:
        uid=state['bones'][bone['id']]
        parent=state['bones'].get(bone['parent'],state['rig_root'])
        if parents[uid]!=parent:raise ValueError('Saved bone tree differs from the common skeleton')
        data=n.read(uid)['item']['data']
        if bool(data['lockToRoot'])!=bone['lock_to_root']:raise ValueError('Bone root-lock constraint differs')
        if bool(data['allowParentToTargets'])!=bone['allow_parent_to_targets']:
            raise ValueError('Bone parent-target constraint differs from shared reference support')
    available={}
    for resource in n.binding_resources():
        b=n.invoke(['resources','read',resource['uri']])['item']
        if b['parameter']['name'] in CORE_PARAMETERS:available[b['target']['uuid'],b['parameter']['name'],b['name']]=b
    report={'template_sha256':p['reference_template']['sha256'],'grid_count':len(p['domains']),
            'maximum_depth_error':0.,'maximum_deformation_error':0.,'keys_verified':0,'depth_order':[],
            'bone_tree_and_constraints_verified':True,'bone_source_mappings_verified':0}
    root=n.read(state['rig_root'])['item']['data']
    source_bindings={b['target']:b for b in root['bindings']}
    live={}
    for d in p['domains']:
        uid=state['grids'][d['id']];node=n.read(uid)['item']['data'];live[d['id']]=node
        binding=source_bindings.get(uid)
        if binding is None:raise ValueError('Grid is not bound to DepthRigRoot: '+d['id'])
        actual={s['bone']:s for s in binding['sourceSettings']}
        expected={state['bones'][name] for name in d['bone_sources']}
        if set(actual)!=expected:raise ValueError('Grid BoneSources differ from shared program: '+d['id'])
        for setting in actual.values():
            if not all(abs(setting[key]-value)<=1e-6 for key,value in
                       [('weight',1.),('depthScale',1.),('depthOffset',0.),('rotation',0.)]):
                raise ValueError('Grid source plane or weight differs from compiled depth: '+d['id'])
        if 'bone_influence_rule' in d and binding['influenceRule']!=d['bone_influence_rule']:
            raise ValueError('Grid influence rule differs from shared references: '+d['id'])
        report['bone_source_mappings_verified']+=1
        for key,field in [('axis_x','grid_axis_x'),('axis_y','grid_axis_y'),('depths','depths')]:
            a=np.asarray(d[key]);b=np.asarray(node[field])
            if a.shape!=b.shape or np.max(abs(a-b))>.0003:raise ValueError('Reference geometry readback mismatch: '+d['id'])
        report['maximum_depth_error']=max(report['maximum_depth_error'],float(max(abs(np.array(node['depths'])-d['depths']))))
        for parameter,field in d['reference_deformations'].items():
            binding=available.get((uid,parameter,'deform'))
            if binding is not None and binding['axisValues']!=field['axes']:raise ValueError('Core binding axes differ')
            for i,column in enumerate(field['values']):
                for j,values in enumerate(column):
                    expected=np.array(values).reshape(-1,2)
                    if parameter=='Face::Yaw-Pitch' and d.get('placement_offset_model_units',0):
                        expected+=d['placement_offset_model_units']*np.array(state['head_depth_projection'][f'{i},{j}'])
                    if binding is None:
                        if np.max(abs(expected))>.0001:raise ValueError('Missing nonzero core binding: '+d['id'])
                        continue
                    if not binding['data']['isSet'][i][j]:raise ValueError('Uncommitted core key')
                    actual=np.array(binding['data']['values'][i][j]).reshape(-1,2)
                    err=float(np.max(abs(actual-expected)));report['maximum_deformation_error']=max(report['maximum_deformation_error'],err)
                    if err>.0003:raise ValueError('Core deformation differs from registered template: '+d['id']+' '+parameter)
                    report['keys_verified']+=1
    for constraint in evidence['depth_order_constraints']:
        front=live[constraint['front']];back=live[constraint['back']];xy=constraint['xy_model']
        a=sample(front['grid_axis_x'],front['grid_axis_y'],front['depths'],xy)[:,0]*p['native_depth_scale']
        b=sample(back['grid_axis_x'],back['grid_axis_y'],back['depths'],xy)[:,0]*p['native_depth_scale']
        minimum=float(np.min(a-b))
        if minimum<=0:raise ValueError('Saved hair depth is behind face at measured opaque overlap')
        report['depth_order'].append({'front':constraint['front'],'back':constraint['back'],
            'overlap_pixels':len(xy),'minimum_front_gap_model_units':minimum})
    bone_count=0
    for spec in p['parameters']:
        for curve in spec.get('reference_curves',[]):
            b=available[state['bones'][curve['bone']],spec['name'],curve['property']]
            expected=np.array(curve['values'])
            if curve['units']=='torso_length':expected*=p['reference_template']['torso_length']
            if not np.asarray(b['data']['isSet']).all() or not np.allclose(expected,b['data']['values'],rtol=0,atol=.0003):
                raise ValueError('Saved bone driver differs from common template')
            bone_count+=1
    material_path=run/'reference-material-program.json'
    material_keys=0
    if 'reference_material_program_sha256' in state:
        materials=read_json(material_path);uv=read_json(run/'source-uv-program.json')
        if materials['content_sha256']!=state['reference_material_program_sha256']:raise ValueError('Material program hash mismatch')
        scales={op['target']:np.array(op['local_coordinate_scale']) for op in uv['parts']}
        for op in materials['operations']:
            b=available[op['part'],op['parameter_name'],'deform']
            i,j=[next(k for k,v in enumerate(axis) if abs(v-x)<1e-6) for axis,x in zip(b['axisValues'],op['key'])]
            expected=np.array(op['values']).reshape(-1,2)*scales[op['part']]
            actual=np.array(b['data']['values'][i][j]).reshape(-1,2)
            if not b['data']['isSet'][i][j] or np.max(abs(expected-actual))>.0003:raise ValueError('Saved Part correction differs from common template transfer')
            material_keys+=1
    report['material_keys_verified']=material_keys
    from bake_depth_angles import validate as validate_depth_angles
    report['depth_angles']=validate_depth_angles(run,n,available)
    report['bone_curves_verified']=bone_count;report['passed']=True
    report['program_sha256']=p['content_sha256'];report['content_sha256']=json_digest(report)
    write_json(run/'validation/reference-transfer-readback.json',report)
    print('Verified common reference transfer:',report['keys_verified'],'surface keys;',bone_count,'bone curves; depth ordering passed')


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--run',required=True);a.add_argument('--njc',required=True)
    args=a.parse_args();validate(args.run,args.njc)
