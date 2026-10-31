"""Verify PF3 Converter v1.1 branding through CLI, XMP, GUI and packaging."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch
import tempfile
import os
import tkinter as tk
from tkinter import ttk
import unittest

from app import App
from app_info import APP_NAME, APP_AUTHOR, APP_VERSION, display_name
from cli import main
from lut import load_cube
from xmp_bridge import export_xmp, load_xmp

ROOT = Path(__file__).resolve().parents[1]


class BrandingTests(unittest.TestCase):
    def setUp(self):
        self.settings = tempfile.TemporaryDirectory()
        self.settings_patch = patch.dict(os.environ, {'PICTURE_BRIDGE_CONFIG_DIR': self.settings.name})
        self.settings_patch.start()

    def tearDown(self):
        self.settings_patch.stop()
        self.settings.cleanup()

    def test_common_app_identity(self):
        self.assertEqual((APP_NAME, APP_VERSION, APP_AUTHOR),
                         ('PF3 Converter', '1.1', 'ImDeokyong'))
        self.assertEqual(display_name(), 'PF3 Converter v1.1')

    def test_cli_version_message(self):
        text = StringIO()
        with redirect_stdout(text), self.assertRaises(SystemExit) as result:
            main(['--version'])
        self.assertEqual(result.exception.code, 0)
        self.assertIn('PF3 Converter v1.1', text.getvalue())
        self.assertIn('ImDeokyong', text.getvalue())

    def test_profile_defaults_to_picture_bridge_group(self):
        cube = load_cube(ROOT/'example_luts'/'identity_2.cube')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'test.xmp'
            export_xmp(cube, path, name='Test')
            self.assertEqual(load_xmp(path).kind, 'profile')
            raw = path.read_text(encoding='utf-8')
            self.assertIn('<rdf:li xml:lang="x-default">PF3 Converter</rdf:li>', raw)
            self.assertIn('x:xmptk="PF3 Converter"', raw)

    def test_windows_packaging_name_and_metadata(self):
        bat = (ROOT/'build_windows.bat').read_text(encoding='utf-8')
        workflow = (ROOT/'.github/workflows/windows-build.yml').read_text(encoding='utf-8')
        metadata = (ROOT/'version_info.txt').read_text(encoding='utf-8')
        for script in (bat, workflow):
            self.assertIn('--name PF3Converter', script)
            self.assertIn('--version-file version_info.txt', script)
            self.assertIn('PF3Converter.exe', script)
        for marker in ("StringStruct('CompanyName', 'ImDeokyong')",
                       "StringStruct('ProductName', 'PF3 Converter')",
                       'prodvers=(1, 1, 0, 0)', 'filevers=(1, 1, 0, 0)'):
            self.assertIn(marker, metadata)

    def test_gui_title_author_and_about(self):
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f'Tk display unavailable: {error}')
        try:
            app = App(root)
            self.assertIn('PF3 Converter v1.1', root.title())
            texts = []
            def visit(widget):
                for child in widget.winfo_children():
                    if isinstance(child, (tk.Label, ttk.Label)):
                        texts.append(child.cget('text'))
                    visit(child)
            visit(root)
            self.assertIn('PF3 Converter', texts)
            self.assertIn('버전 1.1  ·  제작자 : ImDeokyong', texts)
            with patch('app.messagebox.showinfo') as popup:
                app.show_about()
                self.assertIn('ImDeokyong', popup.call_args.args[1])
                self.assertIn('PF3 Converter v1.1', popup.call_args.args[1])
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
