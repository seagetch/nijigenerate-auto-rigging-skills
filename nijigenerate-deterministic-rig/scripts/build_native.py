"""Compile/apply a generated humanoid program using the live public NJC API."""
import argparse
import itertools
import math
import numpy as np
from pathlib import Path
import time
import json
from riglib.data import read_json, write_json, json_digest
from riglib.live import Live, created_id
from riglib.native_compile import compile_native
from riglib.model import read_model_metadata
from riglib.hierarchy import validate_hierarchy
from riglib.part_mesh import verify_mesh
from riglib.carrier import rotation,to_root,to_local
from riglib.resampling import native_axis_distinct


def model_structure(client):
    nodes=[]
    def visit(node,parent=None):
        if node['typeId'] in ('Parameter','Binding'):return
        if not isinstance(node.get('data'),dict):raise ValueError('Missing node census data')
        nodes.append((node['uuid'],node['typeId'],parent))
        for child in node.get('children') or []:visit(child,node['uuid'])
    for node in client.find('*')['items']:visit(node)
    if len({uid for uid,_,_ in nodes})!=len(nodes):raise ValueError('Duplicate node in structure census')
    parameters=client.find('Parameter')['items']
    return sorted(nodes),sorted(p['uuid'] for p in parameters)


def require_single_rig(client,expected_root,expected_bones):
    nodes,_=model_structure(client)
    roots=[uid for uid,kind,parent in nodes if kind=='DepthRigRoot']
    bones=[uid for uid,kind,parent in nodes if kind=='DepthBone']
    if roots!=[expected_root] or set(bones)!=set(expected_bones):
        raise RuntimeError(f'Rig structure mismatch: roots={roots}, bone count={len(bones)}')
    parents={uid:parent for uid,kind,parent in nodes}
    for bone in bones:
        cursor=bone
        while cursor is not None and cursor!=expected_root:cursor=parents[cursor]
        if cursor!=expected_root:raise RuntimeError(f'Bone {bone} is outside the single RigRoot')


def wait_for_baked_key(reader,parameter,targets,key,timeout=45):
    # The native GPU command queues work. A success response is not a commit.
    # Keep this pose unchanged until every requested target has this key.
    deadline=time.monotonic()+timeout
    pending=set(targets)
    while pending:
        for target in list(pending):
            uri=f'resource://nijigenerate/bindings/get?parameter={parameter}&target={target}&name=deform'
            result=reader.invoke(['resources','read',uri])
            item=result.get('item')
            if item is None:
                if not str(result.get('error','')).startswith('Binding not found:'):raise RuntimeError(result)
                continue
            axes=item['axisValues']
            i=next((i for i,v in enumerate(axes[0]) if abs(v-key[0])<1e-6),None)
            j=next((j for j,v in enumerate(axes[1]) if abs(v-(key[1] if len(key)>1 else 0))<1e-6),None)
            if i is not None and j is not None and item['data']['isSet'][i][j]:pending.remove(target)
        if pending:
            if time.monotonic()>deadline:raise RuntimeError(f'Deformation was not committed: parameter={parameter}, key={key}, targets={sorted(pending)}')
            time.sleep(.1)


def apply_registered_fields(n,program,state):
    """Assign absolute compiled fields, including zero keys, after native refresh.

    Prior model bindings are never a generation source. Reapplication writes
    the same program values instead of accumulating or restoring live offsets.
    """
    n.call('ToolCommand_ModelEditMode');n.call('ViewportCommand_ResetParameters')
    for spec in program['parameters']:
        if spec.get('deformation_authority')!='registered_reference_fields':continue
        uid=state['parameters'][spec['name']]
        for domain in program['domains']:
            field=domain['reference_deformations'][spec['name']]
            expected=np.array(field['values'],float).reshape(len(field['axes'][0]),len(field['axes'][1]),-1,2)
            if spec['name']=='Face::Yaw-Pitch' and domain.get('placement_offset_model_units',0):
                for i in range(expected.shape[0]):
                    for j in range(expected.shape[1]):
                        expected[i,j]+=domain['placement_offset_model_units']*np.array(state['head_depth_projection'][f'{i},{j}'])
            expected=np.round(expected,4);target=state['grids'][domain['id']]
            positions=[(i,j) for i in range(expected.shape[0]) for j in range(expected.shape[1])]
            for i,j in sorted(positions,key=lambda ij:not np.any(expected[ij])):
                n.call('ModelCommand_SetDeformBinding',bindingName='deform',values=expected[i,j].ravel().tolist(),
                    context={'parameters':[uid],'nodes':[target],
                             'parameterValue':[field['axes'][0][i],field['axes'][1][j]]})
        n.call('ViewportCommand_ResetParameters')
        print('Applied common fields '+spec['name'],flush=True)


