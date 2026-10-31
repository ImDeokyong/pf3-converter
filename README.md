# PF3 Converter v1.1

**제작자 : ImDeokyong** · 오픈소스 (MIT 라이선스)

**Interface languages:** 한국어 (Korean, default) · English · 日本語 (Japanese) · 简体中文 (Simplified Chinese). The language selector is in the upper-right corner of the application. Changes take effect without restarting, and the selection is stored locally. See `WINDOWS_GUIDE_KO.txt`, `WINDOWS_GUIDE_EN.txt`, `WINDOWS_GUIDE_JA.txt`, and `WINDOWS_GUIDE_ZH_CN.txt` for a quick start in each language.

Windows GUI and CLI for opening **3D CUBE LUTs and Adobe XMP looks**, inspecting
full-resolution photos/RAW, exporting an **approximate Canon Picture Style (.pf3)**,
creating a **Lightroom/Camera Raw creative XMP profile from a CUBE**, and exporting
**standard / LUMIX-ready CUBE LUTs from XMP or CUBE** (MIT).

## macOS support

PF3 export also works on macOS with the macOS build of Canon Picture Style
Editor installed. The macOS PSE ships the same `EdsCFParse` C API inside
`PictureStyleEditor.app/Contents/PlugIns/EdsCFParse.bundle` (universal x86_64/arm64),
which is loaded with `ctypes.CDLL` instead of `WinDLL`. Nothing from Canon is bundled.

- Start: double-click `launch_mac.command` (needs Python 3.10+ with Tk, e.g. python.org).
- CLI: `.venv/bin/python cli.py look.cube -o look.pf3 --strength 0.5`
- "LUT reference" preview works everywhere. The "Canon native" RAW preview uses
  `DppCore.bundle` and is experimental on macOS.
- See `MAC_GUIDE_KO.txt` for a Korean quick start.

## v1.1 — Consistent sRGB CUBE output (2026-10-30)

**Output destinations are explicit:** Standard CUBE → Photoshop (document in **sRGB**),
LUMIX CUBE → supported Panasonic REAL TIME LUT cameras, XMP → Adobe Lightroom,
PF3 → Canon (the PF3 engine and fitting code remain unchanged).

**Two CUBE buttons use one and the same LUT sampler.** For the same 0–100%
strength, both export a 33³, full-range `[0,1]` RGB table in CUBE R-fast order
with the same clamp policy and nine-digit rounding. At 100% the RGB rows are
**byte-identical**, including for XMP inputs. The LUMIX version differs **only
by its `#LUMIXPHOTOSTYLE` header**. The header changes how a physical LUMIX
selects its *base Photo Style*; it does not numerically change the LUT RGB rows.
The Photoshop CUBE now also bakes the current strength slider (previously it
always exported at 100%). The GUI continues to begin at a provisional 50%.

### Why XMP develop preset → sRGB CUBE cannot be exactly reverse-engineered

A `.xmp` *develop preset* describes Lightroom process-engine operations, not a
complete 3D LUT. `classic negative_by.BB.xmp`, for example, contains exposure,
highlights/shadows, parametric + point tone curves, many HSL adjustments, and a
*reference to* Adobe Color. That base camera profile is **not embedded**. A
standalone sRGB LUT cannot reproduce per-image RAW processing, Adobe Color base
rendering, camera white balance, highlight recovery, or masks. The existing
approximation engine is retained for compatibility, and **has not been verified
against Lightroom**. Changing the nominal output to sRGB does not solve those
fundamental differences.

**LUMIX:** Choose the Photo Style based on the rendering used to create the look.
`STD` does *not* mathematically transform sRGB to the camera's Standard output.
For Panasonic camera fidelity, build the LUT from a TIFF/JPEG captured with the
chosen base Photo Style and test on the actual camera.

**Canon:** `pf3_native.py`, `canon_fit.py`, and the PF3 export engine have not
been modified. Existing dependency policy and the Python 3.15/rawpy limitation
are also unchanged.

## v1.1 — XMP → CUBE and Panasonic LUMIX Real Time LUT (2026-10-30)

**Source ZIP only; no EXE bundled.** The Python dependencies and Canon PSE
requirements have not changed from v1.0.

### Two CUBE export options

- **Save standard CUBE (incl. XMP):** opens either a 3D CUBE or Adobe XMP
  (creative RGBTable profile or supported develop preset) and exports an
  **33³** standard `.cube`. **The current strength setting also applies**,
  just like the LUMIX CUBE.
