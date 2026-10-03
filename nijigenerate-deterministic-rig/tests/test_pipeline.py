from pathlib import Path
import copy
import sys
import tempfile
import unittest
import numpy as np
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from riglib.data import load_template, json_digest,write_json
from riglib.observe import observe_image
from riglib.pipeline import fit_surface,evaluate_surface,sample_pose_suite
ROOT=Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"source.png"
        image=Image.new("RGBA",(200,240))
        ImageDraw.Draw(image).ellipse([10,10,190,230],fill="white")
        image.save(self.path)
        template=load_template(ROOT/"templates"/"face_head.json")
        self.hints={"landmarks":{item["id"]:[10+180*item["uv"][0],10+220*item["uv"][1]]
                                 for item in template["landmarks"] if item["required"]}}

    def tearDown(self): self.temp.cleanup()

    def fit(self): return fit_surface(ROOT/"templates"/"face_head.json",self.path,self.hints)

    def test_missing_semantic_evidence_returns_request_not_guessed_nose(self):
        result=fit_surface(ROOT/"templates"/"face_head.json",self.path)
        self.assertEqual(result["status"],"needs_landmarks")
        self.assertIn("nose_tip",result["missing_roles"])

    def test_same_input_is_identical_and_neutral_is_preserved(self):
        a,b=self.fit(),self.fit()
        self.assertEqual(a,b)
        neutral=evaluate_surface(a,{})
        self.assertEqual(neutral["xy"],a["mesh"]["rest_xy"])
        self.assertTrue(all(p["validation"]["finite"] for p in sample_pose_suite(a)))

    def test_changing_depth_preserves_neutral_but_changes_yaw(self):
        a=self.fit()
        definition=load_template(ROOT/"templates"/"face_head.json")["tunables"][0]
        self.hints["parameters"]={definition["id"]:definition["default"]*1.1}
        b=self.fit()
        np.testing.assert_array_equal(evaluate_surface(a,{})["xy"],evaluate_surface(b,{})["xy"])
        self.assertFalse(np.allclose(evaluate_surface(a,{"yaw":25})["xy"],evaluate_surface(b,{"yaw":25})["xy"]))

    def test_tampered_fit_is_rejected(self):
        fit=self.fit();fit["depth"][0]+=1
        with self.assertRaises(ValueError): evaluate_surface(fit,{})

    def test_neutral_vertex_identity_does_not_hide_uncovered_artwork(self):
        bounds=[60,60,140,180]
        template=load_template(ROOT/"templates"/"face_head.json")
        self.hints={"bounds":bounds,"landmarks":{l["id"]:[60+80*l["uv"][0],60+120*l["uv"][1]]
                     for l in template["landmarks"] if l["required"]}}
        result=self.fit()
        self.assertEqual(result["status"],"needs_coverage")
        self.assertGreater(result["coverage"]["uncovered_pixels"],0)

    def test_host_pixel_units_require_and_apply_explicit_scale(self):
        host=self.fit();host_path=Path(self.temp.name)/"host.json";write_json(host_path,host)
        image=Image.new("RGBA",(400,480));ImageDraw.Draw(image).ellipse([20,20,380,460],fill="white");image.save(self.path)
        template=load_template(ROOT/"templates"/"surface_layer.json")
        hints={"parameters":{"layer_offset":0},"landmarks":{l["id"]:[20+360*l["uv"][0],20+440*l["uv"][1]]
                 for l in template["landmarks"] if l["required"]},
               "bounds":[20,20,380,460],"host":{"fit":str(host_path),"mapping":"same_material_uv"}}
        with self.assertRaises(ValueError): fit_surface(ROOT/"templates"/"surface_layer.json",self.path,hints)
        hints["host"]["host_to_source_scale"]=2
        child=fit_surface(ROOT/"templates"/"surface_layer.json",self.path,hints)
        self.assertEqual(child["status"],"fitted_unreviewed")
        from riglib.geometry import sample_grid
        grid=np.asarray(host["depth"]).reshape(len(host["mesh"]["v_lines"]),len(host["mesh"]["u_lines"]),1)
        expected=sample_grid(grid,host["mesh"]["u_lines"],host["mesh"]["v_lines"],child["mesh"]["uv"]).reshape(-1)*2
        np.testing.assert_allclose(child["depth"],expected)

    def test_holes_are_kept_as_multiple_alpha_intervals(self):
        image=Image.new("RGBA",(30,30),"white")
        ImageDraw.Draw(image).rectangle([10,5,20,25],fill=(0,0,0,0));image.save(self.path)
        obs=observe_image(self.path)
        self.assertTrue(any(len(r["intervals"])==2 for r in obs["rows"]))

    def test_unknown_parameter_and_invalid_pose_are_rejected(self):
        self.hints["parameters"]={"ad_hoc_fix":1}
        with self.assertRaises(ValueError): self.fit()
        self.hints.pop("parameters")
        with self.assertRaises(ValueError): evaluate_surface(self.fit(),{"yaw":float("nan")})


if __name__=="__main__": unittest.main()
