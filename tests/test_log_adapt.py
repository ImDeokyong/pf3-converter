import unittest

import numpy as np
from lut import Cube, apply_cube
from log_adapt import (LOG_CURVES, BT709_TO_FGAMUT, adapt_log_lut, auto_highlight_stops,
                       log_encode, photo_to_scene, srgb_encode)


def flog2_decode(v):
    k = LOG_CURVES['flog2']
    cut2 = k['e'] * k['cut1'] + k['f']
    return np.where(v < cut2, (v - k['f']) / k['e'], (10 ** ((v - k['d']) / k['c']) - k['b']) / k['a'])


def synthetic_flog2_lut(size=33):
    """F-Log2/F-Gamut -> BT.709 display with a simple filmic curve, like a camera Log LUT."""
    axis = np.linspace(0, 1, size)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing='ij'), -1)
    linear = flog2_decode(grid) @ np.linalg.inv(BT709_TO_FGAMUT).T
    linear = np.clip(linear, 0, None)
    shaped = linear / (linear + 3.0) * 2.0  # white at ~+4 stops, rolls off highlights
    display = np.clip(shaped, 0, 1) ** (1 / 2.4)
    return Cube(display.astype(np.float32), np.zeros(3), np.ones(3), 'synthetic')


class LogCurveTests(unittest.TestCase):
    def test_flog2_grey_code_value(self):
        # Fujifilm F-Log2: 18 % reflectance encodes to about 0.391 (normalized code value).
        self.assertAlmostEqual(float(log_encode(0.18, 'flog2')), 0.391, places=3)
        self.assertAlmostEqual(float(log_encode(0.18, 'flog')), 0.459, places=2)

    def test_scene_keeps_grey_and_expands_white(self):
        grey_srgb = float(srgb_encode(0.18))
        scene = photo_to_scene(np.array([[grey_srgb] * 3, [1., 1., 1.]]), highlight_stops=2.0)
        dark = photo_to_scene(np.array([[0.1] * 3]), 2.0, shadow_compress=0.0)[0, 0]
        self.assertGreater(photo_to_scene(np.array([[0.1] * 3]), 2.0, shadow_compress=0.4)[0, 0], dark)
        np.testing.assert_allclose(scene[0], 0.18, rtol=1e-6)
        np.testing.assert_allclose(scene[1], 0.18 * 2 ** (np.log2(1 / 0.18) + 2), rtol=1e-6)

    def test_scene_is_monotonic_and_per_channel(self):
        ramp = np.linspace(0, 1, 101)[:, None].repeat(3, 1)
        scene = photo_to_scene(ramp, 3.0)[:, 0]
        self.assertTrue(np.all(np.diff(scene) >= 0))
        colour = photo_to_scene(np.array([[0.8, 0.4, 0.2]]), 2.0)[0]
        for channel, value in enumerate((0.8, 0.4, 0.2)):
            self.assertAlmostEqual(colour[channel], photo_to_scene(np.array([[value] * 3]), 2.0)[0, 0], places=9)


class AdaptTests(unittest.TestCase):
    def test_auto_highlight_makes_white_white_and_grey_reasonable(self):
        log_lut = synthetic_flog2_lut()
        result = adapt_log_lut(log_lut, 'flog2', 'auto')
        self.assertGreater(result.highlight_stops, 0)
        self.assertGreaterEqual(result.white_out, 0.975)
        self.assertTrue(0.3 < result.grey_out < 0.75, result.grey_out)
        self.assertEqual(result.cube.size, 33)

    def test_default_highlight_expansion(self):
        result = adapt_log_lut(synthetic_flog2_lut(9), 'flog2')
        self.assertEqual(result.highlight_stops, 2.0)
        self.assertLess(result.white_out, adapt_log_lut(synthetic_flog2_lut(9), 'flog2', 'auto').white_out + 1e-6)

    def test_plain_application_overdoes_contrast_compared_with_adapted(self):
        log_lut = synthetic_flog2_lut()
        shadow = np.array([[0.1, 0.1, 0.1]], dtype=np.float32)
        naive = float(apply_cube(log_lut, shadow).mean())
        adapted = float(apply_cube(adapt_log_lut(log_lut, 'flog2', shadow_compress=0.0).cube, shadow).mean())
        # sRGB 0.1 is a real shadow; feeding it as F-Log2 code crushes it toward black.
        self.assertGreater(adapted, naive * 2)

    def test_neutral_input_stays_neutral(self):
        cube = adapt_log_lut(synthetic_flog2_lut(), 'flog2').cube
        neutral = apply_cube(cube, np.linspace(0, 1, 9)[:, None].repeat(3, 1).astype(np.float32))
        self.assertLess(float(np.abs(neutral - neutral.mean(1, keepdims=True)).max()), 0.01)

    def test_validation(self):
        lut = synthetic_flog2_lut(9)
        with self.assertRaises(ValueError):
            adapt_log_lut(lut, 'slog3')
        with self.assertRaises(ValueError):
            adapt_log_lut(lut, 'flog2', exposure=5)
        with self.assertRaises(ValueError):
            adapt_log_lut(lut, 'flog2', shadow_compress=0.9)
        self.assertEqual(auto_highlight_stops(Cube(np.ones((2, 2, 2, 3), np.float32), np.zeros(3), np.ones(3))), 0.0)


if __name__ == '__main__':
    unittest.main()