- **Export LUMIX CUBE (33³):** opens CUBE **or XMP**, resamples to a 33-point
  full-range CUBE, includes the documented `#LUMIXPHOTOSTYLE` base-style tag,
  and uses the current 0–100% strength slider. Default tag `STD`
  (Standard), with a dropdown to select other documented Panasonic tags.
  The default strength is still a *provisional 50%*, unless RAW analysis was used.

Example output header:

```cube
TITLE "PF3 Converter LUT"
#LUMIXPHOTOSTYLE STD
LUT_3D_SIZE 33
```

LUT entries are output in R-fastest `.cube` order, with 9-digit ASCII decimal
values clipped to the `[0,1]` range. Validity is checked before atomic save.
The exporter reports the fraction of RGB components clipped by its own
output-range restriction. Export does not require the Canon DLL or `rawpy`;
RAW auto strength still requires `rawpy`.

### Important limitations of XMP → LUMIX

- **Creative XMP Color Profile:** the embedded Adobe RGBTable is decoded and
  normalized to display-referred sRGB by the existing importer. External
  Adobe camera profiles, look stages or base renders are **not** reproduced.
- **Lightroom/Camera Raw develop XMP:** exposure, tone, HSL and color grading
  are **display-RGB approximations**, not Adobe's actual RAW engine. Masks,
  texture, clarity, grain, dehaze, local adjustments, lens corrections, white
  balance and referenced camera profiles are **not transferable**. The GUI
  displays approximation notices when appropriate.
- **Camera color management is NOT automatic.** A LUT designed around Adobe's
  sRGB-rendered preview does not automatically become identical when applied
  over Panasonic's Standard, Natural, Portrait or V-Log rendering. Selecting
  `#LUMIXPHOTOSTYLE STD` merely tags the expected camera base style; it does
  **not** convert Log/video transforms to Standard. Check exposure, white
  balance, contrast and base Photo Style against actual LUMIX JPEGs.
- **Technical/Hybrid LUT classifier:** structural classification remains a
  *heuristic*; it never guarantees that a lookup table targets LUMIX Standard.
  An improperly matched Log LUT cannot be repaired by reducing opacity.
- **Source resampling:** 32³ XMP tables and larger source CUBE tables are
  sampled to 33³, potentially introducing interpolation errors. RGB values
  outside `[0,1]` are clipped and reported rather than preserved.
- **Real camera support unverified:** camera model, firmware, photo style tags,
  card format and LUT transfer method vary. On supported models, Panasonic
  documents 2–33-point `.cube` LUTs, full-range recommendation, and the
  `#LUMIXPHOTOSTYLE` tag. For SD import, Panasonic recommends placing CUBE
  files in the card root and ASCII-safe filenames (FAT32: 8 characters).
  Refer to your camera manual for exact requirements.

### GUI usage

1. Load a `.cube` or `.xmp` file. An XMP can be a creative RGBTable profile or
   an eligible develop preset. Unsupported files show an error rather than
   silently generating an identity LUT.
2. Optionally preview a photo/RAW. Set strength manually or use **Auto strength
   · 1–5 RAW** for an appropriate Creative look.
3. Choose the **LUMIX base Photo Style**. Default: `STD`. It must match the
   intended LUMIX rendering conditions. Do not assume that a camera's V-Log
   signal is sRGB.
4. Click **Export LUMIX CUBE (33³)**. The selected strength is included in the exported LUT.
5. Load the resulting CUBE via the LUMIX LUT Library on a supported camera.
   Take test JPEGs and compare with the intended appearance.

For a normal XMP → CUBE conversion without Panasonic tags,
use **Save standard CUBE (incl. XMP)** instead.

### Command-line examples

```bat
py -3 cli.py portrait.xmp -o portrait.cube
py -3 cli.py portrait.xmp -o portrait_LUMIX.cube --lumix-style STD --strength 0.50
py -3 cli.py creative.cube -o look_LUMIX.cube --lumix-style NAT --strength 0.75
```

No additional runtime dependencies are required. For each export option,
only `.cube` output uses the new LUMIX path; `--lumix-style` cannot be used
with `.xmp` or `.pf3` output. The user-selected source file is never
silently overwritten through the GUI or CLI.

