"""Verify a PSD import and expose an explicit root through the public NJC API."""
import argparse
from pathlib import Path
from riglib.data import read_json, write_json
from riglib.live import Live, created_id
from riglib.model import observe_model


def imported_layer_name(name):
    """Match NJC's removal of terminal PSD Unicode-string NUL padding.

    Keep the raw name in the source manifest; never normalize whitespace,
    case, punctuation, or internal NULs to hide a registration mismatch.
    """
    return name.rstrip('\x00')


def match_hierarchy(layers, items):
    """Match positional PSD identity to the native tree, including duplicate names."""
    children = {}
    for layer in layers:
        children.setdefault(layer['parent_id'], []).append(layer)
    result = []
    def visit(parent, native):
        source = sorted(children.get(parent, []), key=lambda x:x['sibling_index'])
        if len(source) != len(native):
            raise ValueError(f'PSD child census mismatch at {parent}: {len(source)} != {len(native)}')
        for layer, item in zip(source, native):
            if imported_layer_name(layer['name']) != item['name']:
                raise ValueError(f'PSD layer name mismatch at {layer["id"]}: {layer["name"]!r} != {item["name"]!r}')
            if (item['typeId'] != 'Part') != layer['is_group']:
                raise ValueError('PSD layer kind mismatch at '+layer['id'])
            result.append((layer,item))
            visit(layer['id'], item.get('children') or [])
    visit(None, items)
    return result


def annotate_observation(observation, pairs):
    by_uuid = {item['uuid']:layer for layer,item in pairs}
    for node in observation['nodes']:
        if node['uuid'] in by_uuid:
            layer=by_uuid[node['uuid']]
            node['source_layer_id']=layer['id']
            node['source_index_path']=layer['index_path']
            node['source_order']=layer['flat_order']
    return observation


def prepare(manifest_path, destination, executable):
    manifest = read_json(manifest_path)
    if manifest['status'] != 'psd_observation_ready':
        raise ValueError('PSD observation is not ready')
    out = Path(destination).resolve()
    n = Live(executable, out / 'registration-journal')
    items = n.find('*')['items']
    layers = manifest['layers']
    pairs = match_hierarchy(layers, items)
    # Isolated PSD groups are native composites; pass-through groups must not
    # introduce a render boundary. Identity is checked again after conversion.
    for layer,item in pairs:
        if layer['is_group'] and layer['blend_mode']=='pass':
            if layer['opacity_uint8']!=255:
                raise ValueError('Pass-through group opacity needs an inherited opacity adapter')
            n.call('Node_ConvertTo_Node',context={'nodes':[item['uuid']]})
    items=n.find('*')['items'];pairs=match_hierarchy(layers,items)
    layer_nodes={layer['id']:item['uuid'] for layer,item in pairs}
    for layer,item in pairs:
        if layer['clipping_base_id']:
            base=layer_nodes[layer['clipping_base_id']]
            masks=n.read(item['uuid'])['item']['data'].get('masks',[])
            if not any(m['source']==base and m['mode']=='Mask' for m in masks):
                n.call('NodeMaskCommand_AddMask',maskSrc=base,mode='Mask',context={'nodes':[item['uuid']]})
    n.call('ViewportCommand_ResetParameters')
    n.call('ViewportCommand_FitViewportToModel')
    n.call('ViewCommand_SaveScreenshot', filename=str(out/'import-neutral.png'))
    root = created_id(n.call('NodeCommand_AddNode', className='Node', _suffix='', context={'nodes':[]}))
    n.call('NodeCommand_SetNodeName', newNames=['Source::PSD'], context={'nodes':[root]})
    n.call('NodeCommand_MoveNode', newParent=root, index=0, context={'nodes':[i['uuid'] for i in items]})
    observation = annotate_observation(observe_model(client=n),pairs)
    from riglib.render_camera import create,capture
    camera=create(n,root,manifest,observation,pairs,Path(manifest_path).resolve().parent)
    write_json(out/'render-camera.json',camera)
    observation = annotate_observation(observe_model(client=n),pairs)
    parts = {r['uuid']:r for r in observation['nodes'] if r['type']=='Part'}
    blend_modes={'norm':'Normal','mul ':'Multiply','scrn':'Screen','over':'Overlay',
        'dark':'Darken','lite':'Lighten','div ':'ColorDodge','lddg':'LinearDodge',
        'idiv':'ColorBurn','hLit':'HardLight','sLit':'SoftLight','diff':'Difference',
        'smud':'Exclusion','fsub':'Subtract'}
    mapping = []
    for layer,item in pairs:
        if layer['is_group']:continue
        node = parts[item['uuid']]
        if node['enabled_effective'] != layer['visible_effective']:
            raise ValueError('Imported visibility differs from PSD')
        draw=node['draw_properties']
        if draw.get('blend_mode')!=blend_modes[layer['blend_mode']] or abs(draw.get('opacity',1)-layer['opacity_uint8']/255)>.00001:
            raise ValueError('Imported blend mode or opacity differs from PSD: '+layer['id'])
        mapping.append({'layer_id':layer['id'], 'part':item['uuid'], 'name':item['name'],
                        'source_name':layer['name'], 'index_path':layer['index_path'],
                        'parent_layer_id':layer['parent_id']})
    write_json(out/'observation.json', observation)
    write_json(out/'registration.json', {'psd_sha256':manifest['source']['sha256'],
        'mapping':mapping, 'explicit_root':root,
        'groups':[{'layer_id':l['id'],'node':i['uuid']} for l,i in pairs if l['is_group']],
        'method':'recursive positional PSD hierarchy; terminal NUL removal; native isolated groups and clipping masks',
        'implicit_puppet_root_exposed':False})
    n.save(out/'imported.inx')
    reread = annotate_observation(observe_model(client=n),pairs)
    before = [{k:v for k,v in row.items() if k!='texture_references'} for row in observation['nodes']]
    after = [{k:v for k,v in row.items() if k!='texture_references'} for row in reread['nodes']]
    if before != after:
        raise ValueError('Saved import changed observed geometry or structure')
    # Saving allocates texture atlas slots that do not exist on fresh imports.
    # The active snapshot after saving is the compiler source identity.
    write_json(out/'observation.json', reread)
    capture(n,out,out/'registered-neutral.png')
    from riglib.data import digest,json_digest
    write_json(out/'registered-neutral.json',{'file':str(out/'registered-neutral.png'),
        'sha256':digest(out/'registered-neutral.png'),'observation_sha256':json_digest(reread),
        'public_source_sha256':reread['source']['metadata_sha256'],'saved_reopen_equal':None,'save_reopen_performed':False,'saved_active_readback_verified':True})
    print('Verified PSD mapping, explicit root and saved source snapshot', flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--manifest',required=True);p.add_argument('--out',required=True);p.add_argument('--njc',required=True)
    a=p.parse_args();prepare(a.manifest,a.out,a.njc)
