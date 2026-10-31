"""Windows/macOS Canon PF3 file writer using the *user-installed* Picture Style Editor runtime.

This project does not redistribute Canon binaries.  The Canon library is invoked
locally as a serializer, not via GUI automation.  Compatibility of camera output
is separate from a successful parser/serializer round trip.

MIT License.  Implementation is independent of third-party application code.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
import hashlib
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading

import numpy as np
from lut import Cube, apply_cube
from canon_fit import fit_cube, target_rgb

_NATIVE_LOCK = threading.RLock()

GRID = 33
TABLE_ID_A = 0x40001070
TABLE_ID_B = 0x40001071
TABLE_BYTES = 6 + GRID ** 3 * 6
# Property schema used by Canon's locally installed PF3 serializer.
# Build synthetic, conservative data instead of redistributing Canon-owned files.
SIZES = (
    (0x00000114, 4), (0x00000115, 32),
    (0x40001002, 32), (0x4000100A, 64),
    (0x40001021, 240), (0x40001029, 240),
    (0x40001019, 300), (0x40001018, 300), (0x40001065, 300),
    (0x40001061, 512), (0x40001062, 512),
    (0x40001023, 8), (0x4000102B, 8),
    (0x40001008, 456), (0x40001012, 4),
    (TABLE_ID_A, TABLE_BYTES), (TABLE_ID_B, TABLE_BYTES),
    (0x4000100D, 3), (0x4000100C, 2),
    (0x40001011, 4), (0x40001080, 4),
)
STYLE_IDS = {
    'Standard': 0x81,
    'Portrait': 0x82,
    'Landscape': 0x83,
    'Neutral': 0x84,
    'Faithful': 0x85,
    'Fine Detail': 0x88,
}
MAGIC = bytes.fromhex('0000300050535000')


MAC_PSE_APP = Path('/Applications/Canon Utilities/Picture Style Editor/PictureStyleEditor.app')
MAC_LIBRARY = Path('Contents/PlugIns/EdsCFParse.bundle/Contents/MacOS/EdsCFParse')


def _library_names() -> tuple[str, ...]:
    return ('edscfparse',) if sys.platform == 'darwin' else ('edscfparse.dll',)


def _mac_library_in(p: Path) -> Path | None:
    """Accept PictureStyleEditor.app, its folder, the .bundle, or the binary."""
    for test in (p / MAC_LIBRARY, p / 'PictureStyleEditor.app' / MAC_LIBRARY,
                 p / 'Contents/MacOS/EdsCFParse'):
        if test.is_file():
            return test.resolve()
    return None


def find_canon_library(path: str | Path | None = None) -> Path:
    """Locate user's existing EdsCFParse library; never download or bundle it."""
    if path:
        p = Path(path).expanduser()
        if p.is_file() and p.name.lower() in _library_names():
            return p.resolve()
        if p.is_dir():
            if sys.platform == 'darwin':
                found_mac = _mac_library_in(p)
                if found_mac:
                    return found_mac
            direct = [p / 'EdsCFParse.dll', p / 'DPP4Lib' / 'EdsCFParse.dll']
            for test in direct:
                if test.is_file():
                    return test.resolve()
            found = list(p.glob('**/EdsCFParse.dll'))
            if found:
                return found[0].resolve()
        raise FileNotFoundError(f'Canon EdsCFParse not found at {p}')
    if sys.platform == 'darwin':
        for app in (MAC_PSE_APP, Path.home() / MAC_PSE_APP.relative_to('/')):
            found_mac = _mac_library_in(app)
            if found_mac:
                return found_mac
        raise FileNotFoundError(
            'EdsCFParse not found. Install Canon Picture Style Editor for macOS, '
            'or select PictureStyleEditor.app in the application.'
        )
    candidates: list[Path] = []
    for key in ('ProgramW6432', 'ProgramFiles', 'ProgramFiles(x86)'):
        root = os.environ.get(key)
        if root:
            for prefix in ('Canon', 'Canon Inc'):
                base = Path(root) / prefix
                if base.is_dir():
                    candidates.append(base)
    for base in candidates:
        found = list(base.glob('**/EdsCFParse.dll'))
        if found:
            # Prefer 64-bit PSE if both variants are available.
            return found[0].resolve()
    raise FileNotFoundError(
        'EdsCFParse.dll not found. Install Canon Picture Style Editor, '
        'or select its DPP4Lib folder in the application.'
    )


