"""Convert source PSD groups before assembly, using native Grid AutoMesh."""
from pathlib import Path
from .data import write_json
from .live import Live
from .model import observe_model


def prepare(run, njc, observation, registration, materials):
    run = Path(run)
    n = Live(njc, run/'group-mesh-journal')
    nodes = {r['uuid']: r for r in observation['nodes']}
    features = {m['part']: m.get('feature') or '' for m in materials}
    eye = {'sclera', 'iris', 'upper', 'lower', 'corner', 'fold', 'brow'}
    descendants = {r['node']: set() for r in registration['groups']}
    for row in observation['nodes']:
        if row['type'] != 'Part': continue
        parent = row['parent']
        while parent is not None:
            if parent in descendants: descendants[parent].add(row['uuid'])
            parent = nodes[parent]['parent']
    records = []
    # Children first: outer AutoMesh measures the already converted subtree.
    groups = sorted(registration['groups'], key=lambda r: len(nodes[r['node']].get('source_index_path', [])), reverse=True)
    axis = [i/10 for i in range(11)]
    for group in groups:
        uid = group['node']; parts = descendants[uid]
        kinds = {features.get(p, '') for p in parts}
        is_eye = bool(kinds) and kinds <= eye
        is_mouth = bool(kinds) and all(k.startswith('mouth') for k in kinds)
        target = 'DynamicComposite' if is_eye or is_mouth else 'GridDeformer'
        before = n.read(uid)['item']['data']
        if before['type'] != target:
            if before['type'] != 'Node': n.call('Node_ConvertTo_Node', context={'nodes': [uid]})
            n.call('Node_ConvertTo_'+target, context={'nodes': [uid]})
        record = {**group, 'name': before['name'], 'type': target,
                  'classification': 'eye' if is_eye else 'mouth' if is_mouth else 'source_group',
                  'parts': sorted(parts)}
        if target == 'GridDeformer':
            n.call('AutoMesh_SetSimple_grid', mask_threshold=1, x_segments=10, y_segments=10, margin=0.)
            n.call('AutoMesh_SetAdvanced_grid', scale_x=axis, scale_y=axis)
            n.call('AutoMesh_Apply_grid', context={'nodes': [uid]})
        after = n.read(uid)['item']['data']
        if after['type'] != target or after['transform'] != before['transform']:
            raise ValueError('PSD group conversion changed identity or coordinate frame: '+before['name'])
        if target == 'GridDeformer':
            axes = [after['grid_axis_'+a] for a in ('x', 'y')]
            if any(len(a) != 11 or any(x >= y for x, y in zip(a, a[1:])) for a in axes):
                raise ValueError('PSD group AutoMesh did not produce 10x10 cells: '+before['name'])
            record.update(processor='grid', grid_axis_x=axes[0], grid_axis_y=axes[1], cells=[10, 10])
        records.append(record)
        print('PSD group', before['name'], '->', target, '10x10' if target == 'GridDeformer' else '', flush=True)
    n.save(run/'imported.inx')
    fresh = observe_model(client=n)
    updated = {r['uuid']: r for r in fresh['nodes']}
    if set(updated) != set(nodes): raise ValueError('PSD group conversion changed node identities')
    for uid, row in updated.items():
        old = nodes[uid]
        if row['parent'] != old['parent'] or row['nominal_world_matrix'] != old['nominal_world_matrix']:
            raise ValueError('PSD group conversion moved source hierarchy: '+old['name'])
        for key in ('source_layer_id', 'source_index_path', 'source_order'):
            if key in old: row[key] = old[key]
    observation.clear(); observation.update(fresh)
    for material in materials: material['node'] = updated[material['part']]
    write_json(run/'source-group-meshes.json', {'groups': records, 'native_automesh': True,
               'source': fresh['source'], 'stage': 'initial_construction_before_assembly'})
