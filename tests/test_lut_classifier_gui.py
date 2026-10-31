"""Classification GUI, opt-in manual override and preserved conversion output."""
import os
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch
import numpy as np
from app import App
from i18n import LANGUAGES, tr
from lut import Cube


def tech_cube():
    v = np.linspace(0., 1., 17, dtype=np.float32)
    grid = np.stack(np.meshgrid(v, v, v, indexing='ij'), -1)
    return Cube((np.clip((grid-.12)/.62, 0, 1)**1.1).astype(np.float32),
                np.zeros(3), np.ones(3))


class ClassifierGuiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'PICTURE_BRIDGE_CONFIG_DIR': self.tmp.name})
        self.env.start()
        try:
            self.root = tk.Tk()
        except tk.TclError as ex:
            self.env.stop()
            self.tmp.cleanup()
            self.skipTest(str(ex))
        self.app = App(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        self.root.destroy()
        self.env.stop()
        self.tmp.cleanup()

    def _load_technical(self):
        with patch('app.filedialog.askopenfilename', return_value='Fake_Film_Look.cube'), \
             patch('app.load_cube', return_value=tech_cube()), \
             patch('app.messagebox.showwarning') as warning:
            self.app.open_cube()
            warning.assert_not_called()  # User explicitly requested no warning feature.

    def test_technical_is_shown_inline_no_warning_and_conversion_not_blocked(self):
        self._load_technical()
        self.assertEqual(self.app.lut_classification.kind, 'technical')
        self.assertEqual(str(self.app.raw_strength_button['state']), 'disabled')
        self.assertEqual(str(self.app.xmp_button['state']), 'normal')
        with patch('app.sys.platform', 'win32'), \
             patch('app.filedialog.asksaveasfilename', return_value='demo.pf3'), \
             patch('app.export_pf3', return_value={'file': 'demo.pf3', 'bytes': 1024,
                   'sha256': 'a'*64, 'fit': {'estimated_rgb_mae_255': 2.5}}) as export, \
             patch('app.messagebox.showinfo'):
            self.app.save_pf3()
            self.assertTrue(export.called)

    def test_manual_override_enables_optimizer_and_can_reset_in_four_languages(self):
        self._load_technical()
        for code in LANGUAGES:
            self.app.language_label.set(LANGUAGES[code])
            self.app.change_language()
            self.assertEqual(str(self.app.raw_strength_button['state']), 'disabled')
            self.assertIn('Technical', self.app.lut_class_message.get())
            self.app.lut_kind_selection.set(tr(code, 'lut_class_override_creative'))
            self.app.on_lut_class_override()
            self.assertEqual(str(self.app.raw_strength_button['state']), 'normal')
            self.assertEqual(self.app.lut_kind_override, 'creative')
            self.app.lut_kind_selection.set(tr(code, 'lut_class_override_auto'))
            self.app.on_lut_class_override()
            self.assertEqual(str(self.app.raw_strength_button['state']), 'disabled')

    def test_no_identifier_on_xmp_and_strength_still_available(self):
        self._load_technical()
        with patch('app.filedialog.askopenfilename', return_value='sample.xmp'), \
             patch('app.load_xmp') as importer:
            from types import SimpleNamespace
            importer.return_value = SimpleNamespace(cube=tech_cube(), kind='profile',
                                                   ignored=(), warnings=(), color_space='sRGB')
            self.app.open_cube()
        self.assertIsNone(self.app.lut_classification)
        self.assertEqual(str(self.app.raw_strength_button['state']), 'normal')

if __name__ == '__main__':
    unittest.main()
