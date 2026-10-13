"""CPU regression tests for unit conversion, transforms and failure detection."""
import json
from pathlib import Path
import tempfile
import unittest
from pxr import Gf, UsdGeom
from tools.omniverse.export_usd import ROOT, decode_cad_glb, export, matrix, new_stage
from tools.omniverse.usdchecker import check


class USDTest(unittest.TestCase):
    def test_column_major_rotation_translation_and_reflection(self):
        # +90 degrees Y, then position (12,3,7): local +Z -> world +X.
        transform = matrix([0,0,-1,0, 0,1,0,0, 1,0,0,0, 12,3,7,1])
        self.assertEqual(transform.Transform(Gf.Vec3d(0,0,2)), Gf.Vec3d(14,3,7))
        mirrored = matrix([-2,0,0,0, 0,3,0,0, 0,0,4,0, 0,0,0,1])
        self.assertEqual((mirrored*transform).Transform(Gf.Vec3d(1,0,0)), Gf.Vec3d(12,3,9))

    def test_cad_glb_is_already_metres(self):
        for name,expected in [('conveyor',[2,.7,.6]),('inspection_booth',[.8,1.5,.8]),('diverter',[1,.7,.6])]:
            geom=decode_cad_glb(ROOT/'assets/cad'/name/'dt_v1/model.glb')
            for i,dim in enumerate(expected):
                self.assertAlmostEqual(max(geom['points'][i::3])-min(geom['points'][i::3]),dim,places=6)

    def test_stale_capture_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'stale.json';source.write_text(json.dumps({'source_hashes':{}}))
            target=Path(d)/'campus.usda'
            with self.assertRaisesRegex(ValueError,'Stale prefab'):
                export(source,target)
            self.assertFalse(target.exists())

    def test_official_validator_rejects_unresolved_reference(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'bad.usda';stage=new_stage(path)
            UsdGeom.Xform.Define(stage,'/World/Missing').GetPrim().GetReferences().AddReference('missing.usda')
            stage.GetRootLayer().Save()
            result=check(path)
            self.assertFalse(result['pass'])
            self.assertTrue(any(r['issues'] for r in result['runs']))


if __name__=='__main__':
    unittest.main()
