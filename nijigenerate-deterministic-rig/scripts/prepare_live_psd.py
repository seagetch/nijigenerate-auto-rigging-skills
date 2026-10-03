"""Verify a PSD import and expose an explicit root through the public NJC API."""
import argparse
from pathlib import Path
from riglib.data import read_json, write_json
from riglib.live import Live, created_id
from riglib.model import observe_model


def prepare(manifest_path, destination, executable):
    manifest = read_json(manifest_path)
    if manifest['status'] != 'psd_observation_ready':
        raise ValueError('PSD observation is not ready')
    out = Path(destination).resolve()
    n = Live(executable, out / 'registration-journal')
    items = n.find('*')['items']
    layers = manifest['layers']
    # The current selector enumerates descendants, excluding the implicit puppet
    # root. Require a verified flat import before introducing an explicit root.
    if any(r['is_group'] for r in layers):
        raise ValueError('Grouped import requires a hierarchy registration adapter')
    if (len(items) != len(layers) or any(i['typeId'] != 'Part' or i['children'] for i in items)
            or [i['name'] for i in items] != [r['name'] for r in layers]):
        raise ValueError('Live import does not match PSD index order and layer census')
    n.call('ViewportCommand_ResetParameters')
    n.call('ViewportCommand_FitViewportToModel')
    n.call('ViewCommand_SaveScreenshot', filename=str(out/'import-neutral.png'))
    root = created_id(n.call('NodeCommand_AddNode', className='Node', _suffix='', context={'nodes':[]}))
    n.call('NodeCommand_SetNodeName', newNames=['Source::PSD'], context={'nodes':[root]})
    n.call('NodeCommand_MoveNode', newParent=root, index=0, context={'nodes':[i['uuid'] for i in items]})
    observation = observe_model(client=n)
    parts = {r['uuid']:r for r in observation['nodes'] if r['type']=='Part'}
    mapping = []
    for item, layer in zip(items, layers):
        node = parts[item['uuid']]
        if node['enabled_effective'] != layer['visible_effective']:
            raise ValueError('Imported visibility differs from PSD')
        mapping.append({'layer_id':layer['id'], 'part':item['uuid'], 'name':layer['name']})
    write_json(out/'observation.json', observation)
    write_json(out/'registration.json', {'psd_sha256':manifest['source']['sha256'],
        'mapping':mapping, 'explicit_root':root,
        'method':'verified flat PSD index order; NJC explicit identity carrier',
        'implicit_puppet_root_exposed':False})
    n.save(out/'imported.inx')
    n.open(out/'imported.inx')
    reread = observe_model(client=n)
    before = [{k:v for k,v in row.items() if k!='texture_references'} for row in observation['nodes']]
    after = [{k:v for k,v in row.items() if k!='texture_references'} for row in reread['nodes']]
    if before != after:
        raise ValueError('Saved import changed observed geometry or structure')
    # Saving allocates texture atlas slots that do not exist on fresh imports.
    # The re-opened snapshot is the authoritative compiler source identity.
    write_json(out/'observation.json', reread)
    n.call('ViewCommand_SaveScreenshot', filename=str(out/'registered-neutral.png'))
    print('Verified PSD mapping, explicit root and saved source snapshot', flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--manifest',required=True);p.add_argument('--out',required=True);p.add_argument('--njc',required=True)
    a=p.parse_args();prepare(a.manifest,a.out,a.njc)
