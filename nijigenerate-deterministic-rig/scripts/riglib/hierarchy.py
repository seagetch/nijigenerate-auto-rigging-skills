"""Initial material-origin hierarchy; never a post-rig compensation pass."""
from collections import defaultdict
import numpy as np
from .carrier import rotation
from .data import json_digest


def material_groups(observation, assembly, evidence):
    nodes={n['uuid']:n for n in observation['nodes']}
    roles={m['part']:dict(evidence.get('material_overrides',{}).get(str(m['part']),m)) for m in assembly['materials']}
    receivers={m['part']:m['receiver'] for m in evidence['semantic_materials'] if m.get('receiver')}
    def role(uid,seen=()):
        if uid in seen:raise ValueError('Cyclic PSD clipping receiver')
        if uid in receivers:return role(receivers[uid],(*seen,uid))
        r=dict(roles[uid]);chart=r['chart'];owner=r['owner']
        if owner=='torso' and chart=='torso/neck':chart='torso/body'
        if owner.startswith(('arm:','leg:')) and chart.split('/',1)[1] in ('hand','foot'):chart=owner+'/skin'
        r['chart']=chart
        return r
    resolved={uid:role(uid) for uid in roles};grouped=defaultdict(list);aliases={}
    for uid,r in resolved.items():
        node=nodes[uid];grouped[r['chart']].append(node)
        old=roles[uid]['chart']+'@'+nodes[node['parent']].get('source_layer_id','root')
        aliases[old]=r['chart']+'@semantic'
    return grouped,resolved,aliases


def compile_hierarchy(domains,evidence,observation,scaffold):
    nodes={n['uuid']:n for n in observation['nodes']};children=defaultdict(list)
    for n in nodes.values():children[n['parent']].append(n['uuid'])
    assigned={p['uuid']:d['id'] for d in domains for p in d['parts']}
    def chain(uid):
        result=[]
        while uid is not None:result.append(uid);uid=nodes[uid]['parent']
        return result
    common=set.intersection(*(set(chain(u)[1:]) for u in assigned))
    scope=next(u for u in chain(next(iter(assigned))) if u in common)
    def part_descendants(uid):
        return ({uid} if nodes[uid]['type']=='Part' else set()).union(*(part_descendants(c) for c in children[uid]))
    descendants={uid:part_descendants(uid) for uid in nodes}
    receiver_map={m['part']:m['receiver'] for m in evidence['semantic_materials'] if m.get('receiver')}
    receivers=set(receiver_map)
    clip_scopes=set()
    for uid,parts in descendants.items():
        if nodes[uid]['type'] not in ('Composite','DynamicComposite') or not parts:continue
        draw=nodes[uid]['draw_properties']
        if draw.get('blend_mode','Normal')!='Normal' or draw.get('opacity',1)!=1:continue
        bases=parts-receivers
        if len(bases)==1 and len(parts)>1 and all(receiver_map.get(p) in bases for p in parts-bases):clip_scopes.add(uid)
    features={m['part']:m for m in evidence['semantic_materials']}
    by_chart={d['semantic_chart']:d for d in domains}
    def anchor(domain,face=False):
        candidates=[p['uuid'] for p in domain['parts'] if p['uuid'] not in receivers]
        if face:
            facial=[u for u in candidates if features.get(u,{}).get('role')=='face']
            if facial:candidates=facial
        def area(u):
            b=nodes[u]['bounds']['nominal_world_xy'];return (b[2]-b[0])*(b[3]-b[1])
        return max(candidates,key=area)
    for d in domains:
        ids={p['uuid'] for p in d['parts']};units=set()
        for uid in ids:
            top=uid;p=nodes[top]['parent']
            while p!=scope and p is not None and p not in clip_scopes and descendants[p] and descendants[p]<=ids:
                top=p;p=nodes[p]['parent']
            units.add(top)
        d['render_units']=sorted(units,key=lambda u:nodes[u].get('source_order',0))
        d['origin_part']=anchor(d,d['semantic_chart']=='head/face')
    body=by_chart.get('torso/body')
    if body is None:
        candidates=[d for d in domains if d['owner']=='torso' and d['semantic_chart'].split('/')[1] in ('topwear_front','topwear_waist')]
        if not candidates:raise ValueError('PSD has no torso origin material')
        body=max(candidates,key=lambda d:len(d['parts']))
        body['bone_sources']=['Pelvis','Spine','Chest','Neck']
    bones={b['id']:b for b in scaffold['bones']}
    groups=[{'id':'Body::Root','parent':{'node':scope},'origin':bones['Pelvis']['head'][:2],'bone':'Pelvis'},
            {'id':'Head::Root','parent':{'node':body['origin_part']},'origin':bones['Head']['head'][:2],'bone':'Head'}]
    for family,bone in (('arm','UpperArm'),('leg','Thigh')):
        for tag,side in evidence['side_mapping'].items():
            if side not in ('L','R') or not any(d['owner']==family+':'+tag for d in domains):continue
            groups.append({'id':family.title()+'::Root::'+side,
                'parent':{'node':body['origin_part'] if family=='arm' else scope},
                'origin':bones[bone+'.'+side]['head'][:2],'bone':bone+'.'+side})
    parents={}
    for d in domains:
        owner=d['owner'];label=d['semantic_chart'].split('/',1)[1]
        if d is body:parent={'group':'Body::Root'}
        elif owner=='head':parent={'group':'Head::Root'}
        elif owner=='torso':parent={'node':body['origin_part']}
        else:
            family,tag=owner.split(':');side=evidence['side_mapping'][tag];base=by_chart.get(owner+'/skin')
            if label!='skin' and base:parent={'node':base['origin_part']}
            elif side=='Both':parent={'node':body['origin_part'] if family=='arm' else scope}
            else:parent={'group':family.title()+'::Root::'+side}
        parents[d['id']]=parent
    face=by_chart.get('head/face')
    result={'schema_version':'rig-material-origin-hierarchy/2','render_scope':scope,
        'groups':groups,'surface_parents':parents,'body_origin':body['origin_part'],
        'clipping_receivers':{str(u):v for u,v in receiver_map.items() if u in assigned and assigned[u]==assigned.get(v)},
        'face_origin':face['origin_part'] if face else None,
        'source_nodes':{str(u):{'parent':n['parent'],'matrix':n['nominal_world_matrix'],
             'zsort':sum(nodes[v]['draw_properties'].get('zsort',0) for v in chain(u)),
             'type':n['type']} for u,n in nodes.items()},
        'transform_policy':'native material inheritance; one Head origin at Head Bone; no compensating grids'}
    result['content_sha256']=json_digest(result)
    return result


