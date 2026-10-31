import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

import numpy as np
from lut import Cube
from pf3_native import (
    GRID, MAGIC, SIZES, STYLE_IDS, TABLE_BYTES, TABLE_ID_A, TABLE_ID_B,
    make_canon_grid, make_properties, validate_envelope,
)


def cube_of_size_2(fn):
    axis = np.linspace(0., 1., 2, dtype=np.float32)
    matrix = np.stack(np.meshgrid(axis, axis, axis, indexing='ij'), -1)
    return Cube(fn(matrix), np.zeros(3), np.ones(3), 'test')


class CanonTableTests(unittest.TestCase):
    def test_table_identity_at_grid_nodes_and_channel_order(self):
        cube = cube_of_size_2(lambda arr: arr)
        blob = make_canon_grid(cube)
        self.assertEqual(len(blob), TABLE_BYTES)
        self.assertEqual(struct.unpack_from('<HHH', blob), (12, 3, 33))
        nodes = np.frombuffer(blob[6:], dtype='<u2').reshape(GRID, GRID, GRID, 3)
        np.testing.assert_array_equal(nodes[0, 0, 0], [0, 0, 0])
        np.testing.assert_array_equal(nodes[32, 32, 32], [4095, 4095, 4095])
        np.testing.assert_array_equal(nodes[32, 0, 0], [4095, 0, 0])
        np.testing.assert_array_equal(nodes[0, 32, 0], [0, 4095, 0])
        np.testing.assert_array_equal(nodes[0, 0, 32], [0, 0, 4095])
        self.assertTrue(np.all(nodes[:, 0, 0, 0] >= 0))

    def test_strength_zero_is_identity_even_with_inverted_cube(self):
        cube = cube_of_size_2(lambda arr: 1-arr)
        ref = make_canon_grid(cube_of_size_2(lambda arr: arr))
        self.assertEqual(make_canon_grid(cube, strength=0.0), ref)
        self.assertEqual(struct.unpack_from('<3H', make_canon_grid(cube, 1), 6), (4095, 4095, 4095))

    def test_bad_strength_fails(self):
        with self.assertRaises(ValueError):
            make_canon_grid(cube_of_size_2(lambda x:x), -0.01)

    def test_property_sizes_and_curve_not_all_zero(self):
        props = make_properties(cube_of_size_2(lambda x: x), 'Camera Test', 'Neutral')
        self.assertEqual(tuple(props), tuple(prop for prop, _ in SIZES))
        for prop, expected_len in SIZES:
            self.assertEqual(len(props[prop]), expected_len)
        self.assertEqual(props[TABLE_ID_A], props[TABLE_ID_B])
        self.assertEqual(props[0x114], struct.pack('<I', STYLE_IDS['Neutral']))
        self.assertNotEqual(props[0x40001018], bytes(300))
        self.assertNotEqual(props[0x40001021], bytes(240))
        self.assertTrue(props[0x40001002].startswith(b'Camera Test'))

    def test_envelope_check_detects_corruption(self):
        body = bytes(range(64))
        with tempfile.TemporaryDirectory() as d:
            file = Path(d)/'file.pf3'
            file.write_bytes(MAGIC + len(body).to_bytes(4, 'big') + body)
            info = validate_envelope(file)
            self.assertEqual(info['bytes'], 12 + len(body))
            file.write_bytes(MAGIC + bytes(4) + body)
            with self.assertRaises(ValueError):
                validate_envelope(file)

    def test_cannot_export_fake_pf3_on_non_windows(self):
        from pf3_native import NativeSerializer
        if __import__('sys').platform != 'win32':
            with self.assertRaises(OSError):
                NativeSerializer('/dummy/EdsCFParse.dll')

    def test_finds_mac_library_inside_app_bundle(self):
        import pf3_native
        with tempfile.TemporaryDirectory() as d:
            app = Path(d)/'PictureStyleEditor.app'
            binary = app/pf3_native.MAC_LIBRARY
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'')
            with mock.patch.object(pf3_native.sys, 'platform', 'darwin'):
                self.assertEqual(pf3_native.find_canon_library(app), binary.resolve())
                self.assertEqual(pf3_native.find_canon_library(Path(d)), binary.resolve())
                self.assertEqual(pf3_native.find_canon_library(binary), binary.resolve())

    def test_mac_runtime_is_next_to_parser_bundle(self):
        import canon_render
        with tempfile.TemporaryDirectory() as d:
            plugins = Path(d)/'Contents/PlugIns'
            parser = plugins/'EdsCFParse.bundle/Contents/MacOS/EdsCFParse'
            core = plugins/'DppCore.bundle'
            for f in (parser, core/'Contents/MacOS/DppCore', core/'Contents/Resources/icc/NS.ICC'):
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(b'')
            with mock.patch.object(canon_render.sys, 'platform', 'darwin'):
                self.assertEqual(canon_render.find_runtime(parser), core.resolve())
            library, icc = canon_render._runtime_files(core)
            self.assertEqual(library.name, 'DppCore')
            self.assertEqual(icc.name, 'NS.ICC')

if __name__ == '__main__':
    unittest.main()
