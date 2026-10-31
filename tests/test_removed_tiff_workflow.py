"""Ensure removed Lightroom TIFF fitting workflow cannot reappear in the UI/CLI."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import unittest

import numpy as np

from app import App
from cli import main
from i18n import _MESSAGES, LANGUAGES, tr
from lut import apply_cube, load_cube
from lumix_export import export_lumix_cube, export_srgb_cube
from xmp_bridge import load_xmp

ROOT = Path(__file__).resolve().parents[1]


class NoTiffWorkflowTests(unittest.TestCase):
    def test_removed_library_commands_and_translations(self):
        self.assertFalse((ROOT / 'lightroom_reference.py').exists())
        self.assertFalse((ROOT / 'tests/test_srgb_reference.py').exists())
        self.assertFalse(any(k.startswith('reference_chart') or k.startswith('reference_select_') for k in _MESSAGES))
        self.assertNotIn('footnote', _MESSAGES)
        for lang in LANGUAGES:
            self.assertNotIn('현재 강도를 LUT에 반영', tr(lang,'lumix_note'))

    def test_no_reference_cli_options(self):
        with redirect_stdout(StringIO()) as out:
            with self.assertRaises(SystemExit) as err:
                main(['--help'])
        self.assertEqual(err.exception.code,0)
        for marker in ('--lightroom-before','--lightroom-after','--make-reference-chart'):
            self.assertNotIn(marker, out.getvalue())

    def test_main_window_no_extra_tiff_controls_or_pf3_footnote(self):
        try:
            root=tk.Tk()
        except tk.TclError as error:
            self.skipTest(f'Display unavailable: {error}')
        try:
            app=App(root)
            texts=[]
            def visit(widget):
                for child in widget.winfo_children():
                    if isinstance(child, (tk.Label, ttk.Label, ttk.Button)):
                        texts.append(child.cget('text'))
                    visit(child)
            visit(root)
            self.assertNotIn('Lightroom 기준 차트 TIFF 생성', texts)
            self.assertNotIn('Lightroom 전후 TIFF로 LUT 맞춤', texts)
            self.assertFalse(any('PF3는 DPP가' in str(s) for s in texts))
            self.assertNotIn('현재 강도를 LUT에 반영', ''.join(texts))
        finally:
            root.destroy()

    def test_both_cube_exports_identical_at_equal_strength(self):
        xmp=ROOT/'example_xmp'/'warm_film_sample.xmp'
        cube=load_xmp(xmp).cube
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            for strength in (1., .5):
                a=Path(directory)/'photoshop.cube'
                b=Path(directory)/'lumix.cube'
                export_srgb_cube(cube,a,strength=strength,title='same')
                export_lumix_cube(cube,b,strength=strength,title='same')
                first=a.read_text(encoding='ascii').splitlines()
                second=b.read_text(encoding='ascii').splitlines()
                self.assertEqual(first[0],second[0])
                self.assertEqual(first[1:],second[2:])

if __name__=='__main__':
    unittest.main()
