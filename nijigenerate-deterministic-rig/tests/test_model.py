"""In-memory normalization and NJC transport tests; no model-file fixtures."""
from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from riglib.data import json_digest
from riglib.model import observe_metadata, observe_model, read_model_metadata


def node(uuid, kind='Node', **extra):
    return {'uuid': uuid, 'name': f'node-{uuid}', 'type': kind, 'enabled': True,
            'transform': {'trans': [0, 0, 0], 'rot': [0, 0, 0], 'scale': [1, 1]},
            'children': [], **extra}


def part(uuid=2, **extra):
    return node(uuid, 'Part', mesh={'verts': [0, 0, 1, 0, 0, 1],
                                   'indices': [0, 1, 2], 'origin': [0, 0]}, **extra)


def normalize(data, include_geometry=True):
    return observe_metadata(data, {'transport': 'in-memory-test',
                                  'metadata_sha256': json_digest(data)},
                            include_geometry=include_geometry)


class MemoryNJC:
    """Stub for the independently inspected public resource contract."""
    def __init__(self, root=None, parameters=()):
        self.root = deepcopy(root)
        self.parameters = deepcopy(list(parameters))
        self.resources = {}
        self.calls = []
        def record(item):
            self.resources[item['uuid']] = item
            for child in item.get('children', []):
                record(child)
        if self.root is not None:
            record(self.root)

    def find(self, selector):
        self.calls.append(('find', selector))
        if selector != '*':
            raise AssertionError('unexpected discovery selector')
        def item(value):
            return {'uuid': value['uuid'], 'name': value['name'], 'typeId': value['type'],
                    'data': {'uuid': value['uuid']},
                    'children': [item(child) for child in value.get('children', [])]}
        items = [item(self.root)] if self.root is not None else []
        items.extend({'uuid': p['uuid'], 'name': p['name'], 'typeId': 'Parameter', 'children': []}
                     for p in self.parameters)
        return {'items': items}

    def read(self, uid):
        self.calls.append(('read', uid))
        value = deepcopy(self.resources[uid])
        value.pop('children', None)
        return {'item': {'typeId': 'Node', 'uuid': uid, 'name': value['name'], 'data': value}}