Official Panasonic documentation:
- S9 LUT Library: https://eww.pavc.panasonic.co.jp/dscoi/DC-S9/html/DC-S9_DVQP3138_eng/0074.html
- S5II LUT Library: https://eww.pavc.panasonic.co.jp/dscoi/DC-S5M2/html/DC-S5M2_DVQP2839_eng/0180.html
- Panasonic workflow guidance: https://www.panasonic.com/uk/consumer/cameras-camcorders/lumix-expert-advice-learn/lumix-expert-advice/using-real-time-luts.html

## v1.0 — PF3 Converter by ImDeokyong

### Four-language GUI edition (2026-10-28)

The interface now ships with an offline translation catalog (`i18n.py`) for Korean,
English, Japanese, and Simplified Chinese. The language selector changes menus,
actions, preview labels, import/export dialogs, status text and known XMP warnings
immediately without affecting image data or triggering Canon re-renders. Preferences
are stored under `%APPDATA%\PF3Converter\settings.json` on Windows, or
`~/.config/picture-bridge/settings.json` elsewhere. Optional environment variable
`PICTURE_BRIDGE_CONFIG_DIR` overrides the settings folder (useful for testing).
No translation service, API key, internet access or additional Python packages
are required. The Canon base-style identifiers and file extensions remain in
English because they are native technical values. Internal conversion diagnostics
from third-party libraries may still appear in their original language.

This is an update of **v1.0**, retaining the requested program version and the
same Windows executable identity; the localization does not change file formats.


Version 1.0 updates the application name and credits, the Windows EXE name and
version metadata, and the default Adobe profile group. Converters, preview and
Canon-native export are otherwise retained from v0.6. Run `build_windows.bat` on
Windows to build `dist\PF3Converter.exe` with version and creator metadata.
The source ZIP does not contain a prebuilt EXE.

## RAW-based automatic strength recommendation (Mode B)

**New in the v1.0 source revision:** the GUI now offers **Auto strength · 1–5 RAW**
under the PF3 strength slider. This is a *conservative heuristic*, not an AI
model, artistic grading objective, or a promise that a converted PF3 will match
Canon DPP exactly.

1. Open a `.cube` (or compatible `.xmp`) profile.
2. Click **Auto strength · 1–5 RAW** and choose **one to five camera RAW files**.
   For a style intended for general use, select scenes with varied lighting,
   skin/landscape subject matter, and contrast.
3. Wait for the background analysis to decode each RAW with `rawpy` using camera
   white balance and sRGB output (without automatic brightness adjustment).
4. The tool tests 100%, 95%, …, 5% strength and chooses the **strongest blend
   satisfying conservative thresholds on *all* selected photos**. It inspects
   95th-percentile display-luma and RGB changes, chroma increases, and new
   highlight clipping/shadow crushing. This is a safety/tonality guide, not a
   perceptual color-quality assessment.
5. The result automatically updates the **strength slider**, reference LUT
   preview, and **PF3 export strength**. To inspect an individual RAW, open it
   separately with **Preview photo / RAW**. You can still move the slider.
6. If even 5% exceeds the limits, the tool reports that 5% is a **fallback,
   not a verified-safe value**. Check actual Canon DPP rendering before use.

Initial GUI strength is **50% (provisional)** instead of 100%; this is *not* an
analyzed recommendation until RAW analysis completes. The analyzer is RAW-only:
JPEG/PNG do not qualify as RAW references. It does not need any new third-party
packages beyond the existing NumPy, Pillow and `rawpy` dependencies. On Python
versions lacking compatible rawpy wheels (e.g., the previously reported
Python 3.15 environment), RAW analysis remains unavailable until rawpy is
installed successfully; this update **does not resolve rawpy installation**.

**Important for video LUTs:** The conversion pipeline still treats the LUT as
**display-referred sRGB → sRGB** unless the input was correctly color-managed.
The new classifier can estimate the *kind* of transform from RGB table patterns,
but **cannot identify exact Log/gamut encodings or perform color-space conversion**.
A technical LUT (e.g. S-Log3 → Rec.709) still requires correct color management;
reducing the strength cannot fix a mismatched input color space.

## Content-based CUBE LUT type estimate (v1.0 revision)

