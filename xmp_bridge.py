"""Adobe Camera Raw/Lightroom XMP RGB-table profiles and limited develop presets.

XMP creative profiles use the DNG SDK 'big table' RGB-table codec.  The preset
sampler is *not* an Adobe process engine; all supported sliders are approximate.
No third-party code or Adobe binary is bundled.
"""
from __future__ import annotations

from app_info import APP_NAME, XMP_GROUP

from dataclasses import dataclass, field
import hashlib
import html
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET
import zlib

import numpy as np
from lut import Cube, apply_cube

CRS = 'http://ns.adobe.com/camera-raw-settings/1.0/'
RDF = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
ADOBE85 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-:+=^!/*?`'|()[]{}@%$#"
_DECODE = {c: i for i, c in enumerate(ADOBE85)}
PRIMARIES = ('sRGB', 'AdobeRGB', 'ProPhoto', 'DisplayP3', 'Rec2020')
GAMMAS = ('Linear', 'sRGB', '1.8', '2.2', 'Rec2020')
MAX_XMP_BYTES = 16 * 1024 * 1024
MAX_BINARY_BYTES = 8 * 1024 * 1024
COLOR_BANDS = ('Red','Orange','Yellow','Green','Aqua','Blue','Purple','Magenta')
CURVES = ('ToneCurvePV2012','ToneCurvePV2012Red','ToneCurvePV2012Green','ToneCurvePV2012Blue')
SLIDERS = ('Exposure2012', 'Contrast2012', 'Highlights2012', 'Shadows2012', 'Whites2012',
           'Blacks2012', 'Saturation', 'Vibrance')
HSL = tuple(f'{mode}Adjustment{band}' for mode in ('Hue','Saturation','Luminance') for band in COLOR_BANDS)
PARAMETRIC = ('ParametricShadows','ParametricDarks','ParametricLights','ParametricHighlights')
GRADING = tuple(f'ColorGrade{region}{setting}' for region in ('Shadow','Midtone','Highlight','Global')
                for setting in ('Hue','Sat','Lum')) + ('SplitToningShadowHue','SplitToningShadowSaturation',
                                                      'SplitToningHighlightHue','SplitToningHighlightSaturation')
SUPPORTED = set(SLIDERS) | set(CURVES) | set(HSL) | set(PARAMETRIC) | set(GRADING)
METADATA = {'PresetType', 'UUID', 'Version', 'ProcessVersion', 'HasSettings', 'Name',
            'Group', 'Cluster', 'SupportsAmount', 'SupportsColor', 'SupportsMonochrome',
            'SupportsHighDynamicRange', 'SupportsNormalDynamicRange', 'SupportsSceneReferred',
            'SupportsOutputReferred', 'RequiresRGBTables', 'ConvertToGrayscale',
            'ToneCurveName2012', 'ToneCurveName', 'RGBTable', 'CameraProfileDigest',
            'PresetName', 'Description', 'SortName', 'Copyright', 'ContactInfo',
            'ParametricShadowSplit','ParametricMidtoneSplit','ParametricHighlightSplit',
            'ColorLabels', 'TreatAsHDR', 'Look', 'CameraProfile', 'WhiteBalance'}
# Non-image-global adjustments must never be reported as transferable.
IGNORED_PREFIXES = ('Mask', 'Correction', 'Local', 'Retouch', 'Perspective', 'Crop', 'Lens',
                    'Sharpen', 'Noise', 'Grain', 'PostCrop', 'Upright', 'Defringe', 'Auto',
                    'RedEye', 'Spot', 'Paint', 'Depth', 'ColorGrade', 'SplitToning',
                    'Parametric', 'Clarity', 'Dehaze', 'Texture', 'Temperature', 'Tint',
                    'CameraCalibration', 'ShadowTint', 'RedPrimary', 'GreenPrimary',
                    'BluePrimary', 'AsShot', 'EnableProfileCorrections')


@dataclass
class XmpResult:
    cube: Cube
    kind: str
    name: str
    warnings: list[str] = field(default_factory=list)
    included: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)
    color_space: str = 'sRGB'


def _adobe85_encode(raw: bytes) -> str:
    result = []
    for start in range(0, len(raw), 4):
        chunk = raw[start:start+4]
        n = int.from_bytes(chunk.ljust(4, b'\0'), 'little')
        encoded = []
        for _ in range(5):
            encoded.append(ADOBE85[n % 85]); n //= 85
        result.extend(encoded[:len(chunk)+1])
    return ''.join(result)


def _adobe85_decode(value: str) -> bytes:
    out = bytearray()
    digits = []
    for ch in value:
        if ch.isspace():
            continue
        if ch not in _DECODE:
            raise ValueError('Invalid Adobe XMP RGBTable base85 character')
        digits.append(_DECODE[ch])
        if len(digits) == 5:
            n = sum(d*85**i for i,d in enumerate(digits))
            if n > 0xFFFFFFFF: raise ValueError('Adobe base85 overflow')
            out.extend(struct.pack('<I', n)); digits.clear()
    if digits:
        if len(digits) == 1: raise ValueError('Invalid partial Adobe base85 block')
        n = sum(d*85**i for i,d in enumerate(digits))
        if n > 0xFFFFFFFF: raise ValueError('Adobe base85 overflow')
        out.extend(struct.pack('<I', n)[:len(digits)-1])
    return bytes(out)


def _grid(n):
    axis = np.linspace(0, 1, n, dtype=np.float32)
    return np.stack(np.meshgrid(axis,axis,axis,indexing='ij'),-1)


def _binary_table(cube: Cube, size: int) -> bytes:
    grid = _grid(size)
    rgb = np.clip(apply_cube(cube,grid),0,1)
    nop = ((np.arange(size,dtype=np.uint32)*65535 + size//2)//(size-1)).astype(np.int64)
    # RGB table ordering: R major, G middle, B minor (C-contiguous).
    baseline = np.stack(np.broadcast_arrays(nop[:,None,None],nop[None,:,None],nop[None,None,:]),-1)
    delta = (np.rint(rgb*65535).astype(np.int64)-baseline) % 65536
    return (struct.pack('<4I',1,1,3,size) + delta.astype('<u2').tobytes() +
            struct.pack('<3I2d',0,1,0,0.,2.))


def export_xmp(cube: Cube, dest: str | Path, *, name: str, group=XMP_GROUP, size=32) -> dict:
    """Create an Adobe *creative profile* with its complete RGB LUT (not sliders)."""
    if not 2 <= size <= 32:
        raise ValueError('Adobe RGBTable profile grid must be 2..32')
    destination = Path(dest).expanduser().resolve()
    if destination.suffix.lower() != '.xmp':
        raise ValueError('Output path must end in .xmp')
    if not name.strip(): raise ValueError('Profile name must not be empty')
    block = _binary_table(cube, size)
    table_id = hashlib.md5(block).hexdigest()
    uuid = hashlib.md5((table_id+name+group).encode('utf-8')).hexdigest().upper()
    blob = _adobe85_encode(struct.pack('<I',len(block))+zlib.compress(block,9))
    escaped_name,escaped_group = html.escape(name,quote=True),html.escape(group,quote=True)
    text = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="{APP_NAME}">\n'
            f' <rdf:RDF xmlns:rdf="{RDF}">\n'
            f'  <rdf:Description rdf:about="" xmlns:crs="{CRS}"\n'
            f'   crs:PresetType="Look" crs:Cluster="" crs:UUID="{uuid}"\n'
            f'   crs:SupportsAmount="True" crs:SupportsColor="True" crs:SupportsMonochrome="True"\n'
            f'   crs:SupportsHighDynamicRange="True" crs:SupportsNormalDynamicRange="True"\n'
            f'   crs:SupportsSceneReferred="True" crs:SupportsOutputReferred="True"\n'
            f'   crs:RequiresRGBTables="False" crs:Version="14.3" crs:ProcessVersion="11.0"\n'
            f'   crs:RGBTable="{table_id}" crs:Table_{table_id}="{blob}" crs:HasSettings="True">\n'
            f'   <crs:Name><rdf:Alt><rdf:li xml:lang="x-default">{escaped_name}</rdf:li></rdf:Alt></crs:Name>\n'
            f'   <crs:Group><rdf:Alt><rdf:li xml:lang="x-default">{escaped_group}</rdf:li></rdf:Alt></crs:Group>\n'
            f'  </rdf:Description>\n </rdf:RDF>\n</x:xmpmeta>\n')
    # Verify codec and XML before writing atomically.
    test = _parse_xmp_bytes(text.encode('utf-8'))
    if test.kind != 'profile': raise AssertionError('XMP codec validation failed')
    import os
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name+'.partial')
    try:
        temporary.write_text(text,encoding='utf-8')
        os.replace(temporary,destination)
    finally:
        temporary.unlink(missing_ok=True)
    # Compare quantized LUT and original at non-node RGB coordinates.
    probe = _grid(11).reshape(-1,3)
    diff = abs(apply_cube(test.cube,probe)-np.clip(apply_cube(cube,probe),0,1))*255
    return {'file':str(destination),'bytes':destination.stat().st_size,'format':'Adobe Creative Profile XMP',
            'size':size,'rgb_table_md5':table_id,'roundtrip_decoded':True,
            'resample_mae_255':float(diff.mean()),'warnings':[
                'Adobe Lightroom/Camera Raw application import was not independently verified.',
                'Input LUT is assumed to map display-referred sRGB to sRGB; Log/gamut transformations are not auto-detected.',
                'XMP 3D RGBTable is limited to 32³ nodes; 33³/65³ source LUTs are resampled.']}


def _decode_table(encoded: str) -> tuple[Cube,int,int]:
    packed = _adobe85_decode(encoded)
    if len(packed) < 7: raise ValueError('Adobe RGB table is truncated')
    expected, = struct.unpack_from('<I',packed)
    if expected < 44 or expected > MAX_BINARY_BYTES:
        raise ValueError('XMP RGB table decompressed size exceeds safety limit')
    inflate = zlib.decompressobj()
    data = inflate.decompress(packed[4:],MAX_BINARY_BYTES+1)
    if len(data)>expected or inflate.unconsumed_tail:
        raise ValueError('Adobe RGB table expands beyond declared size')
    data += inflate.flush()
    if not inflate.eof or inflate.unused_data or len(data)!=expected:
        raise ValueError('Invalid/truncated Adobe RGB table compressed data')
    kind,version,dimensions,n = struct.unpack_from('<4I',data)
    if (kind,version,dimensions)!=(1,1,3) or not 2<=n<=64:
        raise ValueError('Only Adobe 3D RGBTable version 1, grid 2..64 is supported')
    expected_bytes=16+6*n**3+28
    if len(data)!=expected_bytes: raise ValueError('Adobe RGBTable binary length mismatch')
    delta=np.frombuffer(data,dtype='<u2',count=3*n**3,offset=16).reshape(n,n,n,3).astype(np.uint32)
    nop=((np.arange(n,dtype=np.uint32)*65535+n//2)//(n-1))
    base=np.stack(np.broadcast_arrays(nop[:,None,None],nop[None,:,None],nop[None,None,:]),axis=-1)
    rgb=((delta+base)&65535).astype(np.float32)/65535
    primary,gamma,gamut=struct.unpack_from('<3I',data,16+6*n**3)
    if primary>=len(PRIMARIES) or gamma>=len(GAMMAS) or gamut>1:
        raise ValueError('Unsupported Adobe RGB table color-space metadata')
    return Cube(rgb,np.zeros(3),np.ones(3),'XMP RGB Table'),primary,gamma


# D65 RGB matrices and Bradford adaptation, limited to standard declared Adobe primaries.
CHROMATICITIES = (
    ((.64,.33),(.30,.60),(.15,.06),(.3127,.329)),
    ((.64,.33),(.21,.71),(.15,.06),(.3127,.329)),
    ((.734699,.265301),(.159597,.840403),(.036598,.000105),(.34567,.35850)),
    ((.68,.32),(.265,.69),(.15,.06),(.3127,.329)),
    ((.708,.292),(.170,.797),(.131,.046),(.3127,.329))
)

def _xyz(xy):
    x,y=xy
    return np.array([x/y,1,(1-x-y)/y],dtype=np.float64)


def _rgb_xyz(primaries):
    points=CHROMATICITIES[primaries]
    matrix=np.column_stack([_xyz(p) for p in points[:3]])
    white=_xyz(points[3])
    matrix=matrix @ np.diag(np.linalg.solve(matrix,white))
    if primaries==2:
        bradford=np.array([[.8951,.2664,-.1614],[-.7502,1.7135,.0364],[.0389,-.0685,1.0296]])
        d65=_xyz(CHROMATICITIES[0][3]); scale=np.diag((bradford@d65)/(bradford@white))
        matrix=np.linalg.inv(bradford)@scale@bradford@matrix
    return matrix


def _decode_transfer(rgb, gamma):
    x=np.maximum(np.asarray(rgb,dtype=np.float64),0)
    if gamma==0:return x
    if gamma==1:return np.where(x<=.04045,x/12.92,((x+.055)/1.055)**2.4)
    if gamma==2:return x**1.8
    if gamma==3:return x**2.2
    a=1.09929682680944;b=.018053968510807
    return np.where(x<4.5*b,x/4.5,((x+(a-1))/a)**(1/.45))


def _encode_transfer(rgb, gamma):
    x=np.clip(rgb,0,1)
    if gamma==0:return x
    if gamma==1:return np.where(x<=.0031308,12.92*x,1.055*x**(1/2.4)-.055)
    if gamma==2:return x**(1/1.8)
    if gamma==3:return x**(1/2.2)
    a=1.09929682680944;b=.018053968510807
    return np.where(x<b,4.5*x,a*x**.45-(a-1))


def _convert_primaries(rgb, src, dest):
    if src==dest:return rgb
    m=np.linalg.solve(_rgb_xyz(dest),_rgb_xyz(src))
    return np.asarray(rgb) @ m.T


def _as_srgb_cube(native: Cube, primary: int, gamma: int, size=33):
    if primary==0 and gamma==1:return native
    grid=_grid(size)
    native_in=_encode_transfer(_convert_primaries(_decode_transfer(grid,1),0,primary),gamma)
    native_out=apply_cube(native,np.clip(native_in,0,1))
    srgb=_encode_transfer(_convert_primaries(_decode_transfer(native_out,gamma),primary,0),1)
    return Cube(srgb.astype(np.float32),np.zeros(3),np.ones(3),'XMP RGB Table (sRGB)')


def _attrs_and_curves(root):
    result={}
    for desc in root.iter():
        if desc.tag != '{%s}Description'%RDF: continue
        for key,value in desc.attrib.items():
            if key.startswith('{'+CRS+'}'):
                result[key.split('}',1)[1]]=value
        # The outermost camera-raw RDF description is authoritative; nested
        # crs:Look metadata must never overwrite its settings.
        if result:
            break
    for element in root.iter():
        if element.tag.startswith('{'+CRS+'}'):
            key=element.tag.split('}',1)[1]
            if key in CURVES:
                pts=[]
                for li in element.iter():
                    if li.tag=='{%s}li'%RDF and li.text:
                        m=re.fullmatch(r'\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*',li.text)
                        if m:pts.append((float(m.group(1)),float(m.group(2))))
                if len(pts)>=2 and all(np.isfinite(pts).flat):result[key]=pts
    return result


def _preset_cube(attrs):
    detected=[]; ignored=[]
    controls={}
    for key in SLIDERS+HSL+PARAMETRIC+GRADING:
        if key not in attrs:continue
        try:value=float(attrs[key])
        except (ValueError, TypeError):ignored.append(key);continue
        if not np.isfinite(value):ignored.append(key);continue
        if abs(value)>1e-7:
            controls[key]=value;detected.append(key)
    for key in CURVES:
        points=attrs.get(key)
        if isinstance(points,list):
            points=np.array(points,dtype=float)
            if (np.diff(points[:,0])<=0).any():ignored.append(key);continue
            if np.max(np.abs(points[:,1]-points[:,0]))>.05:
                controls[key]=points;detected.append(key)
    for key,value in attrs.items():
        if key in SUPPORTED or key in METADATA or key.startswith('Table_'):continue
        # Ignore zero/default settings without warning; meaningful unsupported
        # adjustments are reported instead of silently claiming exactness.
        if isinstance(value,str) and value.strip().lower() in ('','0','0.0','+0','false','as shot','none','default','linear'):
            continue
        ignored.append(key)
    if not detected:
        if ignored:
            raise ValueError('This XMP has no supported non-neutral color adjustments. Unsupported: '+', '.join(ignored[:12]))
        raise ValueError('XMP has no embedded RGB LUT or supported non-neutral develop adjustments')
    rgb=_grid(33)
    # These are deterministic display-RGB approximations, not Lightroom formulas.
    exposure=np.clip(controls.get('Exposure2012',0),-5,5)
    rgb=np.clip(rgb*(2**exposure),0,1)
    contrast=np.clip(controls.get('Contrast2012',0),-100,100)/100
    rgb=np.clip((rgb-.5)*(1+.70*contrast)+.5,0,1)
    y=np.mean(rgb,axis=-1,keepdims=True)
    for key,weight,center,width in (
            ('Highlights2012',.45,.76,.27),('Shadows2012',.42,.24,.27),
            ('Whites2012',.22,.94,.17),('Blacks2012',.22,.06,.17),
            ('ParametricShadows',.23,.12,.19),('ParametricDarks',.23,.36,.19),
            ('ParametricLights',.23,.64,.19),('ParametricHighlights',.23,.88,.19)):
        val=np.clip(controls.get(key,0),-100,100)/100
        if val:
            # Smooth luma-local additive adjustment, preserving black/white envelope.
            mask=np.exp(-.5*((y-center)/width)**2)*np.maximum(0,4*y*(1-y))
            rgb=np.clip(rgb+val*weight*mask,0,1)
            y=np.mean(rgb,axis=-1,keepdims=True)
    for key in CURVES:
        if key not in controls:continue
        pts=controls[key]
        if key=='ToneCurvePV2012':
            rgb=np.stack([np.interp(rgb[...,ch]*255,pts[:,0],pts[:,1])/255 for ch in range(3)],-1)
        else:
            ch=CURVES.index(key)-1
            rgb[...,ch]=np.interp(rgb[...,ch]*255,pts[:,0],pts[:,1])/255
        rgb=np.clip(rgb,0,1)
    # HSV model for coarse saturation / vibrance and eight HSL bands.
    mx=rgb.max(-1);mn=rgb.min(-1);d=mx-mn
    val=mx.copy();sat=np.divide(d,mx,out=np.zeros_like(d),where=mx>1e-7)
    hue=np.zeros_like(mx)
    mask=d>1e-7
    idx=(mx==rgb[...,0])&mask;hue[idx]=((rgb[...,1][idx]-rgb[...,2][idx])/d[idx])%6
    idx=(mx==rgb[...,1])&mask;hue[idx]=(rgb[...,2][idx]-rgb[...,0][idx])/d[idx]+2
    idx=(mx==rgb[...,2])&mask;hue[idx]=(rgb[...,0][idx]-rgb[...,1][idx])/d[idx]+4
    hue=(hue/6)%1
    saturation=np.clip(controls.get('Saturation',0),-100,100)/100
    vibrance=np.clip(controls.get('Vibrance',0),-100,100)/100
    sat=np.clip(sat*(1+saturation)+vibrance*.70*sat*(1-sat),0,1)
    degrees=np.array([0,30,60,120,180,240,278,320],dtype=float)
    if any(k in controls for k in HSL):
        angle=hue*360
        weights=np.exp(-.5*( ((angle[...,None]-degrees+180)%360-180)/23)**2)
        weights=weights/(1+weights.sum(-1,keepdims=True)*.15)
        hue_offset=np.array([controls.get('HueAdjustment'+b,0) for b in COLOR_BANDS])
        sat_offset=np.array([controls.get('SaturationAdjustment'+b,0) for b in COLOR_BANDS])
        lum_offset=np.array([controls.get('LuminanceAdjustment'+b,0) for b in COLOR_BANDS])
        hue=(hue+np.sum(weights*hue_offset,axis=-1)*.30/360)%1
        sat=np.clip(sat*(1+np.sum(weights*sat_offset,axis=-1)/100),0,1)
        val=np.clip(val+np.sum(weights*lum_offset,axis=-1)/100*val*(1-val)*.7,0,1)
    h=hue*6; c=val*sat; x=c*(1-np.abs((h%2)-1)); m=val-c
    rgb2=np.zeros_like(rgb); sector=np.floor(h).astype(int)%6
    values=((c,x,0),(x,c,0),(0,c,x),(0,x,c),(x,0,c),(c,0,x))
    for i,channels in enumerate(values):
        selected=sector==i
        for channel,value in enumerate(channels):
            if isinstance(value,np.ndarray):rgb2[...,channel][selected]=value[selected]
    rgb2=np.clip(rgb2+m[...,None],0,1)
    if any(k in controls for k in GRADING):
        import colorsys
        y=np.mean(rgb2,axis=-1)
        for region,center,width in (('Shadow',.18,.32),('Midtone',.5,.34),
                                    ('Highlight',.82,.32),('Global',.5,2)):
            h=controls.get(f'ColorGrade{region}Hue',
                           controls.get('SplitToning'+region+'Hue',0))
            sat=controls.get(f'ColorGrade{region}Sat',
                             controls.get('SplitToning'+region+'Saturation',0))
            lum=controls.get(f'ColorGrade{region}Lum',0)
            if not (sat or lum):continue
            mask=np.exp(-.5*((y-center)/width)**2)
            if sat:
                tint=np.asarray(colorsys.hsv_to_rgb((h%360)/360,1,1))
                tint=tint-tint.mean()
                rgb2=np.clip(rgb2+mask[...,None]*(sat/100)*tint[None,None,None,:]*.18,0,1)
            if lum:
                rgb2=np.clip(rgb2+mask[...,None]*lum/100*y[...,None]*(1-y[...,None])*.65,0,1)
    return Cube(rgb2.astype(np.float32),np.zeros(3),np.ones(3),'XMP develop preset approximation'),detected,sorted(set(ignored))


def _parse_xmp_bytes(raw: bytes) -> XmpResult:
    if len(raw)>MAX_XMP_BYTES:raise ValueError('XMP file exceeds 16 MiB limit')
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('DOCTYPE / ENTITY declarations are not allowed in XMP')
    try:root=ET.fromstring(raw)
    except ET.ParseError as ex:raise ValueError('Invalid XMP/XML file') from ex
    attrs=_attrs_and_curves(root)
    name=attrs.get('Name','')
    if not name:
        for node in root.iter():
            if node.tag=='{%s}Name'%CRS:
                name=next((el.text for el in node.iter() if el.tag=='{%s}li'%RDF and el.text),'')
                if name:break
    name = str(name or 'Adobe XMP')
    table_id = attrs.get('RGBTable')
    if table_id:
        if not re.fullmatch(r'[0-9a-fA-F]{32}',table_id):raise ValueError('Invalid Adobe RGBTable identifier')
        encoded=attrs.get('Table_'+table_id)
        if encoded is None:
            # Some Adobe profiles use alternate hex case in the attribute name.
            encoded=next((v for k,v in attrs.items() if k.lower()=='table_'+table_id.lower()),None)
        if encoded is None:raise ValueError('XMP profile references an RGBTable but the embedded table is missing')
        native,primary,gamma=_decode_table(encoded)
        transformed=_as_srgb_cube(native,primary,gamma)
        warns=['Adobe XMP profile RGB table is imported; external profile stages/extra edits are not reproduced.']
        if primary!=0 or gamma!=1:
            warns.append(f'Embedded table color-space converted from {PRIMARIES[primary]} / {GAMMAS[gamma]} to display sRGB (gamut clipping possible).')
        return XmpResult(transformed,'profile',name,warns,['RGBTable'],[],f'{PRIMARIES[primary]} / {GAMMAS[gamma]}')
    # XMP can also be a camera RAW sidecar, unrelated metadata, or a normal develop preset.
    if not attrs:raise ValueError('No Adobe Camera Raw settings found in XMP')
    cube,included,ignored=_preset_cube(attrs)
    warns=['Develop preset values are APPROXIMATED in display RGB; they do not implement Adobe Lightroom processing.',
           'Scene-aware RAW adjustments, base camera profiles, white balance and local masks are not portable to PF3.']
    if attrs.get('CameraProfile','') not in ('','Embedded'):
        warns.append('Referenced camera profile not embedded: '+attrs['CameraProfile'])
    if any(node.tag=='{%s}Look'%CRS for node in root.iter()):
        warns.append('Referenced creative look is not embedded in the converted LUT.')
    if ignored:warns.append('Unsupported/omitted settings: '+', '.join(ignored[:24]))
    return XmpResult(cube,'preset',name,warns,included,ignored)


def load_xmp(path: str | Path) -> XmpResult:
    source=Path(path)
    if source.stat().st_size>MAX_XMP_BYTES:raise ValueError('XMP file exceeds 16 MiB limit')
    result=_parse_xmp_bytes(source.read_bytes())
    if result.name=='Adobe XMP':result.name=source.stem
    return result
