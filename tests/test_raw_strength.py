"""Deterministic tests for the optional RAW-referenced strength heuristic."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from lut import Cube
from raw_strength import recommend_strength, MAX_PHOTOS


def make_cube(look):
    grid = np.stack(np.meshgrid([0., 1.], [0., 1.], [0., 1.], indexing='ij'), -1)
    return Cube(look(grid).astype(np.float32), np.zeros(3), np.ones(3))


IDENTITY = make_cube(lambda x: x)
BLACK = make_cube(lambda x: x * 0)
RED = make_cube(lambda x: np.stack((np.ones_like(x[..., 0]), np.zeros_like(x[..., 1]), np.zeros_like(x[..., 2])), axis=-1))


def image_loader(image):
    def load(_):
        return image.copy(), 'mocked RAW postprocess'
    return load


class RawStrengthTests(unittest.TestCase):
    def test_identity_recommends_full_strength(self):
        photo = Image.new('RGB', (160, 160), (100, 150, 190))
        result = recommend_strength(IDENTITY, ['sample.cr3'], loader=image_loader(photo))
        self.assertEqual(result.recommended_percent, 100)
        self.assertTrue(result.minimum_passed)
        self.assertEqual(result.photos, 1)
        self.assertEqual(result.metrics[0].luma_p95, 0.0)

    def test_dark_crushing_lut_is_attenuated(self):
        image = Image.new('RGB', (128, 128), (110, 110, 110))
        report = recommend_strength(BLACK, ['test.nef'], loader=image_loader(image))
        self.assertLess(report.recommended_percent, 100)
        self.assertGreaterEqual(report.recommended_percent, 5)
        self.assertTrue(report.minimum_passed)
        self.assertLessEqual(report.metrics[0].luma_p95, .14)

    def test_multiple_raw_uses_most_conservative_common_strength(self):
        def load(path):
            c = 205 if path.stem == 'bright' else 60
            return Image.new('RGB', (90, 90), (c, c, c)), ''
        bright_only = recommend_strength(BLACK, ['bright.dng'], loader=load)
        dark_only = recommend_strength(BLACK, ['dark.cr2'], loader=load)
        combined = recommend_strength(BLACK, ['bright.dng', 'dark.cr2'], loader=load)
        self.assertEqual(combined.recommended_percent,
                         min(bright_only.recommended_percent, dark_only.recommended_percent))
        self.assertEqual(len(combined.metrics), 2)

    def test_strength_reduces_extreme_saturation_and_clipping(self):
        picture = Image.new('RGB', (120, 80), (220, 130, 90))
        report = recommend_strength(RED, ['a.arw'], loader=image_loader(picture))
        self.assertLess(report.recommended_percent, 100)
        self.assertTrue(report.minimum_passed)
        self.assertLessEqual(report.metrics[0].additional_clip, .01)

    def test_limits_and_unsupported_paths(self):
        image = Image.new('RGB', (8, 8), (100, 120, 140))
        for paths in ([], ['a.cr2'] * 6, ['a.jpg'], ['a.cr2', 'a.cr2']):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                recommend_strength(IDENTITY, paths, loader=image_loader(image))
        self.assertEqual(MAX_PHOTOS, 5)

    def test_raw_decode_error_is_reported_to_caller(self):
        def failure(_):
            raise RuntimeError('rawpy cannot import')
        with self.assertRaisesRegex(RuntimeError, 'rawpy'):
            recommend_strength(IDENTITY, ['bad.cr3'], loader=failure)

    def test_progress_called_once_per_file(self):
        received = []
        photo = Image.new('RGB', (24, 24), (140, 100, 90))
        recommend_strength(IDENTITY, ['a.cr2', 'b.cr3'], loader=image_loader(photo),
                           progress=lambda *x: received.append(x))
        self.assertEqual(received, [(1, 2, 'a.cr2'), (2, 2, 'b.cr3')])

    def test_very_strong_lut_exposes_floor_warning(self):
        # A hard step at the LUT boundary can create pixel clipping even at 5%;
        # the algorithm must flag that condition, not mislabel 5% as "safe".
        # With ordinary clipped output and a linear blend, most guardrails scale
        # down at 5%; one extreme still could violate p95 bounds with stricter
        # constants, so test an explicitly mocked acceptance threshold.
        photo = Image.new('RGB', (20, 20), (128, 128, 128))
        with patch('raw_strength.MAX_LUMA_P95', 0.0001):
            report = recommend_strength(BLACK, ['a.cr2'], loader=image_loader(photo))
        self.assertEqual(report.recommended_percent, 5)
        self.assertFalse(report.minimum_passed)


if __name__ == '__main__':
    unittest.main()
