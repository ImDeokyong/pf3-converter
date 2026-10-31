"""Regression tests for the Adobe RGB-table codec and approximate develop presets."""
import tempfile
import unittest
from pathlib import Path
import numpy as np

from lut import Cube, load_cube, apply_cube
from xmp_bridge import (_adobe85_encode, _adobe85_decode, _parse_xmp_bytes,
                        export_xmp, load_xmp, _binary_table, _decode_table, _as_srgb_cube)
from canon_fit import fit_cube
from cli import main


class TestXmpBridge(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.folder=Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def identity(self):
        return load_cube(Path(__file__).resolve().parents[1]/'example_luts'/'identity_2.cube')

    def test_base85_roundtrip_all_partial_lengths(self):
        for n in range(1,101):
            raw=bytes((17*i+5)%256 for i in range(n))
            self.assertEqual(_adobe85_decode(_adobe85_encode(raw)),raw)

    def test_cube_to_xmp_to_cube_identity(self):
        out=self.folder/'인물 & 도시.xmp'
        info=export_xmp(self.identity(),out,name='인물 & 도시 <Film> "2026"',group='Test & 프로파일')
        self.assertEqual(info['size'],32)
        self.assertTrue(info['roundtrip_decoded'])
        x=load_xmp(out)
        self.assertEqual(x.kind,'profile')
        self.assertEqual(x.name,'인물 & 도시 <Film> "2026"')
        pts=np.random.default_rng(52).random((200,3))
        self.assertLess(abs(apply_cube(x.cube,pts)-pts).max(),3e-5)

    def test_nontrivial_33_cube_profile_roundtrip(self):
        cube=self.identity()
        cube.data=np.array([[[[.03,.06,.1],[.8,.9,.85]],[[.05,.7,.3],[.9,1.,.7]]],
                            [[[.9,.1,.05],[.8,.3,.9]],[[.95,.8,.3],[1.,1.,1.]]]],dtype=np.float32)
        out=self.folder/'look.xmp'
        exported=export_xmp(cube,out,name='Film')
        decoded=load_xmp(out).cube
        pts=np.random.default_rng(14).random((150,3))
        error=abs(apply_cube(decoded,pts)-apply_cube(cube,pts))
        self.assertLess(error.max(),.001)
        self.assertLess(exported['resample_mae_255'],.02)
        self.assertTrue(out.read_bytes().startswith(b'<?xml'))

    def test_xmp_3d_table_color_space_conversion(self):
        cube=self.identity()
        encoded=_binary_table(cube,9)
        self.assertEqual(_decode_table(_adobe85_encode(__import__('struct').pack('<I',len(encoded))+
                             __import__('zlib').compress(encoded)))[1:],(0,1))
        transformed=_as_srgb_cube(cube,2,2)
        self.assertTrue(np.isfinite(transformed.data).all())
        self.assertEqual(transformed.size,33)

    def test_slider_preset_sampled_and_fit(self):
        xmp=b'''<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/">
        <rdf:RDF><rdf:Description crs:PresetType="Normal" crs:Exposure2012="+0.7" crs:Contrast2012="+10"
        crs:Saturation="-9" crs:HueAdjustmentOrange="+7" crs:SharpenAmount="22" crs:GrainAmount="8">
        <crs:ToneCurvePV2012><rdf:Seq><rdf:li>0, 10</rdf:li><rdf:li>128, 125</rdf:li><rdf:li>255, 246</rdf:li></rdf:Seq></crs:ToneCurvePV2012>
        </rdf:Description></rdf:RDF></x:xmpmeta>'''
        file=self.folder/'preset.xmp';file.write_bytes(xmp)
        result=load_xmp(file)
        self.assertEqual(result.kind,'preset')
        self.assertIn('Exposure2012',result.included)
        self.assertIn('ToneCurvePV2012',result.included)
        self.assertIn('GrainAmount',result.ignored)
        self.assertGreater(abs(result.cube.data-self.identity().data[0,0,0]).mean(),.05)
        fit=fit_cube(result.cube)
        self.assertTrue(np.isfinite(fit.report['estimated_rgb_mae_255']))

    def test_colorgrading_and_parametric_only_preset(self):
        raw=b'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
          xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/">
          <rdf:Description crs:ColorGradeShadowHue="24" crs:ColorGradeShadowSat="45"
          crs:ParametricHighlights="-30" crs:ColorGradeHighlightLum="-12"/></rdf:RDF>'''
        result=_parse_xmp_bytes(raw)
        self.assertEqual(result.kind,'preset')
        self.assertIn('ColorGradeShadowSat',result.included)
        self.assertIn('ParametricHighlights',result.included)
        self.assertFalse(np.allclose(result.cube.data[5,5,5],np.array([5/32]*3)))

    def test_cli_xmp_to_pf3_calls_native_pipeline(self):
        from unittest.mock import patch
        xmp=self.folder/'source.xmp'
        export_xmp(self.identity(),xmp,name='XMP profile')
        fake={'file':str(self.folder/'out.pf3'),'fit':{'estimated_rgb_mae_255':0}}
        with patch('cli.export_pf3',return_value=fake) as native:
            result=main([str(xmp),'-o',str(self.folder/'out.pf3')])
        self.assertEqual(result,0)
        self.assertTrue(native.called)
        self.assertEqual(native.call_args.args[0].size,32)

    def test_no_silent_identity_from_unsupported_xmp(self):
        xmp=b'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"><rdf:Description crs:GrainAmount="80" crs:Clarity2012="+90"/></rdf:RDF>'''
        with self.assertRaisesRegex(ValueError,'no supported non-neutral'):
            _parse_xmp_bytes(xmp)

    def test_malformed_or_non_adobe_rejected(self):
        for raw in (b'<bad>',b'<root/>',b'<!DOCTYPE x [<!ENTITY e "thing">]><x/>'):
            with self.assertRaises(ValueError):_parse_xmp_bytes(raw)

    def test_cli_cube_to_xmp_without_canon_dll(self):
        target=self.folder/'cli.xmp'
        self.assertEqual(main([str(Path(__file__).resolve().parents[1]/'example_luts'/'identity_2.cube'),
                               '-o',str(target)]),0)
        self.assertEqual(load_xmp(target).kind,'profile')

    def test_native_pf3_export_still_windows_only(self):
        import sys
        if sys.platform!='win32':
            source=self.folder/'source.xmp'
            export_xmp(self.identity(),source,name='Test')
            self.assertEqual(main([str(source),'-o',str(self.folder/'out.pf3')]),1)


if __name__=='__main__':unittest.main()
