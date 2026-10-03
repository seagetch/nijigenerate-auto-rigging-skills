"""Capture an explicitly designated reference through NJC, without saving it.

This is template-development evidence, never per-character runtime input.
Multiple top-level artwork roots are preserved, rather than invented away.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from riglib.data import write_json, json_digest
from riglib.live import Live


def capture(client):
    discovery = client.find('*')
    nodes, parameters, bindings = [], [], []
    seen = set()

    def walk(items, parent=None):
        for item in items:
            if item['typeId'] == 'Binding':
                continue
            uid = item['uuid']
            if uid in seen:
                raise ValueError('Duplicate resource identity')
            seen.add(uid)
            detail = client.read(uid)['item']
            if (detail['uuid'], detail['name']) != (uid, item['name']):
                raise ValueError('Discovery/detail identity mismatch')
            if item['typeId'] == 'Parameter':
                parameters.append(detail)
                continue
            nodes.append({'parent': parent, 'item': detail})
            walk(item.get('children') or [], uid)

    walk(discovery['items'])
    for descriptor in client.binding_resources():
        bindings.append(client.invoke(['resources', 'read', descriptor['uri']])['item'])
    nodes.sort(key=lambda r: r['item']['uuid'])
    parameters.sort(key=lambda r: r['uuid'])
    bindings.sort(key=lambda r: (r['parameter']['uuid'], r['target']['uuid'], r['name']))
    return {'nodes': nodes, 'parameters': parameters, 'bindings': bindings}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--njc', required=True)
    a = p.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    client = Live(a.njc)
    opened = client.open(a.model)
    write_json(out/'open-response.json', opened)
    first = capture(client)
    write_json(out/'snapshot.json', first)
    print('First capture: '+str(Counter(r['item']['data']['type'] for r in first['nodes'])), flush=True)
    second = capture(client)
    stable = json_digest(first) == json_digest(second)
    write_json(out/'identity.json', {
        'schema_version': 'designated-reference-capture/1',
        'source_path': str(Path(a.model).resolve()),
        'captured_at_utc': datetime.now(timezone.utc).isoformat(),
        'transport': 'njc', 'public_snapshot_sha256': json_digest(first),
        'repeated_read_equal': stable, 'source_saved': False,
        'complete_file_verified': False,
        'scope': 'Public node hierarchy/data, parameter resources and binding descriptors.',
        'counts': {'nodes': len(first['nodes']), 'parameters': len(first['parameters']),
                   'bindings': len(first['bindings'])}})
    if not stable:
        raise ValueError('Reference changed between reads')
    client.call('ViewportCommand_ResetParameters')
    client.call('ViewportCommand_FitViewportToModel')
    client.call('ViewCommand_SaveScreenshot', filename=str(out/'neutral.png'))
    print('Repeated capture equal; neutral rendered; source not saved.', flush=True)


if __name__ == '__main__':
    main()