Opening a `.cube` now **analyzes its actual 3D RGB lookup table** to estimate
**Creative / likely Technical / likely Hybrid / Uncertain**. The classifier **does
not look at filenames, TITLE text, comments, or third-party metadata**. It samples
the neutral ramp to measure the shape of the transfer function, compressed input
ranges, clipped black/white plateaus, and RGB channel tinting. It additionally
checks whether a neutral-preserving, chromatic transform resembles a color/gamut
matrix. Ambiguous content is marked **Uncertain**, rather than falsely claiming
knowledge of a source or target color space.

- The estimate and its qualitative confidence appear inline under the strength
  slider, in all four supported UI languages. No Technical LUT warning dialog is
  shown and **PF3/XMP export is never blocked** by this classification.
- **Creative** CUBEs keep the existing **RAW 1–5 photo automatic strength** tool.
  If Technical/Hybrid is inferred, the RAW optimizer button is inactive, because
  attenuating a log/gamut transform is not a valid input-space conversion.
  **Uncertain** CUBEs retain opt-in RAW optimization, but users should verify
  suitability. XMP inputs retain their prior RAW optimization behavior.
- The `Override` selector allows the user to explicitly choose Creative,
  Technical or Hybrid if the estimate is wrong. For example, choose Creative to
  enable the original RAW optimizer for a misclassified artistic LUT. This
  only changes eligibility for RAW auto strength; it **does not** change
  transform data, manually selected intensity, or the PF3 export algorithm.
- A 3D RGB table *cannot unambiguously reveal* a LUT's intended input gamut,
  transfer function or creative purpose. A technical gamut matrix can be
  indistinguishable from a creative saturation matrix; a strong film curve can
  resemble a log conversion. The classifier is a **heuristic**, not a standard
  color-space identification tool. It does **not** perform log or gamut conversion
  or attempt to separate hybrid looks into underlying technical + creative LUTs.

## XMP support (introduced in v0.6)

| Input | Output | Operation | Requirements |
| --- | --- | --- | --- |
| `.cube` | `.pf3` | Existing Canon editable-color fit | Windows + installed Canon PSE |
| `.xmp` creative profile | `.pf3` | Decode embedded Adobe RGBTable, then Canon fit | Windows + installed Canon PSE |
| `.xmp` develop preset | `.pf3` | Sample supported slider adjustments into an approximate 33³ LUT, then Canon fit | Windows + installed Canon PSE |
| `.cube` | `.xmp` | Generate Adobe **creative profile** with a real 32³ RGB color table | Any supported Python platform; no Canon DLL |

An Adobe XMP *creative profile* is not the same as an XMP *develop preset* or
an XMP *photo sidecar*. Creative profiles can contain a real 3D LUT (`crs:RGBTable`
/ `crs:Table_<hash>`); this table is decoded without fitting it to sliders.
Profiles with alternate declared primary colors and transfer functions are
converted into a display-sRGB table for the Canon approximation, with gamut
clipping where necessary. A develop preset instead stores Adobe processing
parameters; we cannot run Adobe's proprietary development engine, so slider
conversions are **heuristic and not colorimetrically identical**.

Approximate preset adjustments currently include Exposure, Contrast, Highlights,
Shadows, Whites, Blacks, Saturation, Vibrance, global/per-channel PV2012 point
curves (linear interpolation), eight-band Hue/Saturation/Luminance, parametric
Shadows/Darks/Lights/Highlights, and Shadow/Midtone/Highlight/Global Color Grading
and legacy split-toning hue/saturation. These are sampled in display sRGB, not
RAW working-space Adobe rendering. **Unsupported** include temperature/tint
(raw-dependent white balance), adaptive masks, Auto Tone, clarity, texture, dehaze,
noise reduction, sharpening, camera calibration, lens corrections, grain,
vignetting, external creative-look references, and other photo-specific features.
The importer warns about omitted settings. If an XMP has no supported non-neutral
adjustments or embedded RGB LUT it refuses conversion rather than writing an
unexpectedly neutral file. Extra settings in an RGB-table profile are not applied.

For `.cube → .xmp` the output is a **creative profile carrying a 3D LUT**, not a
set of editable Lightroom Develop sliders. Adobe's profile RGB-table grids have
a 32-node-per-axis limit: 33³ and 65³ CUBEs are resampled. The converter assumes
the source CUBE maps display **sRGB → sRGB**, unless the author has explicitly
built a suitably color-managed LUT. CUBE names do not specify Log or gamut.
The generated XMP has an Amount slider when imported as a profile (subject to
Adobe version behavior). Import via Lightroom Classic's **File → Import Develop
Profiles and Presets** or Camera Raw's **Import Profiles and Presets**. Look for
the profile group **PF3 Converter**. Profile XML/binary round-trip is tested,
but actual Lightroom import has not been verified in this environment.

