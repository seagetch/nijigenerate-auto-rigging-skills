"""Compile and apply PSD-derived secondary motion through NJC only.

An explicit --out makes a development model using NJC SaveFile, preserving the
input run. Default invocation is a finishing stage of the PSD rig pipeline.
"""
import argparse
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from riglib.data import read_json, write_json, json_digest, digest
from riglib.live import Live, created_id
from riglib.physics_structure import compile_structure
from riglib.physics_fields import displacement, protect_triangles, no_inversion, field_weight
from riglib.carrier import rotation
from build_native import require_single_rig


KEYS = [(x,y) for x in (-1,0,1) for y in (-1,0,1)]


def census(n):
    nodes = {}; parents = {}
    def visit(rows, parent=None):
        for row in rows:
            if row['typeId'] in ('Binding','Parameter'):continue
            uid=row['uuid'];nodes[uid]=n.read(uid)['item']['data'];parents[uid]=parent
            visit(row.get('children') or [],uid)
    visit(n.find('*')['items'])
    return nodes, parents


def matrices(nodes, parents):
    result={}
    def world(uid):
        if uid in result:return result[uid]
        d=nodes[uid];tr=d['transform']
        if any(tr['rot'][:2]) or d.get('pinToMesh'):
            raise ValueError('Unsupported neutral physics coordinate frame')
        local=np.eye(3);local[:2,:2]=rotation(tr['rot'][2])@np.diag(tr['scale'][:2]);local[:2,2]=tr['trans'][:2]
        parent=parents[uid]
        if parent is not None and not d.get('lockToRoot'):local=world(parent)@local
        result[uid]=local;return local
    for uid in nodes:world(uid)
    return result


def bindings(n):
    result={}
    for descriptor in n.binding_resources():
        b=n.invoke(['resources','read',descriptor['uri']])['item']
        result[(b['parameter']['uuid'],b['target']['uuid'],b['name'])]=b
    return result


def read_binding(n, pid, uid):
    return n.read(f'resource://nijigenerate/bindings/get?parameter={pid}&target={uid}&name=deform')['item']


def pause(n, pid):
    # Explicit arm command disables global drivers in the editor. Assignment
    # changes never occur after TogglePhysics until the whole pass is complete.
    n.call('ParameditCommand_SetArmedParameterAndKeypoint',context={'armedParameters':[pid],'parameterValue':[0,0]})


def sample_authored_host(host, key, anchor, nodes, transforms):
    """Sample the actual generated host key on its existing NJC triangles."""
    uid=host['target'];d=nodes[uid];v=np.asarray(d['mesh']['verts']).reshape(-1,2)
    transform=transforms[uid];p=v@transform[:2,:2].T+transform[:2,2]
    op=next(o for o in host['operations'] if o['target']==uid and o['key']==list(key))
    values=np.asarray(op['values']).reshape(-1,2)@transform[:2,:2].T;q=np.asarray(anchor)
    for face in np.asarray(d['mesh']['indices']).reshape(-1,3):
        a,b,c=p[face];matrix=np.column_stack((b-a,c-a))
        if abs(np.linalg.det(matrix))<1e-8:continue
        uv=np.linalg.solve(matrix,q-a);weights=np.r_[1-uv.sum(),uv]
        if weights.min()>=-1e-6:return weights@values[face]
    # A proximal alpha point can sit just outside the mesh margin. Use the
    # nearest existing vertex instead of inventing a detached host motion.
    return values[np.argmin(np.linalg.norm(p-q,axis=1))]


