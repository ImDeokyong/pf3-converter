"""Panasonic LUMIX Real Time LUT .cube exporter.

Samples the display-referred Cube transform into a full-range 33-point 3D LUT.
A base Photo Style tag selects camera rendering *before* the LUT; this module
never pretends to convert sRGB into the chosen manufacturer's camera pipeline.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile

import numpy as np
from lut import Cube, apply_cube, load_cube

# Published by Panasonic in the S9 / S5II LUT Library documentation.
# Camera models/firmware differ: availability of individual Photo Styles is not guaranteed.
PHOTO_STYLES = {
    'STD': 'Standard',
    'NAT': 'Natural',
    'VIVD': 'Vivid',
    'FLAT': 'Flat',
    'PORT': 'Portrait',
    'LAND': 'Landscape',
    'LCLASN': 'L.ClassicNeo',
    'MONO': 'Monochrome',
    'LMONO': 'L.Monochrome',
    'LMONOD': 'L.Monochrome D',
    'LMONOS': 'L.Monochrome S',
    'LEICAMONO': 'LEICA Monochrome',
    'CNED2': 'Cinelike D2',
    'CNEV2': 'Cinelike V2',
    '709L': 'Like709',
    '2100HLG': 'Like2100(HLG)',
    '2100HLGF': 'Like2100(HLG) Full Range',
    'VLOG': 'V-Log',
}
GRID_SIZE = 33


def _safe_title(title: str) -> str:
    # ASCII title avoids locale issues on cameras. Prevent CUBE directive injection.
    text = re.sub(r'[^\x20-\x7e]', '_', str(title or 'PF3 Converter LUT'))
    text = re.sub(r'["\\\r\n]', '_', text).strip()[:64]
    return text or 'PF3 Converter LUT'


def export_srgb_cube(
    cube: Cube,
    path: str | Path,
    *,
    style: str | None = None,
    strength: float = 1.0,
    title: str = 'PF3 Converter LUT',
) -> dict:
    """Export a 33³ sRGB display look for Photoshop or tagged for LUMIX.

    The source Cube must be a display-referred creative transform *already
    matching the camera's selected Photo Style*. No automatic color management.
    Strength is blended in signal RGB before baking into the LUT, not recorded as
    a separate Panasonic opacity parameter.
    """
    destination = Path(path).expanduser().resolve()
    if destination.suffix.lower() != '.cube':
        raise ValueError('LUMIX output filename must end in .cube')
    if style is not None and style not in PHOTO_STYLES:
        raise ValueError('Unsupported LUMIX base Photo Style: ' + str(style))
    try:
        strength = float(strength)
    except (ValueError, TypeError) as exc:
        raise ValueError('Strength must be between 0 and 1') from exc
    if not np.isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError('Strength must be between 0 and 1')
    if not np.isfinite(cube.data).all():
        raise ValueError('Input LUT has non-finite values')

    safe_title = _safe_title(title)
    axis = np.linspace(0., 1., GRID_SIZE, dtype=np.float32)
    out_of_range = 0
    num_values = GRID_SIZE ** 3 * 3
    temporary = None
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile('w', encoding='ascii', newline='\n',
                                         prefix='.picture_bridge_', suffix='.partial',
                                         dir=destination.parent, delete=False) as fp:
            temporary = Path(fp.name)
            fp.write(f'TITLE "{safe_title}"\n')
            if style is not None:
                fp.write(f'#LUMIXPHOTOSTYLE {style}\n')
            fp.write('LUT_3D_SIZE 33\n')
            # Omit optional DOMAIN directives for broader camera parser compatibility;
            # 0..1 is the CUBE default and values are explicitly clipped.
            # CUBE standard: R-fastest, then G, then B.
            for b in axis:
                for g in axis:
                    points = np.column_stack((axis, np.full(GRID_SIZE, g),
                                              np.full(GRID_SIZE, b)))
                    transformed = apply_cube(cube, points)
                    mixed = points + strength * (transformed - points)
                    out_of_range += int(np.count_nonzero((mixed < 0) | (mixed > 1)))
                    for row in np.clip(mixed, 0, 1):
                        fp.write(f'{row[0]:.9f} {row[1]:.9f} {row[2]:.9f}\n')
        # Structural validation BEFORE replacing the destination.
        verified = load_cube(temporary)
        if verified.size != GRID_SIZE or not np.isfinite(verified.data).all():
            raise ValueError('Generated CUBE failed structural validation')
        with temporary.open('r', encoding='ascii') as verify:
            header = ''.join(verify.readline() for _ in range(3))
            if style is not None and f'#LUMIXPHOTOSTYLE {style}\n' not in header:
                raise ValueError('LUMIX Photo Style tag missing')
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

    return {
        'file': str(destination), 'bytes': destination.stat().st_size,
        'format': ('Panasonic LUMIX Real Time LUT CUBE' if style is not None else 'Photoshop sRGB CUBE'), 'size': GRID_SIZE,
        'style': style, 'style_name': PHOTO_STYLES.get(style),
        'strength': strength, 'clamped_component_fraction': out_of_range / num_values,
        'warnings': ([
            'A display-referred sRGB lookup table; Adobe Lightroom develop preset rendering is approximate.',
            'The Photoshop document must be in sRGB for the intended reference values.',
        ] if style is None else [
            'No automatic Adobe-to-LUMIX camera color pipeline conversion occurs.',
            'Select the Photo Style used to create the LUT; STD is a reference choice, not a universal conversion.',
            'Lightroom develop presets can only be approximated in a standalone LUT.',
            'Physical Panasonic camera validation is required.',
        ]),
    }


def export_lumix_cube(cube: Cube, path: str | Path, *, style: str = 'STD',
                      strength: float = 1.0, title: str = 'PF3 Converter LUT') -> dict:
    """Compatibility wrapper: exact same sRGB RGB rows as Photoshop exporter."""
    return export_srgb_cube(cube, path, style=style, strength=strength, title=title)
