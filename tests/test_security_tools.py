import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sanitize_png', ROOT / 'tools/sanitize_png.py')
png = importlib.util.module_from_spec(spec)
spec.loader.exec_module(png)


def chunk(kind, payload=b''):
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff)


class SecurityTools(unittest.TestCase):
    def test_png_metadata_is_removed_but_image_data_and_color_are_preserved(self):
        ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0))
        image = chunk(b'IDAT', zlib.compress(b'\0\xff\0\0\xff'))
        color = chunk(b'sRGB', b'\0')
        end = chunk(b'IEND')
        metadata = b''.join(chunk(k, b'private-test-data') for k in png.PRIVATE_CHUNKS)
        source = png.SIGNATURE + ihdr + metadata + color + image + end + b'private-trailer'
        result, removed = png.sanitize(source)
        self.assertEqual(result, png.SIGNATURE + ihdr + color + image + end)
        self.assertEqual(len(removed), len(png.PRIVATE_CHUNKS) + 1)
        self.assertEqual(png.sanitize(result), (result, []))
        with self.assertRaises(ValueError):
            png.sanitize(source[:25])

    def test_installers_refuse_existing_and_symlink_destinations(self):
        checklist = ROOT / 'nijigenerate-checklist-review-loop/scripts/bin/install_checklist_reviewer.sh'
        viewer = ROOT / 'nijigenerate-work-review-tool/scripts/install-review-viewer.mjs'
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            sentinel = project / 'sentinel.txt'
            sentinel.write_text('do not change')
            for args in [['bash', str(checklist), str(project)], ['node', str(viewer), '--project', str(project), '--viewer', '.'], ['node', str(viewer), '--project', str(project), '--viewer', '..']]:
                result = subprocess.run(args, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(sentinel.read_text(), 'do not change')
            linked = project / 'linked'
            linked.symlink_to(project, target_is_directory=True)
            result = subprocess.run(['bash', str(checklist), str(linked / 'child')], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((project / 'child').exists())
            for args, dest in [(['bash', str(checklist), str(project / 'checklist')], project / 'checklist'), (['node', str(viewer), '--project', str(project)], project / 'review-viewer')]:
                result = subprocess.run(args, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue((dest / 'package.json').exists())
                self.assertTrue((dest / 'review-security.mjs').exists())
                self.assertFalse((dest / 'node_modules').exists())
                (dest / 'private.txt').write_text('keep')
                result = subprocess.run(args, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((dest / 'private.txt').read_text(), 'keep')
                self.assertNotIn(str(project), result.stdout + result.stderr)

    def test_anonymized_example_has_no_local_home_paths(self):
        file = ROOT / 'nijigenerate-post-rig-adjustment/references/examples/ao-angle-reference-history.json'
        data = file.read_text()
        json.loads(data)
        self.assertNotIn('/Users/', data)
        self.assertNotIn('CloudStorage', data)
        self.assertNotIn('OneDrive', data)


if __name__ == '__main__':
    unittest.main()