def make_canon_grid(cube: Cube, strength: float = 1.0) -> bytes:
    """Resample CUBE to a B-fast 33^3, unsigned 12-bit camera grid.

    A camera cannot represent out-of-gamut output; clip, with strength
    blending performed in the source LUT's working RGB space.
    """
    if not 0 <= strength <= 1:
        raise ValueError('Strength must be between 0 and 1')
    axis = np.linspace(0, 1, GRID, dtype=np.float32)
    # Coordinate order is R outermost / B innermost for Canon table.
    coords = np.stack(np.meshgrid(axis, axis, axis, indexing='ij'), axis=-1).reshape(-1, 3)
    dst = target_rgb(cube, coords, strength)
    samples = np.rint(dst * 4095).astype('<u2', copy=False)
    blob = struct.pack('<HHH', 12, 3, GRID) + samples.tobytes(order='C')
    assert len(blob) == TABLE_BYTES
    return blob


def _neutral_matrix() -> bytes:
    # 3x3 coefficients embedded in a 60x32-bit fixed-point block.
    coeffs = [0] * 60
    for index in (0, 21, 42):
        coeffs[index] = 65536
    return struct.pack('<60i', *coeffs)


def _neutral_curve() -> bytes:
    knots = [2, 0, 0, 255, 255] + [0] * 20
    return struct.pack('<25I', *knots)


def make_properties(cube: Cube, name: str, base: str = 'Neutral', strength: float = 1.0, *, fitted=None) -> dict[int, bytes]:
    if base not in STYLE_IDS:
        raise ValueError(f'Unknown base style {base}')
    # Camera names are in an ASCII legacy field.  Do not split multi-byte data.
    safe_name = name.encode('ascii', errors='replace')[:31]
    properties = {key: bytes(size) for key, size in SIZES}
    properties[0x114] = struct.pack('<I', STYLE_IDS[base])
    properties[0x40001002] = safe_name.ljust(32, b'\x00')
    properties[0x4000100D] = b'UD '
    properties[0x4000100C] = b'\x01\x00'
    for key in (0x40001021, 0x40001029):
        properties[key] = _neutral_matrix()
    for key in (0x40001019, 0x40001018, 0x40001065):
        properties[key] = _neutral_curve() * 3
    for key in (0x40001061, 0x40001062):
        properties[key] = struct.pack('<II', 2, 0) + bytes(504)
    for key in (0x40001023, 0x4000102B):
        properties[key] = struct.pack('<II', 1, 0)
    fitted = fitted if fitted is not None else fit_cube(cube, strength)
    for key in (0x40001021, 0x40001029):
        properties[key] = fitted.matrix_bytes()
    properties[0x40001065] = fitted.curve_bytes()
    # The editable transform is now authoritative. Identity camera tables avoid
    # applying the requested LUT twice on paths that also consume the matrices.
    axis = np.array([0,1],dtype=np.float32)
    identity = Cube(np.stack(np.meshgrid(axis,axis,axis,indexing='ij'),-1),np.zeros(3),np.ones(3))
    grid = make_canon_grid(identity)
    properties[TABLE_ID_A] = grid
    properties[TABLE_ID_B] = grid
    for key, size in SIZES:
        if len(properties[key]) != size:
            raise AssertionError(f'Incorrect internal property size: {key:08X}')
    return properties


