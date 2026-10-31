"""Conservative RAW-reference strength recommendation for display-referred LUTs.

This is a transparent *image safety heuristic*, not a claim of aesthetically
optimal grading or a Canon DPP/Adobe rendering match. The RAW decoder renders
camera-white-balanced sRGB before analysis; Log/technical LUTs require the
correct input color space and must not be treated as creative sRGB LUTs.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import numpy as np
from PIL import Image

from canon_fit import target_rgb
from photo_loader import RAW_EXTENSIONS, load_photo

MAX_PHOTOS = 5
MAX_SAMPLE_PIXELS = 30000
# Conservative acceptance limits in *gamma-encoded display sRGB*.
MAX_LUMA_P95 = 0.14       # ~36/255 display-code values
MAX_RGB_P95 = 0.24        # maximum per-pixel channel shift, p95
MAX_CHROMA_GAIN_P95 = 0.22
MAX_ADDITIONAL_CLIP = 0.01
MAX_ADDITIONAL_CRUSH = 0.01
LUMA_WEIGHTS = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
CANDIDATES = tuple(range(100, 0, -5))  # highest acceptable strength first


@dataclass(frozen=True)
class PhotoMetrics:
    filename: str
    luma_p95: float
    rgb_p95: float
    chroma_gain_p95: float
    additional_clip: float
    additional_crush: float


@dataclass(frozen=True)
class StrengthResult:
    recommended_percent: int
    photos: int
    metrics: tuple[PhotoMetrics, ...]
    minimum_passed: bool
    note: str = 'Assumes creative/display-referred sRGB LUT; not valid for unconverted Log LUTs.'


def _sample_srgb(photo: Image.Image) -> np.ndarray:
    """Downsize before conversion to bound peak interpolation memory."""
    small = photo.convert('RGB') if photo.mode != 'RGB' else photo
    small.thumbnail((480, 480), Image.Resampling.BOX)
    pixels = np.asarray(small, dtype=np.uint8).reshape(-1, 3)
    if len(pixels) > MAX_SAMPLE_PIXELS:
        indices = np.linspace(0, len(pixels) - 1, MAX_SAMPLE_PIXELS, dtype=np.intp)
        pixels = pixels[indices]
    return pixels.astype(np.float32) / 255.0


def _photo_metrics(rgb: np.ndarray, transformed: np.ndarray, filename: str) -> PhotoMetrics:
    luma0 = rgb @ LUMA_WEIGHTS
    luma1 = transformed @ LUMA_WEIGHTS
    chroma0 = rgb.max(axis=1) - rgb.min(axis=1)
    chroma1 = transformed.max(axis=1) - transformed.min(axis=1)
    clip_new = np.any((transformed >= .995) & (rgb < .98), axis=1)
    # Only count *new* black crushing of initially visible shadow detail.
    crush_new = (luma0 > .035) & (luma1 < .015)
    return PhotoMetrics(
        filename=filename,
        luma_p95=float(np.percentile(np.abs(luma1 - luma0), 95)),
        rgb_p95=float(np.percentile(np.max(np.abs(transformed - rgb), axis=1), 95)),
        chroma_gain_p95=float(np.percentile(np.maximum(0, chroma1 - chroma0), 95)),
        additional_clip=float(np.mean(clip_new)),
        additional_crush=float(np.mean(crush_new)),
    )


def _acceptable(m: PhotoMetrics) -> bool:
    return (m.luma_p95 <= MAX_LUMA_P95 and m.rgb_p95 <= MAX_RGB_P95
            and m.chroma_gain_p95 <= MAX_CHROMA_GAIN_P95
            and m.additional_clip <= MAX_ADDITIONAL_CLIP
            and m.additional_crush <= MAX_ADDITIONAL_CRUSH)


def recommend_strength(cube, raw_paths, *, loader: Callable = load_photo, progress=None) -> StrengthResult:
    """Analyze 1–5 actual RAW photographs and pick the strongest safe blend.

    `loader` is injected for offline tests. It must return (PIL image, note),
    like photo_loader.load_photo. All frames are decoded sequentially and only
    sampled pixels are retained. The strictest sample controls the result.
    A 5% floor is returned if even that fails the guardrails (flagged as such).
    """
    paths = tuple(Path(p) for p in raw_paths)
    if not 1 <= len(paths) <= MAX_PHOTOS:
        raise ValueError('Select between 1 and 5 RAW photos.')
    if any(p.suffix.lower() not in RAW_EXTENSIONS for p in paths):
        raise ValueError('RAW strength analysis accepts camera RAW files only.')
    if len({str(p.resolve()).casefold() for p in paths}) != len(paths):
        raise ValueError('Duplicate RAW photos are not allowed.')

    frames = []
    for index, path in enumerate(paths, 1):
        if progress is not None:
            progress(index, len(paths), path.name)
        image, _ = loader(path)
        try:
            frames.append((path.name, _sample_srgb(image)))
        finally:
            image.close()

    # A one-time CUBE evaluation lets us test all 20 strengths without repeated
    # expensive 3D LUT interpolation. target_rgb also clips final CUBE output.
    targets = [(name, rgb, target_rgb(cube, rgb, 1)) for name, rgb in frames]
    chosen, chosen_metrics, passed = 5, (), False
    for percent in CANDIDATES:
        strength = percent / 100
        reports = tuple(_photo_metrics(rgb, rgb + (lut_rgb-rgb)*strength, name)
                        for name, rgb, lut_rgb in targets)
        if all(_acceptable(r) for r in reports):
            chosen, chosen_metrics, passed = percent, reports, True
            break
        if percent == CANDIDATES[-1]:
            chosen_metrics = reports
    return StrengthResult(chosen, len(paths), chosen_metrics, passed)