class ModelObservationTests(unittest.TestCase):
    def test_direct_paths_and_missing_client_rejected_without_file_io(self):
        with patch('builtins.open', side_effect=AssertionError('file access forbidden')), \
                patch.object(Path, 'open', side_effect=AssertionError('file access forbidden')):
            with self.assertRaisesRegex(ValueError, 'explicit NJC client'):
                read_model_metadata()
            for path in ('missing.inx', 'missing.inp'):
                with self.assertRaisesRegex(ValueError, 'paths cannot be read'):
                    read_model_metadata(path, client=MemoryNJC(node(1)))

    def test_njc_snapshot_has_content_identity_not_file_identity(self):
        client = MemoryNJC(node(1, children=[part()]))
        with patch('builtins.open', side_effect=AssertionError('file access forbidden')), \
                patch.object(Path, 'open', side_effect=AssertionError('file access forbidden')):
            data, source = read_model_metadata(client=client)
        self.assertEqual(source['metadata_sha256'], json_digest(data))
        self.assertEqual(source['transport'], 'njc')
        self.assertEqual(source['hash_scope'], 'canonical_njc_public_metadata_snapshot')
        self.assertIsNone(source['path'])
        self.assertFalse(source['file_identity_verified'])
        self.assertFalse(source['texture_payload_read'])
        self.assertEqual(source['consistency'], 'two_identical_reads_not_atomic')
        self.assertEqual(client.calls, [('find', '*'), ('read', 1), ('read', 2)] * 2)

    def test_observe_model_uses_njc_and_preserves_hierarchy(self):
        observed = observe_model(client=MemoryNJC(node(1, children=[part()])))
        self.assertEqual(observed['node_count'], 2)
        self.assertEqual(observed['nodes'][1]['parent'], 1)
        self.assertTrue(observed['current_live_model_observed'])
        self.assertFalse(observed['model_loaded'])
        self.assertFalse(observed['model_modified'])

    def test_no_active_model_rejected(self):
        with self.assertRaisesRegex(ValueError, 'no active model'):
            read_model_metadata(client=MemoryNJC())

    def test_parameter_details_not_invented(self):
        client = MemoryNJC(node(1), [{'uuid': 20, 'name': 'pose'}])
        with self.assertRaisesRegex(ValueError, 'omit axes/bindings'):
            read_model_metadata(client=client)
        data, source = read_model_metadata(client=client, require_parameters=False)
        self.assertIsNone(data['param'])
        observed = observe_metadata(data, source)
        self.assertEqual(observed['parameter_count'], 1)
        self.assertIsNone(observed['parameters'][0]['binding_count'])
        self.assertIsNone(observed['parameters'][0]['actual_axis_values'])
        self.assertFalse(observed['parameters_complete'])

    def test_expected_snapshot_identity_checked(self):
        client = MemoryNJC(node(1))
        data, source = read_model_metadata(client=client)
        self.assertEqual(read_model_metadata(client=client,
                         expected_metadata_sha256=source['metadata_sha256'])[0], data)
        with self.assertRaisesRegex(ValueError, 'expected_metadata_sha256'):
            read_model_metadata(client=client, expected_metadata_sha256='0' * 64)

    def test_concurrent_geometry_change_rejected(self):
        class ChangingNJC(MemoryNJC):
            def read(self, uid):
                result = super().read(uid)
                if len(self.calls) > 3 and uid == 2:
                    result['item']['data']['mesh']['verts'][0] += 1
                return result
        with self.assertRaisesRegex(ValueError, 'changed during snapshot'):
            read_model_metadata(client=ChangingNJC(node(1, children=[part()])))

    def test_missing_geometry_rejected(self):
        class IncompleteNJC(MemoryNJC):
            def read(self, uid):
                result = super().read(uid)
                if uid == 2:
                    result['item']['data'].pop('mesh')
                return result
        with self.assertRaisesRegex(ValueError, 'omitted complete base mesh'):
            read_model_metadata(client=IncompleteNJC(node(1, children=[part()])))
        grid = node(3, 'GridDeformer', grid_axis_x=[0, 1], grid_axis_y=[0, 1])
        with self.assertRaisesRegex(ValueError, 'omitted axes/depth'):
            read_model_metadata(client=MemoryNJC(node(1, children=[grid])))

    def test_read_identity_mismatch_rejected(self):
        class WrongNJC(MemoryNJC):
            def read(self, uid):
                result = super().read(uid)
                result['item']['uuid'] += 1
                return result
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            read_model_metadata(client=WrongNJC(node(1)))

    def test_json_rpc_resource_envelope_supported(self):
        class EnvelopedNJC(MemoryNJC):
            @staticmethod
            def envelope(payload):
                return {'jsonrpc': '2.0', 'result': {'contents': [{'text': json.dumps(payload)}]}}
            def find(self, selector):
                return self.envelope(super().find(selector))
            def read(self, uid):
                return self.envelope(super().read(uid))
        self.assertEqual(observe_model(client=EnvelopedNJC(node(1)))['node_count'], 1)

    def test_source_identity_required_for_pure_normalizer(self):
        with self.assertRaisesRegex(ValueError, 'source hash'):
            observe_metadata({'nodes': node(1)}, {'metadata_sha256': 'bad'})

    def test_fresh_import_null_parameters_in_memory(self):
        data = {'nodes': node(1, children=[part()]), 'param': None}
        original = deepcopy(data)
        observed = normalize(data)
        self.assertEqual(observed['parameter_count'], 0)
        self.assertEqual(observed['parameters'], [])
        self.assertEqual(data, original)

    def test_invalid_parameter_collection_rejected(self):
        for value in ({}, '', 0, False):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'model param must be an array'):
                normalize({'nodes': node(1), 'param': value})

    def test_full_affine_chain(self):
        child = part(transform={'trans': [1, 2, 0], 'rot': [0, 0, 0], 'scale': [1, 1]})
        root = node(1, children=[child], transform={'trans': [10, 20, 0],
                         'rot': [0, 0, math.pi / 2], 'scale': [2, 3]})
        item = normalize({'nodes': root})['nodes'][1]
        for actual, expected in zip(item['bounds']['nominal_world_xy'], [1, 22, 4, 24]):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(item['bounds']['status'], 'nominal_affine_unverified_rotation')
        self.assertFalse(item['bounds']['rendered_world_exact'])

    def test_out_of_plane_rotation_not_ignored(self):
        root = node(1, children=[part()], transform={'trans': [0, 0, 0],
                   'rot': [0, math.pi / 2, 0], 'scale': [1, 1]})
        bounds = normalize({'nodes': root})['nodes'][1]['bounds']
        self.assertAlmostEqual(bounds['nominal_world_xy'][2], 0)
        self.assertEqual(bounds['status'], 'nominal_affine_unverified_rotation')

    def test_shared_grid_and_enabled_explicit(self):
        grid = node(3, 'GridDeformer', children=[part()], grid_axis_x=[0, 2],
                    grid_axis_y=[0, 3], depths=[0, 1, 2, 3], formation='Bilinear', dynamic=False)
        result = normalize({'nodes': node(1, enabled=False, children=[grid])})
        item = result['nodes'][2]
        self.assertEqual(item['closest_ancestor_grid'], 3)
        self.assertEqual(item['ancestor_grids'], [3])
        self.assertTrue(item['enabled_local'])
        self.assertFalse(item['enabled_inherited'])
        self.assertFalse(item['enabled_effective'])
        self.assertIn('inherited deformers are not evaluated', item['bounds']['reasons'])

    def test_lock_to_root_unknown_bounds(self):
        result = normalize({'nodes': node(1, lockToRoot=True, children=[part()])})
        self.assertIsNone(result['nodes'][1]['bounds']['nominal_world_xy'])
        self.assertEqual(result['nodes'][1]['bounds']['status'], 'unknown')

    def test_mesh_origin_recorded_not_guessed(self):
        child = part()
        child['mesh']['origin'] = [4, 5]
        item = normalize({'nodes': node(1, children=[child])})['nodes'][1]
        self.assertEqual(item['mesh']['origin'], [4, 5])
        self.assertFalse(item['mesh']['origin_applied'])
        self.assertTrue(any('origin' in reason for reason in item['bounds']['reasons']))

    def test_actual_axis_values_in_memory(self):
        parameter = {'uuid': 20, 'name': 'pose', 'is_vec2': True,
                     'min': [-2, -4], 'max': [6, 8], 'defaults': [0, 0],
                     'axis_points': [[0, .25, 1], [0, .5, 1]], 'bindings': []}
        observed = normalize({'nodes': node(1), 'param': [parameter]})['parameters'][0]
        self.assertEqual(observed['actual_axis_values'], [[-2, 0, 6], [-4, 2, 8]])

    def test_duplicate_uuid_invalid_mesh_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate node UUID'):
            normalize({'nodes': node(1, children=[part(1)])})
        child = part()
        child['mesh']['indices'] = [0, 1, 20]
        with self.assertRaisesRegex(ValueError, 'index'):
            normalize({'nodes': node(1, children=[child])})


if __name__ == '__main__':
    unittest.main()
