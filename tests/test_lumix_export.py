"""Tests for LUMIX 33³ exports and XMP -> CUBE route."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import unittest
import tkinter as tk

import numpy as np

from cli import main
from lut import Cube, apply_cube, load_cube
from lumix_export import export_lumix_cube, PHOTO_STYLES
from xmp_bridge import load_xmp, export_xmp
from app import App

ROOT = Path(__file__).resolve().parents[1]


def creative_lut():
    axis = np.linspace(0, 1, 9, dtype=np.float32)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing='ij'), -1)
    tint = np.clip(grid * np.array([1.07, .92, .85]) + .03, 0, 1).astype(np.float32)
    return Cube(tint, np.zeros(3), np.ones(3), 'Artistic LUT')


class TestLumixExport(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.cube = creative_lut()

    def test_official_tag_and_size_and_order(self):
        path = self.folder/'out.cube'
        result = export_lumix_cube(self.cube, path, strength=.5, style='NAT', title='Portrait')
        text = path.read_text(encoding='ascii').splitlines()
        self.assertEqual(text[0], 'TITLE "Portrait"')
        self.assertEqual(text[1], '#LUMIXPHOTOSTYLE NAT')
        self.assertEqual(text[2], 'LUT_3D_SIZE 33')
        self.assertEqual(len(text), 3 + 33**3)
        self.assertEqual(result['size'], 33)
        self.assertEqual(result['style'], 'NAT')
        normalized = load_cube(path)
        samples = np.random.default_rng(4).uniform(0, 1, (200,3))
        expected = samples + .5*(apply_cube(self.cube, samples) - samples)
        actual = apply_cube(normalized, samples)
        np.testing.assert_allclose(actual, expected, atol=.00035)

    def test_0_100_strength_and_clipping(self):
        for strength in (0., 1.):
            path = self.folder/f'{strength}.cube'
            result = export_lumix_cube(self.cube, path, strength=strength)
            l = load_cube(path)
            probes = np.random.default_rng(0).random((100,3)).astype(np.float32)
            expected = probes if strength == 0 else apply_cube(self.cube, probes)
            np.testing.assert_allclose(apply_cube(l, probes), expected, atol=2e-4)
            self.assertEqual(result['strength'], strength)
        g = self.cube.data.copy()
        g[...,1] = 1.2
        high = Cube(g,np.zeros(3),np.ones(3))
        d = export_lumix_cube(high, self.folder/'clamp.cube')
        self.assertGreater(d['clamped_component_fraction'],0)
        values = load_cube(d['file']).data
        self.assertLessEqual(values.max(),1)

    def test_invalid_path_style_strength_and_atomic(self):
        out = self.folder/'original.cube'
        out.write_text('previous content')
        for args in ({'style':'INVALID'}, {'strength': -0.01}, {'strength': 1.01},
                     {'strength': float('nan')}):
            with self.assertRaises(ValueError): export_lumix_cube(self.cube,out,**args)
            self.assertEqual(out.read_text(),'previous content')
        with self.assertRaises(ValueError):
            export_lumix_cube(self.cube,self.folder/'test.txt')
        self.assertEqual(len(PHOTO_STYLES), 18)
        sanitized=self.folder/'safe.cube'
        export_lumix_cube(self.cube,sanitized,title='한국어\nLUT_3D_SIZE 5 "x"')
        self.assertEqual(sanitized.read_text().splitlines()[1], '#LUMIXPHOTOSTYLE STD')

    def test_xmp_profile_to_lumix_cube_cli(self):
        source = self.folder/'profile.xmp'
        export_xmp(self.cube, source, name='Portrait')
        result = self.folder/'portrait_lumix.cube'
        self.assertEqual(main([str(source),'-o',str(result),'--lumix-style','PORT',
                               '--strength','0.75']),0)
        self.assertIn('#LUMIXPHOTOSTYLE PORT',result.read_text(encoding='utf-8'))
        pts = np.random.default_rng(5).random((50,3))
        original = load_xmp(source).cube
        lut = load_cube(result)
        np.testing.assert_allclose(apply_cube(lut,pts),
                         pts + .75*(apply_cube(original,pts)-pts),atol=.002)

    def test_xmp_develop_preset_to_cube_cli(self):
        source = ROOT/'example_xmp'/'warm_film_sample.xmp'
        result = self.folder/'preset.cube'
        self.assertEqual(main([str(source),'-o',str(result)]),0)
        self.assertEqual(load_cube(result).size,33)
        self.assertNotIn('LUMIXPHOTOSTYLE',result.read_text())
        special = self.folder/'preset_lumix.cube'
        self.assertEqual(main([str(source),'-o',str(special),'--lumix-style','STD']),0)
        self.assertIn('#LUMIXPHOTOSTYLE STD',special.read_text())
        self.assertEqual(main([str(source),'-o',str(self.folder/'bad.xmp'),
                               '--lumix-style','STD']),1)

    def test_gui_xmp_can_save_lumix_with_strength(self):
        try:
            root=tk.Tk()
        except tk.TclError as error:
            self.skipTest(f'Tk display unavailable: {error}')
        try:
            app=App(root)
            path=ROOT/'example_xmp'/'warm_film_sample.xmp'
            with patch('app.filedialog.askopenfilename',return_value=str(path)), patch('app.messagebox.showwarning'):
                app.open_cube()
            self.assertEqual(app.input_kind,'xmp')
            app.strength.set(35)
            app.lumix_style.set('NAT')
            dest=self.folder/'gui.cube'
            with patch('app.filedialog.asksaveasfilename',return_value=str(dest)), patch('app.messagebox.showinfo') as popup:
                app.save_lumix()
            self.assertTrue(dest.is_file())
            self.assertIn('#LUMIXPHOTOSTYLE NAT',dest.read_text())
            self.assertIn('35%',popup.call_args.args[1])
        finally:
            root.destroy()

if __name__=='__main__': unittest.main()