### v1.0 steps

1. Extract the ZIP and launch `launch_windows.bat` (Python dependencies required).
2. Click **1. .cube / .xmp 불러오기**, choose the source and read any conversion warnings.
3. Optionally select 1–5 RAW files with **Auto strength · 1–5 RAW** to recommend a conservative strength (provisional default: 50%), then open a photo/RAW to compare the full-resolution target look.
4. For a Canon `.pf3`, set base style, strength and PSE DLL, then click **3. 실제 .pf3 파일 생성**.
5. For an Adobe `.xmp` from a `.cube`, click **4. .cube → Lightroom .xmp 생성**. This
   option is disabled when the input is an XMP.
6. Verify final color in Canon DPP (PF3) or Adobe Lightroom/Camera Raw (XMP).

### v1.0 CLI examples

`python cli.py --version` prints the app name, version and author.

```powershell
python cli.py look.cube -o look.pf3 --base Neutral --strength 1.0
python cli.py LightroomPreset.xmp -o CanonLook.pf3 --base Portrait
python cli.py look.cube -o LightroomLook.xmp --name "My Look" --xmp-group "My Profiles"
```

The `.cube → .xmp` path runs on macOS/Linux too, without Canon software.
PF3 output still requires the installed **Windows** Canon DLL. JSON output
reports held-out Canon fit metrics for PF3 and a round-trip/resampling metric
for XMP; neither substitutes for a test in the target Adobe/Canon application.

## What changed in v0.5 (retained)


## What changed in v0.5

The old exporter wrote the requested look into the two 33³ camera tables while
leaving editable colour matrices/curves neutral. In the reported DPP workflow,
those tables did not produce the displayed LUT look. A constant-magenta table
probe was also ignored by DPP. A byte-perfect serializer round trip was therefore
insufficient evidence of correct colour rendering.

v0.5 fits the look into the editable cubic RGB coefficients and post curves that
Canon's developer consumes. Both camera tables are identity so the look is not
also applied there. **This is an approximation, not lossless CUBE-to-PF3.**
The fit uses a 17³ training grid plus extra neutral samples; an offset 18³ grid
measures model error independently. Arbitrary LUTs may fit poorly, especially
non-monotonic transforms, discontinuities, lifted black, and strong local hue
changes. The GUI/CLI report numerical RGB fit error; it is not perceptual Delta E.

## Start on Windows

1. Install 64-bit Python 3.10+ and Canon Picture Style Editor (PSE).
2. Extract this entire folder and run `launch_windows.bat`.
3. Load a CUBE and a photo/RAW. Set the base style and LUT strength.
4. For Canon CR2/CR3/CRW choose **캐논 PF3 실제 현상** (default).
5. Inspect the actual generated PF3 result. Export with **실제 .pf3 파일 생성**.
6. Open the new file in DPP and assess it under matching exposure/WB settings.

`EdsCFParse.dll` can be located automatically or selected manually. Canon binaries,
ICC profiles, input photos and LUTs are not bundled. The local PSE installation
supplies its own DPP4Lib and `icc/NS.ICC`; there is no download at conversion time.
RAW input additionally uses rawpy/LibRaw from `requirements.txt`.

## Two clearly labelled comparison modes

- **캐논 PF3 실제 현상**: generates the same fitted editable properties used by
  export, loads the generated PF3 into the installed Canon DPP4Lib, and renders
  the Canon RAW. The left pane is Canon base development; the right pane is the
  generated PF3 actually applied by Canon. WB is As Shot, exposure is 0, output
  is sRGB. No LUT is applied on top of the rendered right pane. The toolbar
  reports image error against the target LUT applied to the Canon baseline.
- **고해상도 LUT 목표 참고**: preserves the v0.4 full-resolution raster/LibRaw
  source and shows the target CUBE look. It is a target reference, not a claim
  about what a PF3 will reproduce. JPEG/PNG/TIFF and non-Canon RAW use this view.

