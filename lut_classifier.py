"""LUT content-based classification (NO filenames, titles, or comment heuristics).

The RGB lookup table is all we have. Strongly clipped/steep neutral transfer
functions can suggest technical display transforms, while significant chromatic
styling in the presence of that signature can suggest a hybrid LUT. Neither
classification is proof of source/target gamut: a 3D table has no intrinsic
color-space metadata, and a creative curve may mimic a technical transfer.

Conservative unknown results and a user override are therefore intentional.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from lut import apply_cube


@dataclass(frozen=True)
class LUTClassification:
    kind: str                 # creative / technical / hybrid / uncertain
    confidence: str           # high / medium / low
    markers: tuple[str, ...]  # internal RGB-table signatures (not metadata)
    neutral_rms: float
    dark_plateau: float
    bright_plateau: float
    neutral_tint: float


def _linear_sample(x: np.ndarray, y: np.ndarray, at: float) -> float:
    return float(np.interp(at, x, y))


def classify_lut(cube) -> LUTClassification:
    """Classify using only the 3D RGB mapping, with conservative uncertainty.

    Identical CUBE tables MUST produce identical results irrespective of title,
    file name, comments or LUT size. Samples are normalized input RGB, passed
    through the LUT's actual input domain.
    """
    axis = np.linspace(0., 1., 257, dtype=np.float32)
    neutrals = np.stack((axis, axis, axis), axis=-1)
    mapped = apply_cube(cube, cube.domain_min + neutrals * (cube.domain_max - cube.domain_min))
    luminance = mapped.mean(axis=1)
    # Normalize neutral endpoint levels: hybrid LUTs can deliberately tint white
    # (and compress its luminance) without removing an existing flat shoulder.
    span = max(1e-5, float(luminance[-1] - luminance[0]))
    normalized = (luminance - luminance[0]) / span
    channel_spread = mapped.max(axis=1) - mapped.min(axis=1)
    rms = float(np.sqrt(np.mean((luminance - axis) ** 2)))

    # Plateau locations measure a table's BLACK/WHITE *output*, not the names
    # of its input/output spaces. A 2% threshold tolerates interpolation noise.
    low = normalized <= 0.02
    high = normalized >= 0.98
    dark_end = float(axis[np.where(low)[0][-1]]) if low.any() else 0.0
    bright_start = float(axis[np.where(high)[0][0]]) if high.any() else 1.0
    dark_plateau = dark_end
    bright_plateau = 1.0 - bright_start
    # Localized breaks in the neutral ramp indicate a transfer function, but
    # alone are insufficient to prove it is technical.
    delta = np.diff(normalized) * 256.0
    steep = bool(np.percentile(delta, 90) >= 1.55)
    hard_dark = dark_plateau >= .075
    hard_bright = bright_plateau >= .12
    compressed = dark_plateau + bright_plateau >= .27
    strong_tonal = rms >= .13
    markers: list[str] = []
    if hard_dark:
        markers.append('deep_black_plateau')
    if hard_bright:
        markers.append('early_white_plateau')
    if steep:
        markers.append('steep_transfer_segment')
    if strong_tonal:
        markers.append('large_neutral_remap')
    if compressed:
        markers.append('compressed_input_span')

    # Neutral axis split toning is a fairly specific *creative* signal, whereas
    # color/gamut matrices can change saturated hues without creative intent.
    # Exclude extreme endpoints and require it on ordinary midtone neutrals.
    mid = (axis >= .18) & (axis <= .82)
    tint = float(np.percentile(channel_spread[mid], 85))
    styled_neutrals = tint >= .055
    if styled_neutrals:
        markers.append('colored_neutral_ramp')

    # A technical signature requires multiple features; strong per-channel
    # transformations by themselves (such as gamut matrices) are ambiguous.
    technical_signal = ((hard_dark and hard_bright and steep)
                        or (compressed and steep and strong_tonal)
                        or (hard_bright and strong_tonal and steep and dark_plateau >= .04))
    if technical_signal:
        if styled_neutrals:
            return LUTClassification('hybrid', 'medium', tuple(markers), rms,
                                     dark_plateau, bright_plateau, tint)
        return LUTClassification('technical', 'medium' if compressed else 'low',
                                 tuple(markers), rms, dark_plateau, bright_plateau, tint)

    # A gamut-only transformation can leave every neutral exactly unchanged.
    # Detect matrix-like behavior on colored samples. A creative saturation
    # matrix looks mathematically the same, so this is UNCERTAIN, not technical.
    levels = np.linspace(0., 1., 5, dtype=np.float32)
    colors = np.stack(np.meshgrid(levels, levels, levels, indexing='ij'), -1).reshape(-1, 3)
    mapped_colors = apply_cube(cube, cube.domain_min + colors * (cube.domain_max - cube.domain_min))
    design = np.column_stack((colors, np.ones(len(colors), dtype=np.float32)))
    coefficients = np.linalg.lstsq(design, mapped_colors, rcond=None)[0]
    matrix_error = float(np.sqrt(np.mean((design @ coefficients - mapped_colors) ** 2)))
    off_diagonal = coefficients[:3].copy()
    np.fill_diagonal(off_diagonal, 0.)
    matrix_like = (matrix_error <= .018 and
                   float(np.max(np.abs(off_diagonal))) >= .06 and rms <= .08)
    if matrix_like:
        markers.append('gamut_or_saturation_matrix')
        return LUTClassification('uncertain', 'low', tuple(markers), rms,
                                 dark_plateau, bright_plateau, tint)

    # A near-identity neutral transfer has no obvious technical tone remap.
    # But a pure gamut conversion can preserve this ramp, so confidence is
    # deliberately only medium. We never assert a known Rec.709/sRGB gamut.
    if not (hard_dark or hard_bright) and rms < .12:
        return LUTClassification('creative', 'medium', tuple(markers), rms,
                                 dark_plateau, bright_plateau, tint)

    # Conservative: a strong film contrast curve and a technical transfer can
    # share the same 3D table; guesses must not restrict user workflows.
    return LUTClassification('uncertain', 'low', tuple(markers), rms,
                             dark_plateau, bright_plateau, tint)
