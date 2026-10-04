"""Preserve reference support nodes on anatomical bone paths.

Core bone names identify anatomy; they are not a whitelist of allowed ancestors.
Missing optional ancestors contribute identity motion when a shared hierarchy is
formed. Conflicting nonempty support chains are rejected instead of flattened.
"""
from collections import defaultdict
from pathlib import Path
import numpy as np
from .reference_fields import to_frame,from_frame
from .data import read_json,json_digest

SUPPORT_FIELDS=('parent','lock_to_root','allow_parent_to_targets')


def reference_support():
    template=read_json(Path(__file__).resolve().parents[2]/'structures/reference-humanoid.registered.json')
    if json_digest({k:v for k,v in template.items() if k!='content_sha256'})!=template['content_sha256']:
        raise ValueError('Reference template signature mismatch')
    return {r['bone']:r for r in template['support_skeleton']}


def support_differences(scaffold):
    expected=reference_support();bones={b['id']:b for b in scaffold['bones']}
    if set(bones)!=set(expected):raise ValueError('Scaffold bone set differs from standard support skeleton')
    return [{'bone':name,'field':key,'actual':bones[name].get(key),'expected':row[key]}
            for name,row in expected.items() for key in SUPPORT_FIELDS if bones[name].get(key)!=row[key]]


def compile_support(sources,core):
    core_names={row['bone'] for row in core}
    maps=[];paths=defaultdict(list)
    for source in sources:
        nodes=source['nodes'];parents=source['parents']
        bones={d['boneId']:d for d in nodes.values() if d['type']=='DepthBone'}
        by_uuid={d['uuid']:name for name,d in bones.items()}
        maps.append(bones)
        for row in core:
            chain=[];cursor=parents[bones[row['bone']]['uuid']]
            while cursor in by_uuid and by_uuid[cursor] not in core_names:
                chain.append(by_uuid[cursor]);cursor=parents[cursor]
            if by_uuid.get(cursor)!=row['parent']:raise ValueError('Anatomical parent differs between references')
            paths[row['bone']].append(tuple(reversed(chain)))
    graph=[];helpers={};audit={}
    for row in core:
        child=row['bone'];variants=paths[child]
        nonempty=set(path for path in variants if path)
        if len(nonempty)>1:raise ValueError('Incompatible support paths require explicit reconciliation: '+child)
        chain=next(iter(nonempty),())
        parent=row['parent']
        for helper in chain:
            observations=[(s,m[helper]) for s,m in zip(sources,maps) if helper in m]
            constraints={(bool(d['lockToRoot']),bool(d['allowParentToTargets']),float(d['restRoll'])) for _,d in observations}
            if len(constraints)!=1:raise ValueError('Auxiliary bone constraints disagree: '+helper)
            locked,inherit,roll=next(iter(constraints))
            if locked:raise ValueError('Root-locked auxiliary support needs independent anchoring')
            region=('arm/'+child.rsplit('.',1)[1].lower() if child.startswith(('UpperArm.','Forearm.','Hand.'))
                    else 'leg/'+child.rsplit('.',1)[1].lower() if child.startswith(('Thigh.','Shin.','Foot.'))
                    else 'head' if child=='Head' else 'body')
            heads=[];tails=[];rest_z=[];pose_z=[];anchored=[]
            for s,d in observations:
                f=s['frames'][region];length=s['torso_length']
                heads.append(to_frame([d['restHead'][:2]],f)[0])
                tails.append(to_frame([d['restTail'][:2]],f)[0])
                rest_z.append(np.array([d['restHead'][2],d['restTail'][2]])/length)
                pose_z.append(s['bone_z'][helper])
                anchor=next(n for n in s['nodes'].values() if n.get('boneId')==child)
                anchored.append(np.linalg.norm(np.array(d['restHead'][:2])-anchor['restHead'][:2])<=length*1e-7
                    and abs(s['bone_z'][helper]-s['bone_z'][child])<=1e-7)
            spec={'id':helper,'parent':parent,'frame':region,
                  'head':np.mean(heads,axis=0).tolist(),'tail':np.mean(tails,axis=0).tolist(),
                  'rest_z':np.mean(rest_z,axis=0).tolist(),'pose_origin_z':float(np.mean(pose_z)),
                  'lock_to_root':locked,'allow_parent_to_targets':inherit,'rest_roll':roll,
                  'head_anchor':child if all(anchored) else None}
            if helper in helpers and helpers[helper]!=spec:raise ValueError('Ambiguous auxiliary support ownership: '+helper)
            helpers[helper]=spec
            graph.append({'bone':helper,'parent':parent,'lock_to_root':locked,'allow_parent_to_targets':inherit})
            parent=helper
        graph.append({**row,'parent':parent})
        audit[child]={'reference_paths':[list(path) for path in variants],'shared_path':list(chain),
                      'missing_path_semantics':'identity transform; not a discarded observed driver'}
    # Topological order is required by the NJC node creation adapter.
    unique={row['bone']:row for row in graph};ordered=[];done=set()
    while len(done)<len(unique):
        ready=sorted(name for name,row in unique.items() if name not in done and (row['parent'] is None or row['parent'] in done))
        if not ready:raise ValueError('Cyclic or disconnected support skeleton')
        for name in ready:ordered.append(unique[name]);done.add(name)
    return ordered,list(helpers.values()),audit


def install_support(scaffold,template,frames,torso):
    bones={b['id']:b for b in scaffold['bones']}
    for spec in template['support_bones']:
        xy=from_frame([spec['head'],spec['tail']],frames[spec['frame']])
        z=np.array(spec['rest_z'])*torso
        head=[*xy[0],z[0]];tail=[*xy[1],z[1]]
        pose_z=spec['pose_origin_z']*torso
        if spec['head_anchor'] is not None:
            anchor=bones[spec['head_anchor']]
            delta=np.array(anchor['head'][:2])-xy[0]
            head[:2]=anchor['head'][:2];tail[:2]=(xy[1]+delta).tolist()
            pose_z=anchor['pose_origin_z']
        bones[spec['id']]={'id':spec['id'],'head':head,'tail':tail,'rest_roll':spec['rest_roll'],
                           'pose_origin_z':pose_z}
    # These options come from ngAddStandardDepthSkeleton in exdepthbone.d,
    # independently of the registered reference's two Arm.Hang auxiliaries.
    for name,bone in bones.items():
        if name.startswith('Arm.Hang.'):continue
        standard_locked=name in ('Foot.L','Foot.R')
        row=next(r for r in template['support_skeleton'] if r['bone']==name)
        if row['lock_to_root']!=standard_locked or row['allow_parent_to_targets']!=(name!='Head'):
            raise ValueError('Registered DepthBone options conflict with native Standard Template: '+name)
    ordered=[]
    for row in template['support_skeleton']:
        bone=bones[row['bone']]
        bone.update({key:row[key] for key in ('parent','lock_to_root','allow_parent_to_targets')})
        ordered.append(bone)
    if {b['id'] for b in ordered}!=set(bones):raise ValueError('Unmapped scaffold bone')
    # The standard Head excludes parent motion from its targets. Preserve that
    # separation instead of inferring a different rule from the anatomical tree.
    scaffold['support_constraint_authority']='reference support hierarchy; native standard Head/feet options; no post-install overrides'
    scaffold.pop('head_support_inheritance',None)
    scaffold['bones']=ordered
