"""Full-resolution raster/RAW decoding, independent of Tk and Canon PF3 DLLs."""
from pathlib import Path
from PIL import Image, ImageOps

RAW_EXTENSIONS = ('.cr2', '.cr3', '.crw', '.dng', '.nef', '.nrw', '.arw',
                  '.srf', '.sr2', '.raf', '.orf', '.rw2', '.raw', '.pef',
                  '.ptx', '.srw', '.rwl', '.3fr', '.fff', '.iiq', '.kdc',
                  '.dcr', '.mos', '.erf', '.mef', '.mrw')
RASTER_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.webp')

def patterns(extensions):
    return ' '.join('*' + ext for ext in extensions)

PHOTO_FILETYPES = [
    ('사진 및 RAW', patterns(RASTER_EXTENSIONS + RAW_EXTENSIONS)),
    ('Canon RAW', patterns(('.cr2', '.cr3', '.crw'))),
    ('카메라 RAW', patterns(RAW_EXTENSIONS)),
    ('일반 사진', patterns(RASTER_EXTENSIONS)),
    ('모든 파일', '*.*'),
]

def load_photo(filename):
    """Return independent full-resolution 8-bit RGB pixels and a display note.

    RAW uses the sensor data, not an embedded JPEG thumbnail. LibRaw handles
    orientation and active sensor crop. RAW support depends on camera/encoding.
    """
    path = Path(filename)
    if path.suffix.lower() not in RAW_EXTENSIONS:
        with Image.open(path) as raw:
            photo = ImageOps.exif_transpose(raw).convert('RGB')
        return photo, f'{path.name} | RGB'
    try:
        import rawpy
    except (ImportError, OSError) as error:
        raise RuntimeError('RAW를 열려면 rawpy가 필요합니다. launch_windows.bat을 다시 실행하거나 '
                           'python -m pip install -r requirements.txt로 설치하세요. '
                           '64비트 Python을 사용해 주세요.') from error
    try:
        # A binary stream supports Unicode Windows paths without relying on
        # LibRaw's narrow-character filename handling.
        with path.open('rb') as stream:
            with rawpy.imread(stream) as raw:
                rgb = raw.postprocess(use_camera_wb=True, use_auto_wb=False,
                                      output_color=rawpy.ColorSpace.sRGB,
                                      output_bps=8, half_size=False,
                                      no_auto_bright=True, gamma=(2.4, 12.92))
        photo = Image.fromarray(rgb, 'RGB')
        return photo, f'{path.name} | RAW 현상 → sRGB · 카메라 WB · 자동 밝기 꺼짐'
    except Exception as error:
        raise RuntimeError(f'RAW를 현상하지 못했습니다: {path.name}\n'
                           '해당 카메라/압축 방식의 LibRaw 지원 여부와 파일 손상을 확인하세요.\n'
                           f'{type(error).__name__}: {error}') from error
