"""Adapt a camera Log LUT (e.g. Fujifilm F-Log2 -> film simulation) to photos.

Log LUTs expect a flat, scene-referred Log signal. Applied to an ordinary
sRGB photo they over-render contrast and saturation. This module builds a
new 33^3 CUBE whose input is display sRGB:

    sRGB photo -> approximate scene linear -> F-Gamut -> F-Log/F-Log2 -> Log LUT

The photo has already been tone-mapped by its camera, so scene linear can
only be approximated. Mid grey (18 %) is kept at 0.18 and highlights above it
in each channel are stretched in log2 space ("highlight stops"). The default of
2 stops puts photo white about 4.5 stops above grey.
A camera JPEG already carries the camera's S-curve, and the Log LUT adds its own,
so shadows below grey are pulled toward grey ("shadow compress", 0..0.8) to avoid
stacking contrast. Defaults were tuned on Canon PowerShot V1 photos with the
official Fujifilm F-Log2 film simulation LUTs: overall brightness and shadow
level then stay close to the camera JPEG while the colour rendering changes.
"auto" instead stretches until photo white renders as white in the Log LUT,
which brightens and washes out saturated colours with the official Fujifilm
LUTs. This is an approximation and must be checked with test photos. MIT licensed.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from lut import Cube, apply_cube

# Fujifilm F-Log / F-Log2 OETF constants (Fujifilm data sheets, as in colour-science).
LOG_CURVES = {
    'flog': dict(cut1=0.00089, a=0.555556, b=0.009468, c=0.344676, d=0.790453, e=8.735631, f=0.092864),
    'flog2': dict(cut1=0.000889, a=5.555556, b=0.064829, c=0.245281, d=0.384316, e=8.799461, f=0.092864),
    # Panasonic V-Log (V-Log/V-Gamut reference manual): x<0.01 -> 5.6x+0.125, else c*log10(x+b)+d.
    'vlog': dict(cut1=0.01, a=1.0, b=0.00873, c=0.241514, d=0.598206, e=5.6, f=0.125),
}
# F-Gamut uses the ITU-R BT.2020 primaries (D65). Linear BT.709/sRGB -> BT.2020.
BT709_TO_FGAMUT = np.array([
    [0.6274040, 0.3292820, 0.0433136],
    [0.0690970, 0.9195400, 0.0113612],
    [0.0163916, 0.0880132, 0.8955950],
], dtype=np.float64)
def _rgb_to_xyz(primaries, white=(0.3127, 0.3290)):
    xy = np.array(list(primaries) + [white], dtype=np.float64)
    xyz = np.column_stack([xy[:, 0] / xy[:, 1], np.ones(4), (1 - xy[:, 0] - xy[:, 1]) / xy[:, 1]])
    scale = np.linalg.solve(xyz[:3].T, xyz[3])
    return xyz[:3].T * scale


# V-Gamut primaries (Panasonic), D65. Linear BT.709/sRGB -> V-Gamut.
BT709_TO_VGAMUT = np.linalg.solve(
    _rgb_to_xyz(((0.730, 0.280), (0.165, 0.840), (0.100, -0.030))),
    _rgb_to_xyz(((0.640, 0.330), (0.300, 0.600), (0.150, 0.060))))
GAMUTS = {'flog': BT709_TO_FGAMUT, 'flog2': BT709_TO_FGAMUT, 'vlog': BT709_TO_VGAMUT}
GREY = 0.18
GREY_TO_WHITE = float(np.log2(1 / GREY))  # stops from 18 % grey to photo white
WHITE_TARGET = 0.98
DEFAULT_HIGHLIGHT_STOPS = 2.0
DEFAULT_SHADOW_COMPRESS = 0.35


@dataclass(frozen=True)
class AdaptResult:
    cube: Cube
    curve: str
    highlight_stops: float
    exposure: float
    white_out: float
    grey_out: float


def srgb_decode(v):
    v = np.clip(np.asarray(v, dtype=np.float64), 0, 1)
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def srgb_encode(v):
    v = np.clip(np.asarray(v, dtype=np.float64), 0, 1)
    return np.where(v <= 0.0031308, v * 12.92, 1.055 * v ** (1 / 2.4) - 0.055)


def log_encode(x, curve: str = 'flog2'):
    k = LOG_CURVES[curve]
    x = np.maximum(np.asarray(x, dtype=np.float64), 0)
    return np.where(x < k['cut1'], k['e'] * x + k['f'],
                    k['c'] * np.log10(k['a'] * x + k['b']) + k['d'])


def photo_to_scene(rgb, highlight_stops: float = DEFAULT_HIGHLIGHT_STOPS, exposure: float = 0.0,
                   shadow_compress: float = DEFAULT_SHADOW_COMPRESS):
    """Display sRGB -> approximate scene-linear BT.709 reflectance.

    Each channel is expanded on its own, mirroring the per-channel tone curve a
    camera applies. (Scaling all channels by the brightest one lifted the other
    channels and washed out saturated colours with the official Fujifilm LUTs.)
    """
    linear = srgb_decode(rgb)
    safe = np.maximum(linear, 1e-9)
    s = np.log2(safe / GREY)
    # Smooth expansion above grey: slope 1 at grey, photo white -> +GREY_TO_WHITE+highlight_stops.
    above = np.clip(s, 0, None)
    stretched = s + highlight_stops * (above / GREY_TO_WHITE) ** 2
    # Undo part of the camera S-curve below grey so contrast is not applied twice.
    stretched = np.where(stretched < 0, stretched * (1 - shadow_compress), stretched)
    return np.where(linear > 1e-9, GREY * 2 ** stretched, linear) * 2 ** exposure


def build_input_transform(rgb, curve='flog2', highlight_stops=DEFAULT_HIGHLIGHT_STOPS, exposure=0.0,
                          shadow_compress=DEFAULT_SHADOW_COMPRESS):
    scene = photo_to_scene(rgb, highlight_stops, exposure, shadow_compress)
    return log_encode(scene @ GAMUTS[curve].T, curve)


def _render(log_lut: Cube, rgb, curve, highlight_stops, exposure, output, shadow_compress=DEFAULT_SHADOW_COMPRESS):
    out = apply_cube(log_lut, build_input_transform(rgb, curve, highlight_stops, exposure,
                                                    shadow_compress).astype(np.float32))
    out = np.clip(out.astype(np.float64), 0, 1)
    if output == 'srgb':
        # Log LUTs target a BT.1886 (gamma 2.4) display; re-encode for sRGB viewing.
        out = srgb_encode(out ** 2.4)
    return out


def auto_highlight_stops(log_lut: Cube, curve='flog2', exposure=0.0, output='rec709',
                         shadow_compress=DEFAULT_SHADOW_COMPRESS) -> float:
    """Smallest stretch for which photo white renders at WHITE_TARGET (0..6 stops)."""
    white = np.ones((1, 3))
    def level(stops):
        return float(_render(log_lut, white, curve, stops, exposure, output, shadow_compress).mean())
    if level(0.0) >= WHITE_TARGET:
        return 0.0
    low, high = 0.0, 6.0
    if level(high) < WHITE_TARGET:
        return high
    for _ in range(30):
        mid = (low + high) / 2
        if level(mid) >= WHITE_TARGET:
            high = mid
        else:
            low = mid
    return round(high, 3)


def adapt_log_lut(log_lut: Cube, curve: str = 'flog2', highlight_stops: float | str = DEFAULT_HIGHLIGHT_STOPS,
                  exposure: float = 0.0, output: str = 'rec709', size: int = 33,
                  shadow_compress: float = DEFAULT_SHADOW_COMPRESS) -> AdaptResult:
    """Return a photo (display sRGB input) CUBE built from a Log-input LUT."""
    if curve not in LOG_CURVES:
        raise ValueError(f'Unknown Log curve {curve}; choose {", ".join(LOG_CURVES)}')
    if output not in ('rec709', 'srgb'):
        raise ValueError('output must be rec709 or srgb')
    if not -3 <= exposure <= 3:
        raise ValueError('exposure must be between -3 and +3 stops')
    if not 0 <= shadow_compress <= 0.8:
        raise ValueError('shadow compress must be between 0 and 0.8')
    if highlight_stops == 'auto':
        highlight_stops = auto_highlight_stops(log_lut, curve, exposure, output, shadow_compress)
    if not 0 <= highlight_stops <= 6:
        raise ValueError('highlight stops must be between 0 and 6')
    axis = np.linspace(0, 1, size)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing='ij'), -1)
    data = _render(log_lut, grid.reshape(-1, 3), curve, highlight_stops, exposure, output, shadow_compress)
    cube = Cube(data.reshape(size, size, size, 3).astype(np.float32), np.zeros(3), np.ones(3),
                f'{log_lut.title or "Log LUT"} (photo)')
    probe = _render(log_lut, np.array([[1., 1., 1.], [0.4614, 0.4614, 0.4614]]), curve,
                    highlight_stops, exposure, output, shadow_compress)
    return AdaptResult(cube, curve, float(highlight_stops), float(exposure),
                       float(probe[0].mean()), float(probe[1].mean()))