def validate_hierarchy(client,state,program):
    parents={};types={}
    def visit(node,parent=None):
        if node['typeId'] in ('Parameter','Binding'):return
        uid=node['uuid'];types[uid]=node['typeId'];parents[uid]=parent
        for child in node.get('children') or []:visit(child,uid)
    for node in client.find('*')['items']:visit(node)
    spec=program['hierarchy'];groups=state['groups']
    def resolve(ref):return ref['node'] if 'node' in ref else groups[ref['group']]
    def ancestors(uid):
        chain=[]
        while uid is not None:chain.append(uid);uid=parents[uid]
        return chain
    bindings={b['target']:b for b in client.read(state['rig_root'])['item']['data']['bindings']}
    for group in spec['groups']:
        uid=groups[group['id']]
        if parents.get(uid)!=resolve(group['parent']):raise ValueError('Origin parent mismatch: '+group['id'])
        if types[uid]!='Node':raise ValueError('Anatomical origin must be an ordinary Node')
    head=groups['Head::Root'];body=spec['body_origin']
    if parents[head]!=body:raise ValueError('Head origin must inherit from the body origin Part')
    for uid in state.get('origin_composites',[]):
        if not client.read(uid)['item']['data'].get('propagate_meshgroup'):raise ValueError('Origin composite blocks inheritance')
    for d in program['domains']:
        uid=state['grids'][d['id']]
        if parents[uid]!=resolve(spec['surface_parents'][d['id']]):raise ValueError('Surface origin mismatch: '+d['id'])
        for part in d['parts']:
            chain=ancestors(part['uuid'])
            # PSD group grids and their surface share the same BoneSources.
            grid_chain=[v for v in chain if types[v]=='GridDeformer']
            if uid not in grid_chain or uid not in bindings:raise ValueError('Part has a different deformation authority')
            for v in grid_chain[:grid_chain.index(uid)]:
                if spec['source_nodes'].get(str(v),{}).get('type')!='GridDeformer':
                    raise ValueError('Unexpected Grid between material and its bone-driven surface')
                if v not in bindings or set(bindings[v]['sourceBoneUuids'])!=set(bindings[uid]['sourceBoneUuids']):
                    raise ValueError('PSD group Grid has different BoneSources')
                if bindings[v]['influenceRule']!=bindings[uid]['influenceRule']:
                    raise ValueError('PSD group Grid has a different Bone influence rule')
            if d['owner']=='head' and head not in chain:raise ValueError('Head material escaped the common Head origin')
            if d['semantic_chart']=='head/face' and spec['face_origin'] not in chain:raise ValueError('Facial mechanism escaped its face Part')
        if set(bindings[uid]['sourceBoneUuids'])!={state['bones'][b] for b in d['bone_sources']}:raise ValueError('Incorrect BoneSources')
    needed=set()
    targets=[*groups.values(),*state['bones'].values(),*[p['uuid'] for d in program['domains'] for p in d['parts']]]
    for uid in targets:needed.update(ancestors(uid))
    ids=sorted(needed);public={u:r['item']['data'] for u,r in zip(ids,client.read_many(ids))};world={}
    def matrix(uid):
        if uid in world:return world[uid]
        n=public[uid];t=n['transform'];m=np.eye(4)
        m[:2,:2]=rotation(t['rot'][2])@np.diag(t['scale']);m[:3,3]=t['trans']
        if parents[uid] is not None and not n.get('lockToRoot'):m=matrix(parents[uid])@m
        world[uid]=m;return m
    origin_errors=[]
    for g in spec['groups']:
        delta=matrix(groups[g['id']])[:2,3]-matrix(state['bones'][g['bone']])[:2,3]
        origin_errors.append({'origin':g['id'],'bone':g['bone'],'xy_error':delta.tolist()})
    part_error=max(float(np.max(abs(matrix(p['uuid'])-np.asarray(spec['source_nodes'][str(p['uuid'])]['matrix']))))
        for d in program['domains'] for p in d['parts'])
    return {'passed':True,'hierarchy_sha256':spec['content_sha256'],'group_count':len(groups),
        'surface_count':len(program['domains']),'head_origin':head,'head_origin_parent':body,
        'face_origin':spec['face_origin'],'native_material_inheritance':True,'compensation_grid_count':0,
        'origin_bone_position_observations':origin_errors,'maximum_neutral_part_matrix_error':part_error}