class NativeSerializer:
    """Minimal typed FFI to an optional, user-installed Canon binary."""
    def __init__(self, dll: str | Path):
        if sys.platform not in ('win32', 'darwin'):
            raise OSError('Canon native PF3 export requires Windows or macOS and Canon PSE.')
        self.path = Path(dll).resolve()
        self._dir = os.add_dll_directory(str(self.path.parent)) if hasattr(os, 'add_dll_directory') else None
        try:
            # The macOS PSE ships the same C API inside a universal Mach-O bundle.
            loader = ctypes.WinDLL if sys.platform == 'win32' else ctypes.CDLL
            self.lib = loader(str(self.path))
        except Exception:
            if self._dir:
                self._dir.close()
            raise
        pvoid = ctypes.c_void_p
        p32 = ctypes.POINTER(ctypes.c_uint32)
        u32 = ctypes.c_uint32
        signatures = {
            'EdsCfpInitialize': ([], u32),
            'EdsCfpTerminate': ([], u32),
            'EdsCfpCreateRef': ([ctypes.c_char_p, u32, u32, ctypes.POINTER(pvoid)], u32),
            'EdsCfpRelease': ([pvoid], u32),
            'EdsCfpSetPropertyData': ([pvoid, u32, u32, u32, pvoid], u32),
            'EdsCfpGetPropertySize': ([pvoid, u32, u32, p32, p32], u32),
            'EdsCfpGetPropertyData': ([pvoid, u32, u32, u32, pvoid], u32),
            'EdsCfpReflectProperty': ([pvoid], u32),
        }
        for api_name, (params, ret) in signatures.items():
            symbol = getattr(self.lib, api_name)
            symbol.argtypes, symbol.restype = params, ret

    @staticmethod
    def _check(code: int, operation: str) -> None:
        if code:
            raise RuntimeError(f'Canon {operation}: error 0x{code:08X}')

    @contextmanager
    def document(self, path: Path, new: bool):
        # EdsCFParse has process-global initialization state.
        with _NATIVE_LOCK:
            with self._document(path,new) as reference:
                yield reference

    @contextmanager
    def _document(self, path: Path, new: bool):
        ref = ctypes.c_void_p()
        initialized = False
        try:
            self._check(self.lib.EdsCfpInitialize(), 'initialize')
            initialized = True
            path_bytes = str(path).encode('mbcs' if sys.platform == 'win32' else 'utf-8', errors='strict')
            # New file: create/write. Existing file: open/read.
            self._check(
                self.lib.EdsCfpCreateRef(path_bytes, 1 if new else 2, 1 if new else 0, ctypes.byref(ref)),
                'create reference',
            )
            if not ref.value:
                raise RuntimeError('Canon returned an empty file reference')
            yield ref
        finally:
            if ref.value:
                self._check(self.lib.EdsCfpRelease(ref), 'release')
            if initialized:
                self._check(self.lib.EdsCfpTerminate(), 'terminate')

    def write(self, path: Path, properties: dict[int, bytes]) -> None:
        with self.document(path, new=True) as ref:
            for prop, _ in SIZES:
                raw = properties[prop]
                buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
                self._check(self.lib.EdsCfpSetPropertyData(ref, prop, 0, len(raw), buffer), f'write 0x{prop:08X}')
            self._check(self.lib.EdsCfpReflectProperty(ref), 'serialize PF3')

    def read_prop(self, ref, prop: int) -> bytes:
        size = ctypes.c_uint32()
        typ = ctypes.c_uint32()
        self._check(self.lib.EdsCfpGetPropertySize(ref, prop, 0, ctypes.byref(typ), ctypes.byref(size)),
                    f'read property size 0x{prop:08X}')
        if size.value > 1024 * 1024:
            raise ValueError('Unexpectedly large Canon PF3 property')
        result = (ctypes.c_ubyte * size.value)()
        self._check(self.lib.EdsCfpGetPropertyData(ref, prop, 0, size.value, result),
                    f'read property 0x{prop:08X}')
        return bytes(result)

    def verify(self, path: Path, properties: dict[int, bytes]):
        with self.document(path, new=False) as ref:
            for prop in properties:
                if self.read_prop(ref, prop) != properties[prop]:
                    raise ValueError(f'Canon PF3 round-trip LUT mismatch: 0x{prop:08X}')


def validate_envelope(path: Path):
    data = path.read_bytes()
    if len(data) < 32 or data[:8] != MAGIC:
        raise ValueError('Output does not have the Canon PF3/PSP header')
    claimed = int.from_bytes(data[8:12], 'big')
    if claimed != len(data) - 12:
        raise ValueError('Canon PF3 header length mismatch')
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def export_pf3(cube: Cube, dest: str | Path, *, name: str,
               dll: str | Path | None = None, base: str = 'Neutral',
               strength: float = 1.0) -> dict:
    """Generate an approximate editable PF3 via the locally installed Canon serializer.

    Output is atomically replaced only after a header and full-property round-trip.
    A successful result means readable native properties, not an image/camera test.
    """
    library_path = find_canon_library(dll)
    destination = Path(dest).expanduser().resolve()
    if destination.suffix.lower() != '.pf3':
        raise ValueError('Output path must end in .pf3')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fitted = fit_cube(cube, strength)
    values = make_properties(cube, name, base, strength, fitted=fitted)
    serializer = NativeSerializer(library_path)
    # The Canon library receives an ASCII-only temporary path to avoid encoding
    # issues on non-English Windows.  Move to the requested Unicode name last.
    with tempfile.TemporaryDirectory(prefix='CLBPf3_') as scratch:
        working = Path(scratch) / 'style.pf3'
        serializer.write(working, values)
        info = validate_envelope(working)
        serializer.verify(working, values)
        # Only replace output once Canon's own readback succeeded.
        temp_out = destination.with_suffix(destination.suffix + '.partial')
        try:
            temp_out.write_bytes(working.read_bytes())
            os.replace(temp_out, destination)
        finally:
            temp_out.unlink(missing_ok=True)
    return {'file': str(destination), 'bytes': info['bytes'], 'sha256': info['sha256'],
            'base': base, 'strength': strength, 'engine': str(library_path),
            'native_roundtrip': True, 'camera_tested': False, 'fit': fitted.report}
