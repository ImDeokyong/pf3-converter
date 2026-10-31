"""GUI integration tests for the RAW analyzer and all four locales."""
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch
import os

from app import App
from raw_strength import StrengthResult
from i18n import LANGUAGES, tr


class GUIRawStrengthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'PICTURE_BRIDGE_CONFIG_DIR': self.temp.name})
        self.env.start()
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.env.stop()
            self.temp.cleanup()
            self.skipTest(f'No display: {error}')
        self.app = App(self.root)
        self.root.update_idletasks()
        cube = str(Path(__file__).resolve().parents[1] / 'example_luts' / 'identity_2.cube')
        with patch('app.filedialog.askopenfilename', return_value=cube):
            self.app.open_cube()

    def tearDown(self):
        self.root.destroy()
        self.env.stop()
        self.temp.cleanup()

    def poll_until_idle(self):
        limit = time.monotonic() + 5
        while time.monotonic() < limit:
            self.root.update()
            if self.app.strength_future is None:
                return
            time.sleep(.02)
        self.fail('RAW analyzer never completed')

    def test_initial_fifty_and_result_applied_to_existing_pf3_slider(self):
        self.assertEqual(self.app.strength.get(), 50)
        report = StrengthResult(35, 2, (), True)
        with patch('app.filedialog.askopenfilenames', return_value=('a.cr3', 'b.nef')),\
                patch('app.recommend_strength', return_value=report),\
                patch('app.messagebox.showinfo') as info:
            self.app.start_raw_strength()
            self.poll_until_idle()
            self.assertEqual(self.app.strength.get(), 35)
            self.assertEqual(self.app.strength_label['text'], '35%')
            self.assertEqual(self.app.strength_result.photos, 2)
            self.assertIn('35%', self.app.strength_message.get())
            self.assertEqual(str(self.app.raw_strength_button['state']), 'normal')
            info.assert_called_once()
            for code in LANGUAGES:
                self.app.language_label.set(LANGUAGES[code])
                self.app.change_language()
                self.assertIn('35%', self.app.strength_message.get())
                self.assertEqual(self.app.raw_strength_button.cget('text'), tr(code, 'raw_strength_button'))

    def test_recommendation_reaches_pf3_export_without_new_conversion_path(self):
        from unittest.mock import patch
        self.app.strength.set(40)
        with patch('app.sys.platform', 'win32'), \
             patch('app.filedialog.asksaveasfilename', return_value='demo.pf3'), \
             patch('app.export_pf3', return_value={'file': 'demo.pf3', 'bytes': 1024,
                    'sha256': 'a'*64, 'fit': {'estimated_rgb_mae_255': 2.5}}) as export, \
             patch('app.messagebox.showinfo'):
            self.app.save_pf3()
            self.assertEqual(export.call_args.kwargs['strength'], 0.40)

    def test_invalid_count_and_wrong_extension_not_submitted(self):
        for choice in (('a.jpg',), ('a.cr3',) * 6):
            with patch('app.filedialog.askopenfilenames', return_value=choice), \
                    patch('app.messagebox.showwarning') as warning:
                self.app.start_raw_strength()
                warning.assert_called_once()
                self.assertIsNone(self.app.strength_future)
                self.assertEqual(self.app.strength.get(), 50)

    def test_worker_error_is_shown_and_does_not_change_strength(self):
        with patch('app.filedialog.askopenfilenames', return_value=('x.cr3',)), \
             patch('app.recommend_strength', side_effect=RuntimeError('rawpy failed')), \
             patch('app.messagebox.showerror') as error:
            self.app.start_raw_strength()
            self.poll_until_idle()
            self.assertEqual(self.app.strength.get(), 50)
            self.assertIn('rawpy failed', error.call_args.args[1])

    def test_stale_result_does_not_modify_new_lut(self):
        with patch('app.filedialog.askopenfilenames', return_value=('x.cr3',)), \
                patch('app.recommend_strength', return_value=StrengthResult(15, 1, (), True)),\
                patch('app.messagebox.showinfo') as info:
            self.app.start_raw_strength()
            self.app.cube = object()  # Simulate a newer profile loaded during work.
            self.poll_until_idle()
            self.assertEqual(self.app.strength.get(), 50)
            self.assertFalse(info.called)


if __name__ == '__main__':
    unittest.main()
