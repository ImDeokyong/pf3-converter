"""Content-only classification tests. No filename or TITLE based detection."""
import tempfile
from pathlib import Path
import unittest
import numpy as np
from lut import Cube, load_cube, write_cube
from lut_classifier import classify_lut
from i18n import tr, validate_catalog


def make_cube(fn, size=17, title='creative_movie_looks_Rec709.cube'):
    v = np.linspace(0, 1, size, dtype=np.float32)
    grid = np.stack(np.meshgrid(v, v, v, indexing='ij'), -1)
    data = np.asarray(fn(grid), dtype=np.float32)
    return Cube(data, np.zeros(3), np.ones(3), title)


def log_to_display(x):
    return np.clip((x - .12) / .62, 0, 1) ** 1.1


class LUTStructuralClassifierTests(unittest.TestCase):
    def test_normal_creative_and_identity(self):
        for fx in (lambda x: x, lambda x: np.clip(x * .93 + .025, 0, 1)):
            result = classify_lut(make_cube(fx))
            self.assertEqual(result.kind, 'creative')
            self.assertIn(result.confidence, ('medium', 'low'))

    def test_log_display_transform_is_technical_even_if_file_claims_creative(self):
        cube = make_cube(log_to_display, title='Portrait_Film_Grain_look')
        report = classify_lut(cube)
        self.assertEqual(report.kind, 'technical')
        self.assertIn('compressed_input_span', report.markers)
        self.assertGreater(report.dark_plateau, .09)
        self.assertGreater(report.bright_plateau, .18)

    def test_log_plus_color_cast_is_hybrid(self):
        cube = make_cube(lambda x: log_to_display(x) * np.array([1.04, .98, .90]))
        report = classify_lut(cube)
        self.assertEqual(report.kind, 'hybrid')
        self.assertIn('colored_neutral_ramp', report.markers)

    def test_ambiguous_strong_film_curve_does_not_force_technical(self):
        curve = make_cube(lambda x: np.clip((x - .08) / .84, 0, 1) ** 1.2)
        self.assertEqual(classify_lut(curve).kind, 'uncertain')

    def test_gamut_matrix_is_uncertain_not_falsely_creative(self):
        def matrix(x):
            # Neutral preserved; channel mixing can be either gamut conversion
            # or an artistic saturation operation (cannot distinguish).
            return np.stack((1.14*x[...,0]-.07*x[...,1]-.07*x[...,2],
                             -.06*x[...,0]+1.12*x[...,1]-.06*x[...,2],
                             -.07*x[...,0]-.07*x[...,1]+1.14*x[...,2]), -1)
        report = classify_lut(make_cube(matrix))
        self.assertEqual(report.kind, 'uncertain')
        self.assertIn('gamut_or_saturation_matrix', report.markers)

    def test_title_filename_and_comments_do_not_affect_result(self):
        cube = make_cube(log_to_display)
        with tempfile.TemporaryDirectory() as temp:
            paths = [Path(temp)/'SLog3_to_Rec709.cube', Path(temp)/'Cinematic_look.cube']
            for path in paths:
                write_cube(cube, path, size=17)
            first = paths[0].read_text('utf-8')
            paths[1].write_text(first.replace('PF3 Converter Resampled', 'Cool Creative Preset')
                                .replace('LUT_3D_SIZE', '# Creative LUT (misleading)\nLUT_3D_SIZE'),
                                encoding='utf-8')
            a, b = (classify_lut(load_cube(path)) for path in paths)
            self.assertEqual(a, b)
            self.assertEqual(a.kind, 'technical')

    def test_nondefault_domain_is_analyzed_in_table_coordinates(self):
        cube = make_cube(log_to_display)
        cube.domain_min[:] = [-.1, -.1, -.1]
        cube.domain_max[:] = [1.1, 1.1, 1.1]
        self.assertEqual(classify_lut(cube).kind, 'technical')

    def test_four_locales_are_complete(self):
        validate_catalog()
        for code in ('ko', 'en', 'ja', 'zh-CN'):
            self.assertTrue(tr(code, 'lut_class_result', kind='Technical', confidence='medium'))
            self.assertTrue(tr(code, 'lut_class_override_auto'))

if __name__ == '__main__':
    unittest.main()
