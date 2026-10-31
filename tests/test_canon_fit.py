import os
from pathlib import Path
import tempfile
import unittest
import numpy as np
from lut import Cube,load_cube
from canon_fit import fit_cube,target_rgb
from pf3_native import make_properties,NativeSerializer,TABLE_ID_A,make_canon_grid
from canon_render import render_pair


def identity_cube():
    axis=np.array([0,1],dtype=np.float32)
    return Cube(np.stack(np.meshgrid(axis,axis,axis,indexing='ij'),-1),np.zeros(3),np.ones(3))


class TestCanonFit(unittest.TestCase):
    def test_identity_and_zero_strength(self):
        cube=identity_cube()
        x=np.random.default_rng(2).random((100,3))
        np.testing.assert_allclose(fit_cube(cube).apply(x),x,atol=2e-5)
        cube.data=1-cube.data
        np.testing.assert_allclose(fit_cube(cube,0).apply(x),x,atol=2e-5)

    def test_color_mix_held_out_pixels(self):
        cube=identity_cube()
        matrix=np.array([[.8,.2,0],[0,.7,.3],[.1,0,.9]])
        cube.data=cube.data@matrix.T
        fitted=fit_cube(cube)
        x=np.random.default_rng(4).random((100,3))
        np.testing.assert_allclose(fitted.apply(x),x@matrix.T,atol=.003)
        self.assertLess(fitted.report['estimated_rgb_mae_255'],1)

    def test_editable_fields_carry_look_camera_table_is_identity(self):
        cube=identity_cube();cube.data=cube.data[...,::-1].copy()
        props=make_properties(cube,'test')
        identity=make_properties(identity_cube(),'identity')
        self.assertEqual(props[TABLE_ID_A],make_canon_grid(identity_cube()))
        self.assertTrue(props[0x40001021]!=identity[0x40001021] or
                        props[0x40001065]!=identity[0x40001065])
        self.assertEqual(len(props[0x40001021]),240)
        self.assertEqual(len(props[0x40001065]),300)

    def test_invalid_strength(self):
        for value in (-1,2,float('nan')):
            with self.assertRaises(ValueError):fit_cube(identity_cube(),value)

    def test_roundtrip_checks_editable_fields(self):
        # The original verifier only checked the two camera tables. A corrupted
        # curve must now fail even when both tables round-trip correctly.
        from unittest.mock import patch,MagicMock
        serializer=object.__new__(NativeSerializer)
        properties={TABLE_ID_A:b'table',0x40001065:b'curve'}
        context=MagicMock();context.__enter__.return_value='ref'
        with patch.object(serializer,'document',return_value=context),patch.object(serializer,'read_prop',side_effect=[b'table',b'wrong']):
            with self.assertRaises(ValueError):serializer.verify(Path('test.pf3'),properties)


@unittest.skipUnless(os.environ.get('CLB_NATIVE_RAW') and os.environ.get('CLB_NATIVE_LUT') and os.environ.get('CLB_NATIVE_DLL'),
                     'Set CLB_NATIVE_RAW, CLB_NATIVE_LUT and CLB_NATIVE_DLL for Canon engine integration')
class TestActualCanonRender(unittest.TestCase):
    def test_real_pf3_look_changes_pixels_and_matches_target(self):
        cube=load_cube(os.environ['CLB_NATIVE_LUT'])
        original,altered,report=render_pair(os.environ['CLB_NATIVE_RAW'],cube,1,'Neutral',
                                          os.environ['CLB_NATIVE_DLL'],(4024,6022))
        self.assertEqual(original.size,(1080,1620))
        self.assertGreater(abs(np.asarray(original).astype(float)-np.asarray(altered)).mean(),5)
        self.assertTrue(report['native_render_verified'])
        self.assertLess(report['native_rgb_mae_255'],8)
        self.assertFalse(report['camera_tested'])

if __name__=='__main__':unittest.main()