def compile_operations(structure, assets, nodes, transforms, policy):
    operations=[];checks=[];groups=[]
    for source in structure['groups']:
        spec=dict(source);spec['operations']=[];spec['checks']=[]
        spec['targets']=[]
        for uid in source['targets']:
            d=nodes[uid]
            if d['type']!='Part' or any(d['mesh']['origin']):raise ValueError('Physics requires verified zero-origin NJC Part mesh')
            v=np.asarray(d['mesh']['verts'],float).reshape(-1,2);linear=transforms[uid][:2,:2]
            p=v@linear.T+transforms[uid][:2,2]
            if not np.isfinite(p).all() or np.linalg.cond(linear)>1e8:raise ValueError('Invalid physics frame')
            # Re-register alpha observations to actual rest Part UVs. Model-space
            # geometry is independently checked against the PSD bounds below.
            w=field_weight(spec,p,policy)
            # Check every existing mesh face against the dense PSD protection
            # region. Vertex-only masks miss a skin patch inside a coarse face.
            asset=assets[uid];cloud=asset['points']
            # A separate cloth Part may interpolate over the inferred arm tube
            # without moving the underlying anatomy. Dense face protection is
            # mandatory for a combined skin/cloth Part and for attachment bands.
            dense_spec=dict(spec)
            if not spec.get('mixed_anatomy_cloth'):
                dense_spec['limb']=None;dense_spec['protected_pixels']=[]
            fixed=field_weight(dense_spec,cloud,policy)<=1e-12
            mask=np.zeros(asset['mask'].shape,bool);mask[asset['mask']]=fixed
            lo=np.asarray(asset['layer']['bounds'][:2],float)
            # source_to_model is a common translation in this PSD pipeline.
            # Registration is verified against alpha bounds, not copied pixels.
            shift=cloud.min(axis=0)-np.c_[np.nonzero(asset['mask'])[1],np.nonzero(asset['mask'])[0]].min(axis=0)-lo-.5
            pixel=p-shift-lo-.5;faces=np.asarray(d['mesh']['indices'],int).reshape(-1,3);fixed_vertices=set()
            for face in faces:
                q=pixel[face];mn=np.floor(q.min(axis=0)).astype(int);mx=np.ceil(q.max(axis=0)).astype(int)
                mn=np.maximum(mn,0);mx=np.minimum(mx,[mask.shape[1]-1,mask.shape[0]-1])
                if np.any(mx<mn):continue
                size=mx-mn+1;im=Image.new('1',tuple(size));ImageDraw.Draw(im).polygon([tuple(a-mn) for a in q],fill=1)
                if np.any(np.asarray(im)&mask[mn[1]:mx[1]+1,mn[0]:mx[0]+1]):fixed_vertices.update(map(int,face))
            values=[]
            for key in KEYS:
                delta=protect_triangles(displacement(spec,p,key,policy),p,d['mesh']['indices'],dense_spec,policy)
                delta[w<=1e-12]=0
                if fixed_vertices:delta[list(fixed_vertices)]=0
                values.append(delta@np.linalg.inv(linear).T)
            # Common amplitude reduction protects the existing mesh topology.
            scale=1.
            while scale>=1/128 and not all(no_inversion(v,d['mesh']['indices'],a*scale) for a in values):scale*=.5
            if scale<1/128:raise ValueError('Physics field cannot preserve existing mesh topology')
            for key,value in zip(KEYS,values):
                local=np.round(value*scale,6)
                if not no_inversion(v,d['mesh']['indices'],local):raise ValueError('Quantized physics key inverts a face')
                spec['operations'].append({'target':uid,'key':list(key),'values':local.ravel().tolist()})
            moving=int(np.any(abs(values[0]*scale)>1e-6,axis=1).sum())
            if not moving:
                spec['operations']=[op for op in spec['operations'] if op['target']!=uid]
                row=next(r for r in structure['inventory'] if r['target']==uid)
                row.update(decision='exclude' if uid!=source['target'] else 'unresolved',
                           reason='Existing mesh has no resolved free vertices; retain fully fixed region')
                continue
            spec['targets'].append(uid)
            spec['checks'].append({'target':uid,'moving_vertices':moving,'fixed_vertices':int((w==0).sum()),
                                   'amplitude_topology_scale':scale,'triangles_preserved':True,
                                   'neutral_zero':True,'maximum_displacement':float(max(np.linalg.norm(a*scale,axis=1).max() for a in values))})
        if source['target'] not in spec['targets']:
            continue
        groups.append(spec);operations.extend(spec['operations']);checks.extend(spec['checks'])
    # Carrier bindings are additional targets of the host parameter. Child
    # shape stays intact under the inherited attachment translation. Its own
    # binding has zero displacement at the same attachment band.
    by_id={g['id']:g for g in groups}
    for child in groups:
        host=by_id.get(child.get('support_group'))
        if host is None:continue
        for uid in child['targets']:
            if uid in host['targets']:continue
            d=nodes[uid];v=np.asarray(d['mesh']['verts']).reshape(-1,2);linear=transforms[uid][:2,:2]
            carried=[]
            for key in KEYS:
                delta=sample_authored_host(host,key,child['support_anchor'],nodes,transforms)
                local=np.repeat((delta@np.linalg.inv(linear).T)[None,:],len(v),axis=0)
                op={'target':uid,'key':list(key),'values':np.round(local,6).ravel().tolist(),'carried':True}
                carried.append(op)
            if not any(any(op['values']) for op in carried):continue
            host['operations'].extend(carried);operations.extend(carried)
            host['targets'].append(uid)
    return groups,operations,checks


