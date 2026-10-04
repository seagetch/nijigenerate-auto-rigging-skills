"""Initial eye/mouth DynamicComposite grouping and native Grid AutoMesh."""
from .live import created_id
from .part_mesh import captured_mesh,verify_mesh


def build(tree,evidence,policy):
    n=tree.n;face=tree.spec['face_origin']
    if face is None:return []
    groups=[('Eye::'+e['side']+'::Composite','eye',set(u for k,v in e['part_groups'].items() if k!='brow' for u in v))
            for e in evidence.get('eyes',[])]
    mouth=evidence.get('mouth')
    if mouth:groups.append(('Mouth::Composite','mouth',set(mouth['parts'])))
    def chain(uid):
        result=[]
        while uid is not None:
            result.append(uid);uid=tree.parents[uid]
        return result
    rows=[]
    for name,role,parts in groups:
        if not parts:continue
        common=set.intersection(*(set(chain(u)) for u in parts))
        candidates=[u for u in chain(next(iter(parts))) if u in common and u!=face
                    and face in chain(u) and tree.source.get(str(u),{}).get('type')=='DynamicComposite'
                    and u not in tree.state.get('origin_composites',[])]
        if candidates:
            uid=candidates[0];created=False
            # A PSD may intentionally composite both eyes together. Keep that
            # render boundary and generate its mesh once, rather than replacing
            # the first eye's native mesh when visiting the other semantic eye.
            prior=next((row for row in rows if row['target']==uid),None)
            if prior is not None:
                prior['parts']=sorted(set(prior['parts'])|parts)
                prior['semantic_groups'].append(name)
                continue
        else:
            units=set()
            for part in parts:
                unit=part
                while tree.parents[unit]!=face:
                    parent=tree.parents[unit]
                    contained={p for p in tree.parents if tree.source.get(str(p),{}).get('type')=='Part' and parent in chain(p)}
                    if not contained<=parts:break
                    unit=parent
                units.add(unit)
            ordered=sorted(units)
            uid=created_id(n.call('NodeCommand_InsertNode',className='DynamicComposite',_suffix='::Mechanism',context={'nodes':[ordered[0]]}))
            n.call('NodeCommand_SetNodeName',newNames=[name],context={'nodes':[uid]})
            # Match the face frame while preserving every material's world
            # transform and draw order. This precedes all parameter bindings.
            tree.place(uid,face,tree.world[face],tree.z[face])
            for unit in ordered:tree.place(unit,uid)
            created=True
        spec=policy['roles'][role];simple=spec['simple'];advanced=spec['advanced']
        before=n.read(uid)['item']['data']
        n.call('AutoMesh_SetSimple_grid',**simple)
        n.call('AutoMesh_SetAdvanced_grid',**advanced)
        n.call('AutoMesh_Apply_grid',context={'nodes':[uid]})
        after=n.read(uid)['item']['data'];mesh=captured_mesh(after)
        if after['type']!='DynamicComposite' or after.get('auto_resized'):
            raise RuntimeError('Native Composite AutoMesh did not retain its generated mesh: '+name)
        if before['transform']!=after['transform']:
            raise RuntimeError('Composite AutoMesh changed its coordinate frame: '+name)
        rows.append({'target':uid,'name':after['name'],'semantic_groups':[name],
                     'role':role,'created':created,'parts':sorted(parts),
                     'processor':'grid','simple':simple,'advanced':advanced,'mesh':mesh,
                     'auto_resized':after['auto_resized'],'policy_authority':policy['authority']})
        print('DynamicComposite AutoMesh',name,mesh['vertex_count'],'vertices',mesh['triangle_count'],'triangles',flush=True)
    for row in rows:verify_mesh(n.read(row['target'])['item']['data'],row['mesh'])
    return rows
