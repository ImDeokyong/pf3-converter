"""Four-language GUI, translated runtime messages and persisted preferences."""
from pathlib import Path
from unittest.mock import patch
import os
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest

from app import App
from app_info import APP_NAME, APP_VERSION, APP_AUTHOR
from i18n import (LANGUAGES, LANGUAGE_LABELS, _MESSAGES, config_file,
                  load_language, save_language, tr, validate_catalog)

ROOT = Path(__file__).resolve().parents[1]


class CatalogTests(unittest.TestCase):
    def test_complete_catalog_and_placeholders(self):
        validate_catalog()
        self.assertEqual(set(LANGUAGES), {'ko', 'en', 'ja', 'zh-CN'})
        self.assertEqual(len(LANGUAGE_LABELS), 4)
        self.assertGreaterEqual(len(_MESSAGES), 90)
        for code in LANGUAGES:
            self.assertIn('ImDeokyong', tr(code, 'credit', version=APP_VERSION, author=APP_AUTHOR))
            self.assertIn('1.1', tr(code, 'credit', version=APP_VERSION, author=APP_AUTHOR))
            self.assertTrue(tr(code, 'pf3_saved_body', path='a.pf3', bytes=1024,
                               sha='f'*20, mae=2.1, xmp_note=''))

    def test_persistent_settings_and_invalid_config(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'PICTURE_BRIDGE_CONFIG_DIR': tmp}):
            self.assertEqual(load_language(), 'ko')
            self.assertTrue(save_language('zh-CN'))
            self.assertEqual(load_language(), 'zh-CN')
            self.assertEqual(config_file().read_text(encoding='utf-8').count('zh-CN'), 1)
            config_file().write_text('{ bad json', encoding='utf-8')
            self.assertEqual(load_language(), 'ko')
            with self.assertRaises(ValueError):
                save_language('unknown')


class LocalizationGuiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'PICTURE_BRIDGE_CONFIG_DIR': self.tmp.name})
        self.env.start()
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.env.stop()
            self.tmp.cleanup()
            self.skipTest(f'Display unavailable: {error}')
        self.app = App(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        self.root.destroy()
        self.env.stop()
        self.tmp.cleanup()

    def _switch(self, code):
        self.app.language_label.set(LANGUAGES[code])
        self.app.change_language()
        self.root.update_idletasks()

    def test_gui_switches_immediately_all_four_languages(self):
        self.assertEqual(self.app.language, 'ko')
        self.assertEqual(self.app.status.get(), tr('ko', 'choose_lut'))
        for code in ('en', 'ja', 'zh-CN', 'ko'):
            self._switch(code)
            self.assertEqual(self.app.language, code)
            self.assertEqual(self.app.status.get(), tr(code, 'choose_lut'))
            self.assertEqual(self.app.photo_status.get(), tr(code, 'photo_ready'))
            self.assertEqual(self.app.preview_mode.get(), tr(code, 'mode_canon'))
            self.assertEqual(self.app.language_picker['values'], tuple(LANGUAGES.values()))
            self.assertEqual(self.app.preview_view.fit_button.cget('text'), tr(code, 'fit'))
            self.assertEqual(self.app.preview_view.titles[0].cget('text'), tr(code, 'viewer_original'))
            self.assertEqual(self.app.preview_view.info.get(), tr(code, 'viewer_no_photo'))
            self.assertEqual(self.app.root.title(), tr(code, 'app_title', name=f'{APP_NAME} v{APP_VERSION}'))
            for widget, key, args in self.app._translatables:
                self.assertEqual(widget.cget('text'), tr(code, key, **args))
            with patch('app.messagebox.showinfo') as about:
                self.app.show_about()
                self.assertEqual(about.call_args.args[0], tr(code, 'about'))
                self.assertIn(APP_AUTHOR, about.call_args.args[1])
        self._switch('ja')
        self.assertEqual(load_language(), 'ja')
        second = App(tk.Toplevel(self.root))
        self.assertEqual(second.language, 'ja')
        second.root.destroy()

    def test_file_type_filters_are_translated(self):
        for code in LANGUAGES:
            self._switch(code)
            self.assertEqual(self.app._file_filters()[0][0], tr(code, 'file_filter_lut_xmp'))
            self.assertEqual(self.app._photo_filters()[0][0], tr(code, 'file_filter_photos'))
            self.assertIn('*.cr3', self.app._photo_filters()[0][1])

    def test_loaded_cube_and_xmp_runtime_status_switch_languages(self):
        cube = ROOT/'example_luts'/'identity_2.cube'
        xmp = ROOT/'example_xmp'/'warm_film_sample.xmp'
        with patch('app.filedialog.askopenfilename', return_value=str(cube)):
            self.app.open_cube()
        self.assertEqual(self.app.input_kind, 'cube')
        self._switch('en')
        self.assertIn('RGB samples', self.app.status.get())
        self.assertEqual(str(self.app.xmp_button['state']), 'normal')
        with patch('app.filedialog.askopenfilename', return_value=str(xmp)), patch('app.messagebox.showwarning'):
            self.app.open_cube()
        self._switch('zh-CN')
        self.assertIn('近似', self.app.status.get())
        self._switch('ja')
        self.assertIn('近似', self.app.status.get())
        self.assertEqual(str(self.app.xmp_button['state']), 'disabled')
        self.app.preview_mode.set(tr('ja', 'mode_reference'))
        self._switch('en')
        self.assertEqual(self.app.preview_mode.get(), tr('en', 'mode_reference'))
        self.assertFalse(self.app._is_canon_mode())

    def test_showwarning_is_localized_and_not_dropped(self):
        xmp = ROOT/'example_xmp'/'warm_film_sample.xmp'
        self._switch('ja')
        with patch('app.filedialog.askopenfilename', return_value=str(xmp)),\
                patch('app.messagebox.showwarning') as warning:
            self.app.open_cube()
        self.assertEqual(warning.call_args.args[0], tr('ja', 'xmp_warning_title'))
        self.assertIn('Lightroom', warning.call_args.args[1])
        self.assertNotIn('Scene-aware RAW adjustments', warning.call_args.args[1])

    def test_saving_language_does_not_reset_zoom_or_preview(self):
        from PIL import Image
        self.app.photo = Image.new('RGB', (900, 600))
        self.app.update_preview()
        self.app.preview_view.set_zoom(1.7)
        sequence = self.app.native_sequence
        old_rev = self.app.preview_view.revision
        self._switch('en')
        self.assertEqual(self.app.preview_view.zoom, 1.7)
        self.assertEqual(self.app.preview_view.revision, old_rev)
        self.assertEqual(self.app.native_sequence, sequence)
        self.assertEqual(self.app.preview_view.titles[1].cget('text'), tr('en', 'preview_lut_target'))


if __name__ == '__main__':
    unittest.main()
