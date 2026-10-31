import tempfile
import unittest
from pathlib import Path
import numpy as np
from lut import load_cube, apply_cube, write_cube

class TestCube(unittest.TestCase):
    def test_identity_and_resample(self):
        with tempfile.TemporaryDirectory() as folder:
            f = Path(folder) / 'id.cube'
            with f.open('w') as out:
                out.write('LUT_3D_SIZE 2\n')
                for b in (0,1):
                    for g in (0,1):
                        for r in (0,1):
                            out.write(f'{r} {g} {b}\n')
            lut = load_cube(f)
            x = np.array([[0.1,0.6,0.9],[1,0,0]], dtype=np.float32)
            np.testing.assert_allclose(apply_cube(lut,x),x,rtol=0,atol=1e-6)
            out = Path(folder) / 'norm.cube'
            write_cube(lut,out,33)
            norm = load_cube(out)
            np.testing.assert_allclose(apply_cube(norm,x),x,rtol=0,atol=1e-6)

    def test_reject_1d(self):
        with tempfile.TemporaryDirectory() as folder:
            f = Path(folder) / 'bad.cube'
            f.write_text('LUT_1D_SIZE 2\n0 0 0\n1 1 1\n')
            with self.assertRaises(ValueError): load_cube(f)

if __name__ == '__main__': unittest.main()