The standalone Canon path has been validated at **1080×1620 portrait /
1620×1080 landscape**, for 3:2 Canon RAW images. It deliberately does not request
larger unvalidated portrait buffers. Smaller frame requests were observed to
crop, while larger portrait requests can silently corrupt Canon's output.
The source dimensions and comparison render dimensions are shown separately.
Use the high-resolution reference mode for source-pixel inspection.

Fit/100%, wheel/button zoom, synchronized drag-to-pan, Lanczos display resampling,
and the 64 MiB rendered-pair cache are retained. Native work runs in an isolated
child process; debounced UI requests coalesce and obsolete results are discarded.
Closing a window does not forcibly interrupt an already running native call;
it may finish before the process exits. A failed native render is labelled as
failed, without substituting a target LUT frame as a verified result.

## RAW / colour conditions

The file chooser includes CR2/CR3/CRW, DNG, NEF/NRW, ARW, RAF, ORF, RW2 and other
rawpy/LibRaw extensions. Actual support depends on camera and compression mode.
LibRaw target mode develops full-resolution sensor data with camera WB,
no auto brightness, and 8-bit sRGB. Native mode uses Canon development instead.
No automatic Log/gamut conversion is performed, and LUT filenames are not used for type estimation.
An N-Log/Rec.2020 LUT applied directly to sRGB is interpreted as that explicit
RGB mapping, not as a complete colour-managed N-Log workflow.

## Validation (2026-10-28)

The original 28 v0.5 tests passed on Windows, including real Canon DLL rendering, full editable
property readback, RAW decode, native comparison pixels, UI latest-request
handling/mode switching, fit error, identity/zero-strength, and high-resolution
preview interactions. Native tests used the user's `832A1631.CR3` and
`RED_FilmBiasOffset_Rec2020_N-Log_to_Rec709_BT1886.cube` without redistributing them.

For that test (Neutral / 100%):

- Held-out model RGB MAE: **4.73 / 255**.
- Actual Canon PF3 image versus target-on-Canon-baseline RGB MAE: **3.78 / 255**.
- Actual image 95th percentile channel difference: **11 / 255**.

These are results for one photograph/LUT/settings combination, not a guarantee
for other LUTs or files. They compare the target with the fitted result; the
right-hand native preview itself consists of the actual generated PF3 pixels.
Physical camera output and standalone EXE packaging were not tested.

Run `python -m unittest discover -s tests -v`. Optional native test variables:
`CLB_NATIVE_RAW`, `CLB_NATIVE_LUT`, `CLB_NATIVE_DLL`. `CANON_RAW_TEST_FILE` enables
a real rawpy decode test. Those tests skip when fixtures are absent; Tk tests
skip when no desktop display is available. The native colour-error threshold
in the integration test is a regression target for the reported fixture.

## CLI / build

`python cli.py input.cube -o output.pf3 --base Neutral --strength 1.0` (also accepts `.xmp` inputs; see above)

The JSON output includes approximation metrics and a parser round-trip flag.
It does not claim native image validation unless a separate render is performed.
`build_windows.bat` or the included GitHub workflow builds the EXE and collects
rawpy's native dependencies. Both source and EXE use the same isolated Canon worker.

## Implementation notes

`canon_fit.py` implements a 19-term cubic colour model with three 12-knot post
curves. Fixed-point coefficients and curve points are quantized before validation.
`pf3_native.py` serializes through the locally installed Canon DLL and reads back
**all generated properties**, not just the 3D tables. Native serializer sessions
are locked because Canon initialization is process-global.
`canon_render.py` performs read-only development in a separate process and uses
the loaded-file Picture Style selector (255), not the built-in base selector.
The first development frame is discarded to avoid initial colour instability.

API research reference: https://github.com/LvClFER/Lut-to-Canon-Picture-Style
Canon resources remain in the user's installation and are not redistributed.

## XMP technical and compatibility references

- Adobe official Photoshop Camera Raw XMP sidecar documentation:
  https://helpx.adobe.com/camera-raw/desktop/get-started/overview-and-setup/camera-raw-settings.html
- Adobe DNG SDK (RGB table serialization):
  https://www.adobe.com/support/downloads/dng/dng_sdk.html
- Open documentation of Adobe RGBTable encoding and color-space fields:
  https://github.com/mvimercati/xmp2cube
  https://github.com/MariuzM/learning-archive/tree/main/lut-to-lightroom-camera-profile

These links are interoperability references; the project ships its own Python
implementation. It does not redistribute Canon DLLs or Adobe assets.
