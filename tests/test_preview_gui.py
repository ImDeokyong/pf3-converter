"""Windows/Tk integration checks; run with an interactive desktop available."""
import time
import tkinter as tk
import unittest
from unittest.mock import patch
import tempfile
import os
from PIL import Image
from app import App
from lut import load_cube
from pathlib import Path

class TestPreviewGUI(unittest.TestCase):
    def setUp(self):
        self.settings = tempfile.TemporaryDirectory()
        self.settings_patch = patch.dict(os.environ, {'PICTURE_BRIDGE_CONFIG_DIR': self.settings.name})
        self.settings_patch.start()

    def tearDown(self):
        self.settings_patch.stop()
        self.settings.cleanup()

    def wait_render(self, view):
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            self.root.update()
            if view.timer is None and view.pending is None and view.future is None and hasattr(view,'images'):
                return
            time.sleep(.01)
        self.fail('Preview render timed out')

    def test_resize_zoom_pan_and_latest_request(self):
        try:
            self.root=tk.Tk()
        except tk.TclError as error:
            self.skipTest(f'Tk display unavailable: {error}')
        try:
            app=App(self.root)
            self.root.update()
            view=app.preview_view
            app.photo=Image.new('RGB',(6000,4000),(41,103,207))
            app.update_preview()
            self.wait_render(view)
            first=view.images[0].width()
            self.assertEqual(app.photo.size,(6000,4000))
            self.assertIn('6,000 × 4,000',view.info.get())
            self.root.geometry('1400x1000')
            self.wait_render(view)
            self.assertGreater(view.images[0].width(),first)
            view.set_zoom(1)
            self.wait_render(view)
            self.assertEqual(view.zoom,1)
            self.assertEqual(view.images[0].width(),view.viewport()[0])
            event=type('Event',(),{'x':200,'y':160})()
            view.start_pan(event)
            view.pan(type('Event',(),{'x':100,'y':100})())
            self.wait_render(view)
            self.assertEqual(view.center,(3100,2060))
            for z in (2,.5,1.25):
                view.set_zoom(z)
            self.wait_render(view)
            self.assertEqual(view.zoom,1.25)
            app.cube=load_cube(next((Path(__file__).resolve().parents[1]/'example_luts').glob('*.cube')))
            app.strength.set(35)
            app.on_strength()
            self.wait_render(view)
            self.assertEqual(view.strength,.35)
            view.fit_view()
            self.wait_render(view)
            self.assertTrue(view.fit)
            self.assertEqual(view.images[0].width(),view.images[1].width())
            self.assertNotIn('오류',view.info.get())
        finally:
            self.root.destroy()

    def test_cube_xmp_switch_and_xmp_export_button(self):
        try:
            self.root=tk.Tk()
        except tk.TclError as error:
            self.skipTest(str(error))
        try:
            app=App(self.root)
            cube=str(Path(__file__).resolve().parents[1]/'example_luts'/'identity_2.cube')
            xmp=str(Path(__file__).resolve().parents[1]/'example_xmp'/'warm_film_sample.xmp')
            with patch('app.filedialog.askopenfilename',return_value=cube):
                app.open_cube()
            self.assertEqual(app.input_kind,'cube')
            self.assertEqual(str(app.xmp_button['state']),'normal')
            with patch('app.filedialog.askopenfilename',return_value=xmp),patch('app.messagebox.showwarning'):
                app.open_cube()
            self.assertEqual(app.input_kind,'xmp')
            self.assertEqual(str(app.xmp_button['state']),'disabled')
            self.assertIn('근사',app.status.get())
        finally:
            self.root.destroy()

    def test_async_photo_open_and_error_keeps_previous(self):
        try:
            self.root=tk.Tk()
        except tk.TclError as error:
            self.skipTest(str(error))
        try:
            app=App(self.root)
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'test.png'
                Image.new('RGB',(1200,900),(50,120,210)).save(path)
                with patch('app.filedialog.askopenfilename',return_value=str(path)):
                    app.open_photo()
                self.assertEqual(str(app.photo_button['state']),'disabled')
                deadline=time.monotonic()+10
                while app.photo_future is not None and time.monotonic()<deadline:
                    self.root.update(); time.sleep(.01)
                self.assertIsNone(app.photo_future)
                self.assertEqual(app.photo.size,(1200,900))
                previous=app.photo
                with patch('app.filedialog.askopenfilename',return_value=str(path)+'.missing'), patch('app.messagebox.showerror') as error:
                    app.open_photo()
                    deadline=time.monotonic()+10
                    while app.photo_future is not None and time.monotonic()<deadline:
                        self.root.update(); time.sleep(.01)
                    self.assertIsNone(app.photo_future)
                    error.assert_called_once()
                self.assertIs(app.photo,previous)
                self.assertEqual(str(app.photo_button['state']),'normal')
        finally:
            self.root.destroy()

    def test_native_mode_coalesces_changes_and_switches_to_highres(self):
        try:
            self.root=tk.Tk()
        except tk.TclError as error:
            self.skipTest(str(error))
        try:
            app=App(self.root)
            app.source_photo=app.photo=Image.new('RGB',(1200,1800),(50,90,130))
            app.raw_path='test.CR3'
            app.cube=load_cube(next((Path(__file__).resolve().parents[1]/'example_luts').glob('*.cube')))
            def render(raw,cube,strength,base,dll,size):
                time.sleep(.1)
                return (Image.new('RGB',(108,162)),Image.new('RGB',(108,162),(round(strength*200),0,0)),
                        {'native_rgb_mae_255':1.,'native_rgb_p95_255':3.})
            def wait_for(predicate):
                deadline=time.monotonic()+8
                while time.monotonic()<deadline:
                    self.root.update()
                    if predicate():return
                    time.sleep(.01)
                self.fail('GUI state timed out')
            with patch('app.find_canon_library',return_value=Path('test.dll')),patch('app.render_pair',side_effect=render):
                app.update_preview()
                wait_for(lambda:app.native_future is not None)
                app.strength.set(25);app.update_preview()
                wait_for(lambda:app.native_report is not None)
                self.assertEqual(app.preview_view.comparison.getpixel((0,0)),(50,0,0))
                self.assertEqual(app.preview_view.photo.size,(108,162))
                app.preview_mode.set('고해상도 LUT 목표 참고');app.update_preview()
                self.assertIsNone(app.preview_view.comparison)
                self.assertEqual(app.preview_view.photo.size,(1200,1800))
                self.assertIsNone(app.native_report)
        finally:
            self.root.destroy()

if __name__=='__main__': unittest.main()