def verify_keys(n, groups, identities):
    report=[]
    for g in groups:
        pid=identities[g['id']]['parameter'];targets={op['target'] for op in g['operations']}
        for uid in targets:
            b=read_binding(n,pid,uid)
            vertices=np.asarray(n.read(uid)['item']['data']['mesh']['verts']).reshape(-1)
            maximum_error=0.;maximum_tolerance=0.
            if b['axisValues'] != [[-1,0,1],[-1,0,1]]:raise ValueError('Physics axes differ from plan')
            for op in (o for o in g['operations'] if o['target']==uid):
                x,y=[[-1,0,1].index(v) for v in op['key']]
                if not b['data']['isSet'][x][y]:raise ValueError('Missing physics key')
                a=np.asarray(b['data']['values'][x][y]).reshape(-1);expected=np.asarray(op['values'])
                # The editor stores floats after adding displacement to mesh
                # coordinates. Large source canvases lose up to a few ULPs
                # when that addition is reversed during binding readback.
                tolerance=max(1e-4,float(np.max(np.spacing(np.float32(abs(vertices)+abs(expected)))))*2)
                error=float(np.max(abs(a-expected))) if a.shape==expected.shape else float('inf')
                if error>tolerance:raise ValueError('Physics key readback differs')
                maximum_error=max(maximum_error,error);maximum_tolerance=max(maximum_tolerance,tolerance)
            report.append({'parameter':pid,'target':uid,'axes':b['axisValues'],'isSet':b['data']['isSet'],
                           'neutral_zero':not np.any(b['data']['values'][1][1]),'nine_keys_verified':True,
                           'maximum_readback_error':maximum_error,'coordinate_float_tolerance':maximum_tolerance})
    return report


