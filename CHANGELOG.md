# PF3 Converter Changelog

## v1.1 (2026-10-30) — Panasonic LUMIX and sRGB CUBE outputs

- Added CUBE/XMP → 33³ standard CUBE for Photoshop sRGB documents.
- Added LUMIX CUBE output using `#LUMIXPHOTOSTYLE` base-style tag,
  33³ full-range LUT values, clipping report and atomic save.
- Photoshop CUBE and LUMIX CUBE use the identical RGB sampling, clipping,
  rounding and intensity setting; LUMIX differs only in Photo Style metadata.
- Added XMP → CUBE support, GUI selection, CLI `--lumix-style`, translations
  in four languages and relevant regression tests.
- Removed the cumbersome Lightroom TIFF reference-chart and paired-TIFF fitting
  workflow from GUI, CLI, implementation, tests and documentation.
- Simplified the LUMIX help text and removed the bottom PF3 camera-compatibility
  note from the main window. Canon PF3 generation code remains untouched.
- Lightroom develop preset conversion is still approximate; the software does
  not emulate the Adobe RAW pipeline or perform automatic camera color conversion.

## v1.0 — Content-based LUT type estimate and Creative RAW optimizer

- Add `lut_classifier.py`: inspect **only the CUBE RGB table**, never file names,
  TITLE, comments or metadata. Estimate Creative, Technical, Hybrid or Uncertain.
- Analyze neutral transfer curves, black/white plateaus, tone remapping and
  neutral channel tint. Recognize matrix-like gamut/saturation ambiguity.
- Display confidence and classification inline in Korean, English, Japanese and
  Simplified Chinese, with a **manual type override** for false positives.
- Keep existing RAW 1–5 photo strength recommendation for Creative LUTs. Do not
  offer this heuristic for likely Technical/Hybrid unless the user overrides.
  Uncertain LUTs remain eligible; XMP behavior remains unchanged.
- Do **not** add Technical LUT warning popups, block PF3/XMP export, or alter
  actual LUT transform data and underlying conversion algorithms.
- Document that 3D LUT RGB data cannot guarantee input/output colorspaces and
  that log/gamut conversion is not implemented. Added classifier and GUI tests.

## PF3 Converter v1.0 — RAW reference strength recommendation (Mode B)

- Added `raw_strength.py`: analyze **1–5** RAW reference photos and recommend the
  **highest conservative** CUBE/XMP look intensity passing guardrails on all images.
- Added asynchronous GUI button with results applied directly to the existing
  PF3 strength slider and both preview/export paths, without blocking the UI.
- Changed initial GUI strength from 100% to **provisional 50%**.
- Four-language interface labels, progress, warnings and errors added.
- The analysis assumes camera-WB, non-auto-brightened, rendered sRGB RAW; cannot
  recover technical Log/gamut LUT input transforms or assess creative aesthetics.
- `rawpy` remains necessary for RAW support; no new dependency added.
- Added deterministic analyzer and GUI tests. Version remains 1.0 by request.

## v1.0 — Four-language interface update (2026-10-28)

- Added runtime UI language selection: 한국어, English, 日本語, 简体中文.
- Localized main controls, preview toolbar and modes, status messages, file-dialog
  filters, success/error dialogs, common XMP conversion warnings, and About panel.
- Remember language across launches via local settings.json; operate fully offline.
- Added quick-start instructions in Korean, English, Japanese, and Simplified Chinese.
- Preserved PF3 Converter v1.0 branding (Created by ImDeokyong) and all file converters.
- Added localization catalog validation and GUI integration regression tests.


## v1.0 (2026-10-28)

- Rename the application to **PF3 Converter** and set version **1.0**.
- Credit **ImDeokyong** as the creator in the GUI, About window, CLI and documentation.
- Package the Windows executable as `PF3Converter.exe` and embed Windows file
  metadata (product name, version 1.0 and ImDeokyong).
- Default Adobe creative profiles to the `PF3 Converter` group.
- Retain v0.6 CUBE/XMP/PF3 conversion, high-resolution preview and native export.


## v0.6 (2026-10-28)

- Add `.xmp` to existing CUBE/PF3 GUI source picker.
- Decode XMP creative profile RGBTable with bounded Adobe-base85/zlib parser,
  color-space metadata and sRGB conversion.
- Convert supported XMP develop-preset sliders/curves/HSL/color grading into
  explicitly approximate sampled RGB cube; flag ignored features.
- Export real Adobe creative profile XMP with an embedded 32³ RGBTable from CUBE,
  including round-trip verification and source resampling error.
- Route CLI based on source/output file extensions, preserve Windows Canon
  PSE/DLL PF3 pipeline, maintain full-resolution photo preview.
- 40 unit/integration tests passed under Linux/Xvfb; two external Canon/RAW
  fixture tests skipped. Adobe application import and newly converted XMP→PF3
  native rendering must be checked on a Windows PC with licensed software.

## v0.5 (2026-10-28)

- Fix DPP ignoring LUT-only exports: fit into editable RGB polynomial/curves.
- Keep camera grids identity to avoid applying the look twice.
- Add actual generated-PF3 Canon RAW preview in an isolated native worker.
- Distinguish native PF3 results from high-resolution target LUT references.
- Report held-out model error and actual native-image target error.
- Verify every generated property on readback; serialize DLL sessions safely.
- Pass 28 tests including real Canon RAW/PF3 rendering and GUI mode changes.
- Reported fixture: native-image RGB MAE 3.78/255; camera hardware untested.


## v0.4 (2026-10-28)

- Add rawpy/LibRaw full-resolution RAW input and grouped photo/RAW file filters.
- Develop RAW with camera WB, 8-bit sRGB and automatic brightness disabled.
- Decode photos on a background worker; preserve the previous photo on errors.
- Include rawpy native libraries in EXE build commands.
- Cancel GUI timers during shutdown to prevent stale Tk callback errors.
- Pass 20 tests, including an actual Canon 40D sRAW CR2 decode.


## v0.3 (2026-10-28)

- Retain original photo resolution and apply EXIF orientation.
- Add synchronized resizable dual canvases, Fit/100%, zoom and pan.
- Add resolution/zoom display, Lanczos rendering and live strength updates.
- Add background visible-region rendering, debounce, latest-result checks and 64 MiB LRU.
- Add Windows DPI awareness and five preview tests including Tk integration.
- Preserve PF3 export implementation; Canon DLL/camera validation remains outstanding.

## v0.2 (2026-10-28)

- Added direct Canon PF3 generation using locally installed PSE `EdsCFParse.dll`.
- Added Windows native DLL discovery and manual override.
- Converted .cube into dual 33³/12-bit LUT tables, with strength blending.
- Added neutral post-LUT curves/matrices to avoid zero-map black output.
- Added PF3 PSP header and native table readback verification.
- Added base style selection and command-line batch conversion.
- Added Windows packaging workflow and unit tests.
- Real Windows, PSE-import and EOS-camera validation **not yet performed**.

## v0.1

- LUT inspect/preview and CUBE resampling.
- No direct PF3 generation (superseded by v0.2).
