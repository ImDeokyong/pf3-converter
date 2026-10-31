"""CLI for CUBE/XMP -> PF3, Adobe XMP and LUMIX CUBE (MIT)."""
import argparse
import json
from pathlib import Path
import sys

from lut import load_cube
from lumix_export import export_lumix_cube, export_srgb_cube, PHOTO_STYLES
from xmp_bridge import load_xmp, export_xmp
from app_info import APP_NAME, APP_AUTHOR, display_name, XMP_GROUP
from pf3_native import STYLE_IDS, export_pf3, find_canon_library
from log_adapt import LOG_CURVES, adapt_log_lut


def main(argv=None):
    parser = argparse.ArgumentParser(description=f'{display_name()} by {APP_AUTHOR}: CUBE/XMP to approximate Canon PF3; CUBE to Lightroom creative XMP profile.')
    parser.add_argument('--version', action='version', version=f'{display_name()} | 제작자 : {APP_AUTHOR}')
    parser.add_argument('input', nargs='?', help='Input 3D .cube or Adobe .xmp file')
    parser.add_argument('-o', '--output', help='Output .pf3, .xmp (CUBE input only), or .cube')
    parser.add_argument('--name', help='Profile name')
    parser.add_argument('--base', default='Neutral', choices=STYLE_IDS.keys())
    parser.add_argument('--strength', type=float, default=1., help='Blend factor for PF3, Photoshop CUBE or LUMIX CUBE, 0..1')
    parser.add_argument('--lumix-style', choices=tuple(PHOTO_STYLES), metavar='STYLE',
        help='Write LUMIX-compatible 33³ CUBE, tagged with base Photo Style (e.g. STD, NAT, VLOG)')
    parser.add_argument('--dll', help='Path to installed Canon EdsCFParse.dll')
    parser.add_argument('--xmp-group', default=XMP_GROUP, help='Adobe XMP creative profile group')
    parser.add_argument('--probe', action='store_true', help='Locate Canon engine')
    parser.add_argument('--log-input', choices=tuple(LOG_CURVES),
        help='Input CUBE expects Fujifilm F-Log/F-Log2 (F-Gamut); adapt it to ordinary photos first')
    parser.add_argument('--exposure', type=float, default=0., help='With --log-input: exposure offset in stops')
    parser.add_argument('--highlight-stops', default='2',
        help='With --log-input: extra stops above grey for photo highlights (default 2, or "auto" to make photo white render white)')
    parser.add_argument('--shadow-compress', type=float, default=0.35,
        help='With --log-input: 0..0.8, pulls shadows toward grey so camera and LUT contrast do not stack (default 0.35)')
    parser.add_argument('--log-output', choices=('rec709', 'srgb'), default='rec709',
        help='With --log-input: keep the LUT BT.709 output as is, or re-encode gamma 2.4 for sRGB')
    args = parser.parse_args(argv)
    try:
        if args.probe:
            print(str(find_canon_library(args.dll)))
            return 0
        if not args.input:parser.error('an input .cube or .xmp is required')
        source=Path(args.input)
        if source.suffix.lower()=='.cube':
            cube=load_cube(source)
            xmp_info=None
        elif source.suffix.lower()=='.xmp':
            xmp_info=load_xmp(source)
            cube=xmp_info.cube
        else:
            raise ValueError('Input must end in .cube or .xmp')
        adapt_info=None
        if args.log_input:
            if xmp_info:raise ValueError('--log-input requires a .cube input')
            stops=args.highlight_stops if args.highlight_stops=='auto' else float(args.highlight_stops)
            adapted=adapt_log_lut(cube,args.log_input,stops,args.exposure,args.log_output,
                                  shadow_compress=args.shadow_compress)
            cube=adapted.cube
            adapt_info={'curve':adapted.curve,'highlight_stops':adapted.highlight_stops,
                        'exposure':adapted.exposure,'shadow_compress':args.shadow_compress,'photo_white_out':round(adapted.white_out,4),
                        'photo_grey_out':round(adapted.grey_out,4),'output':args.log_output}
        dest=Path(args.output) if args.output else source.with_suffix('.pf3')
        if args.lumix_style and dest.suffix.lower() != '.cube':
            raise ValueError('--lumix-style requires a .cube output')
        if dest.suffix.lower()=='.xmp':
            if source.suffix.lower()!='.cube':raise ValueError('.xmp output requires a .cube input')
            info=export_xmp(cube,dest,name=args.name or source.stem,group=args.xmp_group)
        elif dest.suffix.lower()=='.cube':
            if source.resolve() == dest.resolve():
                raise ValueError('Output cannot overwrite source CUBE')
            if args.lumix_style:
                info=export_lumix_cube(cube,dest,style=args.lumix_style,
                                       strength=args.strength,title=args.name or source.stem)
            else:
                info=export_srgb_cube(cube,dest,strength=args.strength,title=args.name or source.stem)
            if xmp_info:
                info['xmp_source']={'kind':xmp_info.kind,'included':xmp_info.included,
                                    'ignored':xmp_info.ignored,'warnings':xmp_info.warnings}
        elif dest.suffix.lower()=='.pf3':
            info=export_pf3(cube,dest,name=args.name or source.stem,dll=args.dll,
                            base=args.base,strength=args.strength)
            if xmp_info:
                info['xmp_source']={'kind':xmp_info.kind,'included':xmp_info.included,
                                    'ignored':xmp_info.ignored,'warnings':xmp_info.warnings,
                                    'table_color_space':xmp_info.color_space}
        else:raise ValueError('Output must end in .pf3, .xmp, or .cube')
        if adapt_info:info['log_adapt']=adapt_info
        print(json.dumps(info,indent=2,ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f'ERROR: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