def apply_program(program, executable, source, output, journal):
    signed=dict(program);signed.pop('content_sha256',None)
    if json_digest(signed)!=program['content_sha256']:raise ValueError('program hash mismatch')
    if program['source'].get('transport')!='njc':
        raise ValueError('Re-observe source through NJC; direct-file observations are not accepted')
    if Path(source).resolve()==Path(output).resolve():raise ValueError('source and output must differ')
    n=Live(executable,journal)
    reader=Live(executable)
    # Check generated arrays before any model operation. NJC transport limits
    # must never turn into a different communication or file-editing path.
    for domain in program['domains']:
        if not native_axis_distinct(domain['axis_x']) or not native_axis_distinct(domain['axis_y']):
            raise ValueError('Compiled Grid axes collapse under native tolerance: '+domain['id'])
        n.preflight_call('VertexCommand_DefineGrid',axisX=domain['axis_x'],axisY=domain['axis_y'],context={'nodes':[4294967295]})
        n.preflight_call('DepthMapCommand_SetDepths',target=4294967295,depths=domain['depths'])
        n.preflight_call('NodeCommand_MoveNode',newParent=4294967295,index=0,
                         context={'nodes':[part['uuid'] for part in domain['parts']]})
        for spec in domain.get('reference_deformations',{}).values():
            for i,column in enumerate(spec['values']):
                for j,values in enumerate(column):
                    n.preflight_call('ModelCommand_SetDeformBinding',bindingName='deform',values=values,
                        context={'parameters':[4294967295],'nodes':[4294967295],
                                 'parameterValue':[spec['axes'][0][i],spec['axes'][1][j]]})
    # The open command may be deferred by an application dialog. Verify the
    # actual NJC snapshot before saving or creating anything.
    n.open(source)
    _,identity=read_model_metadata(client=reader)
    if identity['metadata_sha256']!=program['source']['metadata_sha256']:
        raise ValueError('NJC source snapshot mismatch; no build mutations performed')
    for domain in program['domains']:
        for part in domain['parts']:
            verify_mesh(reader.read(part['uuid'])['item']['data'],
                        {'method':part['mesh_method'],'vertices':part['vertices'],'indices':part['indices']})
    source_structure=model_structure(reader)
    if any(kind in ('DepthRigRoot','DepthBone') for _,kind,_ in source_structure[0]):
        raise ValueError('A new build requires the designated unrigged source INX')
    n.save(output)
    if model_structure(reader)!=source_structure:
        raise RuntimeError('Open did not load the designated source; no rig nodes were created')
    n.call('ToolCommand_ModelEditMode');n.call('ViewportCommand_ResetParameters')
    state={'program_sha256':program['content_sha256'],'bones':{},'grids':{},'groups':{},'parameters':{},'output':str(Path(output).resolve())}
    for group in program['hierarchy']['groups']:
        parent=state['groups'][group['parent']] if group['parent'] else program['source_root']
        uid=created_id(n.call('NodeCommand_AddNode',className='Node',_suffix='::Group',context={'nodes':[parent]}))
        n.call('NodeCommand_SetNodeName',newNames=[group['id']],context={'nodes':[uid]})
        state['groups'][group['id']]=uid
    assigned={p['uuid'] for d in program['domains'] for p in d['parts']}
    references=[uid for uid,kind,parent in source_structure[0] if kind=='Part' and uid not in assigned]
    if references:n.call('NodeCommand_MoveNode',newParent=state['groups']['References'],index=0,context={'nodes':references})
    root=created_id(n.call('DepthBoneCommand_CreateDepthRigRoot',parent=program['source_root'],name='Rig::Humanoid'))
    state['rig_root']=root
    for bone in program['scaffold']['bones']:
        uid=created_id(n.call('DepthBoneCommand_AddDepthBone',parent=state['bones'].get(bone['parent'],root),
                             boneId=bone['id'],restHead=bone['head'],restTail=bone['tail'],restRoll=bone['rest_roll']))
        state['bones'][bone['id']]=uid
        if bone['lock_to_root']:n.call('Inspector_Apply_LockToRoot',value=True,context={'nodes':[uid]})
        n.call('DepthBoneCommand_SetDepthBoneConstraint',bone=uid,
               constraint=json.dumps({'allowParentToTargets':bone['allow_parent_to_targets']}))
        if 'pose_origin_z' in bone:
            parent_z=next((b['pose_origin_z'] for b in program['scaffold']['bones'] if b['id']==bone['parent']),0.)
            z=bone['pose_origin_z']-(0. if bone['lock_to_root'] else parent_z)
            n.call('Inspector_Apply_TranslationZ',value=z,context={'nodes':[uid]})
    n.save(output)
    require_single_rig(reader,root,state['bones'].values())
    print('Created fitted skeleton',flush=True)
    for index,domain in enumerate(program['domains']):
        parent=state['groups'][program['hierarchy']['surface_parents'][domain['id']]]
        parts=[part['uuid'] for part in domain['parts']]
        n.call('NodeCommand_MoveNode',newParent=parent,index=0,context={'nodes':parts})
        # Insert wraps an existing Part. The native command creates one wrapper
        # per selected node, so insert once and collect its sibling materials.
        gid=created_id(n.call('NodeCommand_InsertNode',className='GridDeformer',_suffix='::Surface',context={'nodes':[parts[0]]}))
        state['grids'][domain['id']]=gid
        if len(parts)>1:n.call('NodeCommand_MoveNode',newParent=gid,index=0,context={'nodes':parts[1:]})
        n.call('NodeCommand_SetNodeName',newNames=['Rig::'+domain['id']],context={'nodes':[gid]})
        settings={'mask_threshold':15,'x_segments':len(domain['axis_x'])-1,
                  'y_segments':len(domain['axis_y'])-1,'margin':.1}
        n.call('AutoMesh_SetSimple_grid',**settings)
        n.call('AutoMesh_Apply_grid',context={'nodes':[gid]})
        generated=reader.read(gid)['item']['data']
        if len(generated['grid_axis_x'])<2 or len(generated['grid_axis_y'])<2:
            raise ValueError('Grid AutoMesh returned empty axes')
        state.setdefault('grid_automesh',{})[domain['id']]={'target':gid,'processor':'grid',
            'settings':settings,'generated_axis_counts':[len(generated['grid_axis_x']),len(generated['grid_axis_y'])]}
        # Adjust the populated Grid after AutoMesh. Lock artwork while changing
        # the carrier frame, then express the same PSD positions in that frame.
        carrier=domain['carrier_frame']
        locks={uid:reader.read(uid)['item']['data']['lockToRoot'] for uid in parts}
        for uid in parts:
            if not locks[uid]:n.call('Inspector_Apply_LockToRoot',value=True,context={'nodes':[uid]})
        for axis,value in zip(('X','Y'),carrier['origin']):
            n.call('Inspector_Apply_Translation'+axis,value=value,context={'nodes':[gid]})
        n.call('Inspector_Apply_RotationZ',value=carrier['rotation'],context={'nodes':[gid]})
        n.call('VertexCommand_DefineGrid',axisX=domain['axis_x'],axisY=domain['axis_y'],context={'nodes':[gid]})
        for part in domain['parts']:
            uid=part['uuid'];original=part['original_transform']
            if not locks[uid]:
                n.call('Inspector_Apply_LockToRoot',value=False,context={'nodes':[uid]})
                position=to_local(np.asarray(original['trans'][:2]),carrier)
                for axis,value in zip(('X','Y'),position):
                    n.call('Inspector_Apply_Translation'+axis,value=float(value),context={'nodes':[uid]})
                n.call('Inspector_Apply_RotationZ',value=original['rot'][2]-carrier['rotation'],context={'nodes':[uid]})
            actual=reader.read(uid)['item']['data']
            verify_mesh(actual,{'method':part['mesh_method'],'vertices':part['vertices'],'indices':part['indices']})
            t=actual['transform'];vertices=np.asarray(part['vertices']).reshape(-1,2)
            wanted=(vertices*np.asarray(original['scale']))@rotation(original['rot'][2]).T+original['trans'][:2]
            local=(vertices*np.asarray(t['scale']))@rotation(t['rot'][2]).T+t['trans'][:2]
            current=local if locks[uid] else to_root(local,carrier)
            if actual['lockToRoot']!=locks[uid] or np.max(abs(current-wanted))>.001:
                raise ValueError('Grid adjustment changed neutral Part geometry')
        n.call('NodeCommand_MoveNode',newParent=gid,index=0,context={'nodes':parts})
        actual_grid=reader.read(gid)['item']['data']
        for actual_name,expected_name in [('grid_axis_x','axis_x'),('grid_axis_y','axis_y')]:
            a=np.asarray(actual_grid[actual_name]);b=np.asarray(domain[expected_name])
            if a.shape!=b.shape or not np.allclose(a,b,rtol=0,atol=.0003):
                raise ValueError('NJC Grid axis adjustment did not commit: '+domain['id'])
        n.call('DepthMapCommand_SetDepths',target=gid,depths=domain['depths'])
        for source_name in domain['bone_sources']:
            n.call('DepthBoneCommand_AddDepthBoneSource',root=root,target=gid,bone=state['bones'][source_name])
        # Large radius avoids undefined uncovered grid points; normalized nearest
        # bone weights are a declared native skinning policy, not anatomy claims.
        influence=domain.get('bone_influence_rule',{'maxInfluences':4,'radiusScale':2.0,'minimumRadius':1.0,'falloff':'gaussian'})
        n.call('DepthBoneCommand_SetDepthBoneInfluenceRule',root=root,target=gid,rule=json.dumps(influence))
        print(f'Surface {index+1}/{len(program["domains"])} {domain["id"]}',flush=True)
    n.save(output)
    require_single_rig(reader,root,state['bones'].values())
    write_json(Path(journal).parent/'native-state.json',state)
    write_json(Path(journal).parent/'hierarchy-applied.json',validate_hierarchy(reader,state,program))
    n.call('ViewportCommand_FitViewportToModel')
    n.call('ViewCommand_SaveScreenshot',filename=str(Path(journal).parent/'structure-neutral.png'))
    for spec in program['parameters']:
        n.call('ViewportCommand_ResetParameters')
        if spec['vec2']:
            uid=created_id(n.call('ParamCommand_Add2DParameter',min=-1,max=1))
        else:
            uid=created_id(n.call('ParamCommand_Add1DParameter',min=-1,max=1))
        state['parameters'][spec['name']]=uid
        n.call('ParamPropCommand_SetParameterName',newName=spec['name'],context={'parameters':[uid]})
        axis=[0,.25,.5,.75,1]
        n.call('ParamPropCommand_ApplyParameterPropsAxes',min=[-1,-1 if spec['vec2'] else 0],max=[1,1 if spec['vec2'] else 0],axisX=axis,axisY=axis if spec['vec2'] else [],context={'parameters':[uid]})
        keys=list(itertools.product([-1,-.5,0,.5,1],repeat=2)) if spec['vec2'] else [(x,) for x in [-1,-.5,0,.5,1]]
        for binding in spec['bindings']:
            for key in keys:
                context={'parameters':[uid],'nodes':[state['bones'][binding['bone']]],'parameterValue':list(key)}
                angle=binding['degrees']*key[binding['input']]
                if binding['axis'] in ('x','y'):
                    tool='ModelCommand_SetRotation'+binding['axis'].upper()+'Binding'
                    n.call(tool,rotationRadians=math.radians(angle),context=context)
                else:
                    n.call('ModelCommand_SetTRSBinding',translation=[],scale=[],rotationDegrees=angle,applyRotation=True,context=context)
        if spec.get('deformation_authority') in ('registered_reference_fields','native_depth_projection'):
            curves=spec['reference_curves'];length=program['reference_template']['torso_length']
            for bone in sorted({c['bone'] for c in curves}):
                fields={c['property']:c for c in curves if c['bone']==bone}
                for i,x in enumerate([-1,-.5,0,.5,1]):
                    for j,y in enumerate([-1,-.5,0,.5,1] if spec['vec2'] else [0]):
                        context={'parameters':[uid],'nodes':[state['bones'][bone]],'parameterValue':[x,y]}
                        for axis in ('x','y'):
                            prop='transform.r.'+axis
                            if prop in fields:n.call('ModelCommand_SetRotation'+axis.upper()+'Binding',
                                rotationRadians=fields[prop]['values'][i][j],context=context)
                        tr=[]
                        if any('transform.t.'+a in fields for a in ('x','y')):
                            tr=[fields['transform.t.'+a]['values'][i][j]*length if 'transform.t.'+a in fields else 0. for a in ('x','y')]
                        rz=fields.get('transform.r.z')
                        if tr or rz:n.call('ModelCommand_SetTRSBinding',translation=tr,scale=[],
                            rotationDegrees=math.degrees(rz['values'][i][j]) if rz else 0.,applyRotation=bool(rz),context=context)
            projection={}
            if spec['deformation_authority']=='registered_reference_fields' and spec['name']=='Face::Yaw-Pitch' and any(d.get('placement_offset_model_units',0) for d in program['domains']):
                face=next(d for d in program['domains'] if d['id']=='head/face')
                face_id=state['grids'][face['id']]
                points=np.array([[x,y] for y in face['axis_y'] for x in face['axis_x']])
                design=np.c_[points,face['depth_model_units'],np.ones(len(points))]
                for i,x in enumerate([-1,-.5,0,.5,1]):
                    for j,y in enumerate([-1,-.5,0,.5,1]):
                        n.call('ParameditCommand_SetArmedParameterAndKeypoint',context={'armedParameters':[uid],'parameterValue':[x,y]})
                        n.call('DepthBoneCommand_ApplyDepthBoneDeform',root=root,targets='',context={'armedParameters':[uid]})
                        wait_for_baked_key(reader,uid,state['grids'].values(),[x,y])
                        uri=f'resource://nijigenerate/bindings/get?parameter={uid}&target={face_id}&name=deform'
                        data=reader.invoke(['resources','read',uri])['item']['data']['values'][i][j]
                        target=points+np.asarray(data).reshape(-1,2)
                        matrix=np.linalg.lstsq(design,target,rcond=None)[0]
                        error=float(np.max(abs(design@matrix-target)))
                        if error>.003:raise ValueError('Head depth projection is not affine; placement transfer rejected')
                        projection[i,j]=matrix[2]
                state['head_depth_projection']={f'{i},{j}':v.tolist() for (i,j),v in projection.items()}
            n.call('ViewportCommand_ResetParameters');n.save(output)
            write_json(Path(journal).parent/'native-state.json',state)
            print('Prepared common reference drivers '+spec['name'],flush=True)
            continue
        for key in keys:
            n.call('ParameditCommand_SetArmedParameterAndKeypoint',context={'armedParameters':[uid],'parameterValue':list(key)})
            n.call('DepthBoneCommand_ApplyDepthBoneDeform',root=root,targets='',context={'armedParameters':[uid]})
            wait_for_baked_key(reader,uid,state['grids'].values(),key)
        n.call('ViewportCommand_ResetParameters')
        n.save(output)
        require_single_rig(reader,root,state['bones'].values())
        write_json(Path(journal).parent/'native-state.json',state)
        print(f'Baked {spec["name"]}',flush=True)
    apply_registered_fields(n,program,state)
    n.call('ToolCommand_ModelEditMode');n.call('ViewportCommand_ResetParameters')
    n.call('ViewportCommand_ResetParameters')
    n.save(output)
    require_single_rig(reader,root,state['bones'].values())
    write_json(Path(journal).parent/'hierarchy-applied.json',validate_hierarchy(reader,state,program))
    return state


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--observation',required=True);p.add_argument('--assembly',required=True);p.add_argument('--evidence',required=True)
    p.add_argument('--prior',default=str(Path(__file__).resolve().parents[1]/'structures'/'humanoid-prior.json'))
    p.add_argument('--program',required=True);p.add_argument('--apply',action='store_true')
    p.add_argument('--njc');p.add_argument('--source');p.add_argument('--out');p.add_argument('--journal')
    a=p.parse_args()
    program=compile_native(read_json(a.observation),read_json(a.assembly),read_json(a.evidence),read_json(a.prior))
    write_json(a.program,program)
    print(f'Compiled {len(program["domains"])} domains and {len(program["parameters"])} drivers',flush=True)
    if a.apply:
        if not all([a.njc,a.source,a.out,a.journal]):p.error('--apply requires --njc --source --out --journal')
        apply_program(program,a.njc,a.source,a.out,a.journal)


if __name__=='__main__':main()
