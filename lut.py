"""Strict .cube parser and trilinear interpolation. MIT licensed."""
from dataclasses import dataclass
from pathlib import Path
import numpy as np

@dataclass
class Cube:
    data: np.ndarray
    domain_min: np.ndarray
    domain_max: np.ndarray
    title: str = ''

    @property
    def size(self):
        return self.data.shape[0]


def load_cube(path):
    p = Path(path)
    if p.stat().st_size > 128 * 1024 * 1024:
        raise ValueError('LUT file exceeds 128 MiB limit')
    size = None
    title = ''
    domain_min = [0., 0., 0.]
    domain_max = [1., 1., 1.]
    rows = []
    for line_no, line in enumerate(p.read_text(encoding='utf-8-sig').splitlines(), 1):
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        key = parts[0].upper()
        if key == 'TITLE':
            title = line[5:].strip().strip('"')
        elif key == 'LUT_3D_SIZE':
            if size is not None or rows:
                raise ValueError(f'Line {line_no}: repeated or misplaced LUT_3D_SIZE')
            size = int(parts[1])
            if not 2 <= size <= 65:
                raise ValueError('Only LUT sizes 2 through 65 are supported')
        elif key == 'DOMAIN_MIN':
            domain_min = [float(x) for x in parts[1:]]
        elif key == 'DOMAIN_MAX':
            domain_max = [float(x) for x in parts[1:]]
        elif key == 'LUT_1D_SIZE':
            raise ValueError('1D LUTs are not supported; expected LUT_3D_SIZE')
        elif len(parts) == 3:
            if size is None:
                raise ValueError('LUT_3D_SIZE must precede data')
            try:
                rows.append([float(x) for x in parts])
            except ValueError as ex:
                raise ValueError(f'Line {line_no}: invalid RGB value') from ex
            if len(rows) > size ** 3:
                raise ValueError('Too many LUT rows')
        else:
            raise ValueError(f'Line {line_no}: unsupported CUBE directive: {parts[0]}')
    if size is None or len(rows) != size ** 3:
        raise ValueError(f'Expected {size ** 3 if size else "?"} RGB rows; got {len(rows)}')
    low, high = np.array(domain_min), np.array(domain_max)
    if low.shape != (3,) or high.shape != (3,) or np.any(high <= low):
        raise ValueError('Invalid LUT input domain')
    raw = np.array(rows, dtype=np.float32)
    if not np.isfinite(raw).all():
        raise ValueError('LUT contains non-finite RGB values')
    # CUBE: red index varies fastest, then green, then blue.
    data = raw.reshape(size, size, size, 3).transpose(2, 1, 0, 3)
    return Cube(data, low, high, title)


def apply_cube(cube, rgb):
    """Apply to floating point RGB arrays in [0,1]. Shapes (...,3)."""
    x = np.asarray(rgb, dtype=np.float32)
    if x.shape[-1] != 3:
        raise ValueError('RGB input must end in 3 channels')
    t = np.clip((x - cube.domain_min) / (cube.domain_max - cube.domain_min), 0, 1) * (cube.size - 1)
    i0 = np.floor(t).astype(np.int32)
    i1 = np.minimum(i0 + 1, cube.size - 1)
    f = (t - i0).astype(np.float32)
    result = np.zeros_like(x, dtype=np.float32)
    for r in (0, 1):
        ir = i1[..., 0] if r else i0[..., 0]
        wr = f[..., 0] if r else 1 - f[..., 0]
        for g in (0, 1):
            ig = i1[..., 1] if g else i0[..., 1]
            wg = f[..., 1] if g else 1 - f[..., 1]
            for b in (0, 1):
                ib = i1[..., 2] if b else i0[..., 2]
                wb = f[..., 2] if b else 1 - f[..., 2]
                result += cube.data[ir, ig, ib] * (wr * wg * wb)[..., None]
    return result


def write_cube(cube, path, size=33):
    if size not in (17, 33, 65):
        raise ValueError('Output grid must be 17, 33 or 65')
    lin = np.linspace(0., 1., size, dtype=np.float32)
    with open(path, 'w', encoding='utf-8', newline='\n') as out:
        out.write('TITLE "PF3 Converter Resampled"\nLUT_3D_SIZE %d\n' % size)
        # Export LUT in normalized RGB [0,1] domain, embedding original domain adjustments.
        for b in lin:
            for g in lin:
                points = np.column_stack((lin, np.full(size, g), np.full(size, b)))
                transformed = apply_cube(cube, points)
                for row in transformed:
                    out.write('%.9f %.9f %.9f\n' % tuple(row))