def apply(run,njc,out=None,plan_only=False,author_only=False,configure_only=False):
    run=Path(run).resolve();dest=Path(out).resolve() if out else run
    dest.mkdir(parents=True,exist_ok=True);state=read_json(run/'native-state.json')
    policy=read_json(Path(__file__).resolve().parents[1]/'structures/physics-policy.json')
    if configure_only:
        structure=read_json(dest/'physics-structure.json');assets=None
    else:
        structure,assets=compile_structure(run,policy);write_json(dest/'physics-structure.json',structure)
    if plan_only:return structure
    n=Live(njc,dest/'physics-journal')
    if configure_only:
        authored=read_json(dest/'physics-authored.json');plan=read_json(dest/'physics-program.json')
        if authored['physics_program_sha256']!=plan['content_sha256']:raise ValueError('Authored physics plan mismatch')
        if (structure['compiler_sha256']!=digest(Path(__file__).parent/'riglib/physics_structure.py')
                or plan['compiler_sha256']!=digest(Path(__file__))
                or plan['fields_sha256']!=digest(Path(__file__).parent/'riglib/physics_fields.py')
                or structure['material_roles_sha256']!=json_digest(read_json(Path(__file__).resolve().parents[1]/'structures/physics-material-roles.json'))
                or structure['policy_sha256']!=json_digest(policy)):
            raise ValueError('Physics generator changed after authored-key validation')
        nodes,parents=census(n);transforms=matrices(nodes,parents)
        baseline=read_json(dest/'physics-baseline.json')
        before={tuple(r['key']):r['binding'] for r in baseline['bindings']}
        original={int(k):v for k,v in baseline['nodes'].items()}
        return configure(n,state,plan,plan['groups'],authored['identities'],original,transforms,before,structure,dest,
                         dest/'physics-rigged.inx' if out else Path(state['output']))
    require_single_rig(n,state['rig_root'],state['bones'].values())
    n.call('ToolCommand_ModelEditMode');n.call('ViewportCommand_ResetParameters')
    from verify_physics import capture
    n.call('ViewportCommand_FitViewportToModel')
    capture(n,dest/'physics-before.png')
    nodes,parents=census(n);transforms=matrices(nodes,parents);before=bindings(n)
    groups,operations,checks=compile_operations(structure,assets,nodes,transforms,policy)
    write_json(dest/'physics-resolved-inventory.json',structure['inventory'])
    if not groups:
        report={'identities':{},'status':'no_supported_group','unresolved':[r for r in structure['inventory'] if r['decision']=='unresolved'],
                'visual_review_required':True,'rig_complete':False}
        write_json(dest/'physics-applied.json',report)
        return report
    existing={p['name']:p['uuid'] for p in n.find('Parameter')['items']}
    receipt_path=dest/'physics-applied.json';previous=read_json(receipt_path) if receipt_path.is_file() else None
    # Plan hash includes implementation and the actual existing mesh geometry.
    plan={'structure_sha256':structure['content_sha256'],'policy':policy,'groups':groups,'checks':checks,
          'compiler_sha256':digest(Path(__file__)),
          'fields_sha256':digest(Path(__file__).parent/'riglib/physics_fields.py'),
          'geometry_sha256':json_digest({str(u):nodes[u] for u in sorted({op['target'] for op in operations})})}
    plan['content_sha256']=json_digest(plan);write_json(dest/'physics-program.json',plan)
    if previous and any(g['name'] in existing for g in groups):
        if previous['physics_program_sha256']!=plan['content_sha256']:raise ValueError('Existing owned physics differs; explicit replacement required')
        verify_keys(n,groups,previous['identities']);return previous
    if any(g['name'] in existing for g in groups):raise ValueError('Unowned Physics parameter name collision')
    for op in operations:
        n.preflight_call('ModelCommand_SetDeformBinding',bindingName='deform',values=op['values'],
                         context={'parameters':[4294967295],'nodes':[op['target']],'parameterValue':op['key']})
    output=dest/'physics-rigged.inx' if out else Path(state['output'])
    n.save(dest/'physics-before.inx')
    write_json(dest/'physics-baseline.json',{'nodes':{str(k):v for k,v in nodes.items()},
                                  'bindings':[{'key':list(k),'binding':v} for k,v in before.items()]})
    identities={}
    for g in groups:
        pid=created_id(n.call('ParamCommand_Add2DParameter',min=-1,max=1));ctx={'parameters':[pid]}
        identities[g['id']]={'parameter':pid};write_json(dest/'physics-progress.json',identities)
        n.call('ParamPropCommand_SetParameterName',context=ctx,newName=g['name'])
        n.call('ParamPropCommand_ApplyParameterPropsAxes',context=ctx,min=[-1,-1],max=[1,1],axisX=[0,.5,1],axisY=[0,.5,1])
        n.call('ParameditCommand_SetStartingKeyFrame',context={'parameters':[pid],'parameterValue':[0,0]})
        pause(n,pid)
        for op in sorted(g['operations'],key=lambda o:not any(o['values'])):
            n.call('ModelCommand_SetDeformBinding',bindingName='deform',values=op['values'],
                   context={'parameters':[pid],'nodes':[op['target']],'parameterValue':op['key']})
    key_report=verify_keys(n,groups,identities);write_json(dest/'physics-keys-before-assignment.json',key_report)
    n.save(dest/'physics-authored.inx')
    authored={'physics_program_sha256':plan['content_sha256'],'identities':identities,
              'output':str(dest/'physics-authored.inx'),'visual_review_required':True,'solver_assigned':False}
    write_json(dest/'physics-authored.json',authored)
    # Endpoint verification occurs before arming the solver. Capture the entire
    # authored grid, not just one representative parameter.
    from riglib.run_options import render_images
    if render_images(run):
        from verify_physics import render_keys
        from overlay_physics import overlay_plan
        overlay_plan(n,plan,assets,dest,nodes,transforms)
        render_keys(n,groups,identities,dest)
    if author_only:
        n.save(dest/'physics-authored.inx')
        report={'physics_program_sha256':plan['content_sha256'],'identities':identities,
                'output':str(dest/'physics-authored.inx'),'visual_review_required':True,'solver_assigned':False}
        write_json(dest/'physics-authored.json',report);return report
    return configure(n,state,plan,groups,identities,nodes,transforms,before,structure,dest,output)


