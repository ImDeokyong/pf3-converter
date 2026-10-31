import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import numpy as np
from PIL import Image
from photo_loader import load_photo, PHOTO_FILETYPES, RAW_EXTENSIONS

class TestPhotoLoader(unittest.TestCase):
    def test_raster_full_size_and_exif_rotation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'photo.jpg'
            exif=Image.Exif(); exif[274]=6
            Image.new('RGB',(1400,800),(20,80,120)).save(path,exif=exif)
            photo,note=load_photo(path)
            self.assertEqual(photo.size,(800,1400))
            self.assertEqual(photo.mode,'RGB')
            path.unlink()  # decoder closed the input file

    def test_raw_options_case_and_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'한글.CR3'; path.write_bytes(b'test')
            rawpy=MagicMock()
            raw=rawpy.imread.return_value.__enter__.return_value
            raw.postprocess.return_value=np.full((18,24,3),97,dtype=np.uint8)
            with patch.dict('sys.modules',{'rawpy':rawpy}):
                photo,note=load_photo(path)
            self.assertEqual(photo.size,(24,18))
            self.assertEqual(photo.getpixel((0,0)),(97,97,97))
            self.assertIn('RAW',note)
            options=raw.postprocess.call_args.kwargs
            self.assertFalse(options['half_size'])
            self.assertTrue(options['use_camera_wb'])
            self.assertTrue(options['no_auto_bright'])
            self.assertEqual(options['output_bps'],8)
            rawpy.imread.return_value.__exit__.assert_called_once()
            self.assertTrue(rawpy.imread.call_args.args[0].closed)
            path.unlink()

    def test_missing_rawpy_message(self):
        with patch.dict('sys.modules',{'rawpy':None}):
            with self.assertRaisesRegex(RuntimeError,'rawpy'):
                load_photo('test.cr2')

    def test_bad_raw_message(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'broken.nef'; path.write_bytes(b'broken')
            rawpy=MagicMock(); rawpy.imread.side_effect=ValueError('bad data')
            with patch.dict('sys.modules',{'rawpy':rawpy}):
                with self.assertRaisesRegex(RuntimeError,'LibRaw'):
                    load_photo(path)

    def test_filters(self):
        for ext in ('.cr2','.cr3','.crw','.dng','.nef','.arw','.raf','.orf','.rw2'):
            self.assertIn(ext,RAW_EXTENSIONS)
            self.assertIn('*'+ext,PHOTO_FILETYPES[0][1])

    @unittest.skipUnless(os.environ.get('CANON_RAW_TEST_FILE'),'Set CANON_RAW_TEST_FILE for real RAW decoding')
    def test_real_raw(self):
        photo,note=load_photo(os.environ['CANON_RAW_TEST_FILE'])
        self.assertEqual(photo.mode,'RGB')
        self.assertGreater(photo.width,1000)
        self.assertGreater(photo.height,1000)
        self.assertIn('sRGB',note)
        self.assertGreater(np.asarray(photo).std(),1)

if __name__=='__main__': unittest.main()