def configure(n,state,plan,groups,identities,nodes,transforms,before,structure,dest,output):
    policy=plan['policy'];verify_keys(n,groups,identities)
    pause(n,identities[groups[0]['id']]['parameter'])
    for g in groups:
        parent=state['bones'][g['parent_bone']]
        sid=created_id(n.call('Node_Add_SimplePhysics',context={'nodes':[parent]}));ctx={'nodes':[sid]}
        identities[g['id']]['simple_physics']=sid;write_json(dest/'physics-progress.json',identities)
        n.call('NodeCommand_SetNodeName',context=ctx,newNames=[g['name']])
        root=np.r_[g['fixed'],1]@np.linalg.inv(transforms[parent]).T
        for axis,value in zip('XY',root[:2]):n.call('Inspector_Apply_Translation'+axis,context=ctx,value=float(value))
        n.call('NodeSimplePhysicsCommand_SetSimplePhysicsParameter',context=ctx,parameter=identities[g['id']]['parameter'])
        n.call('NodeSimplePhysicsCommand_SetSimplePhysicsModelType',context=ctx,modelType='SpringPendulum')
        n.call('NodeSimplePhysicsCommand_SetSimplePhysicsMapMode',context=ctx,mapMode='XY')
        n.call('NodeSimplePhysicsCommand_SetSimplePhysicsLocalOnly',context=ctx,localOnly=False)
        settings={'Gravity':policy['settings']['gravity'],'Length':g['length'],
                  'Frequency':policy['profiles'][g['profile']]['frequency'],
                  'AngleDamping':policy['settings']['angle_damping'],'LengthDamping':policy['settings']['length_damping'],
                  'OutputScaleX':policy['settings']['output_scale'][0],'OutputScaleY':policy['settings']['output_scale'][1]}
        for key,value in settings.items():n.call('NodeSimplePhysicsCommand_SetSimplePhysics'+key,context=ctx,value=value)
        identities[g['id']]['settings']=settings;identities[g['id']]['readback']=n.read(sid)['item']
    after=bindings(n);owned={r['parameter'] for r in identities.values()}
    protected={k:v for k,v in after.items() if k[0] not in owned}
    if json_digest(list(before.values()))!=json_digest(list(protected.values())):raise ValueError('Unrelated bindings changed; refuse save')
    for g in groups:
        found={k[1] for k in after if k[0]==identities[g['id']]['parameter']}
        if found!=set(g['targets']):raise ValueError('Unexpected physics binding target')
    old_after,_=census(n)
    if any(nodes[u]!=old_after[u] for u in nodes):raise ValueError('Existing node changed; refuse save')
    n.call('ViewportCommand_ResetParameters');n.save(output)
    snapshot=json_digest(list(after.values()))
    if json_digest(list(bindings(n).values()))!=snapshot:raise ValueError('Saved bindings differ')
    key_report=verify_keys(n,groups,identities)
    report={'physics_program_sha256':plan['content_sha256'],'identities':identities,'keys':key_report,
            'output':str(output),'protected_bindings_unchanged':True,'old_nodes_unchanged':True,
            'saved_live_readback_verified':True,'assignment_drivers':'disabled via explicit armed-parameter context',
            'anatomy_targets':[],'unresolved':[r for r in structure['inventory'] if r['decision']=='unresolved'],
            'visual_review_required':True,'rig_complete':False}
    write_json(dest/'physics-applied.json',report)
    # The verification entry owns enable/playback/reset/restore and leaves the
    # inspected output paused. No blind toggle is used during assignments.
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--njc',required=True)
    p.add_argument('--out');mode=p.add_mutually_exclusive_group()
    mode.add_argument('--plan-only',action='store_true');mode.add_argument('--author-only',action='store_true')
    mode.add_argument('--configure-only',action='store_true');a=p.parse_args()
    result=apply(a.run,a.njc,a.out,a.plan_only,a.author_only,a.configure_only)
    print('Physics groups:',len(result.get('groups',result.get('identities',{}))),flush=True)
