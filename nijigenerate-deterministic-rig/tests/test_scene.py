"""Shared-surface scene tests; synthetic nominal geometry, no model mutation."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from riglib.data import json_digest
from riglib.geometry import GeometryError, evaluate_depth, make_uv_grid
from riglib.scene import register_scene, evaluate_scene


def make_fit(depth=.1, pivot=(0, 0, 0)):
    u, v = [0, .5, 1], [0, .5, 1]
    uv = make_uv_grid(u, v)
    operators = [{"type": "constant", "value": depth}]
    fit = {
        "schema_version": "rig-fit/1", "status": "fitted_unreviewed",
        "template": {"id": "synthetic-shared-chart",
                     "geometry": {"operators": operators}, "correction_rules": []},
        "parameters": {}, "bounds": [0, 0, 2, 2], "depth_scale": 2,
        "control": {"u_lines": u, "v_lines": v, "xy": (uv*2).tolist()},
        "mesh": {"u_lines": u, "v_lines": v, "uv": uv.reshape(-1, 2).tolist(),
                 "rest_xy": (uv.reshape(-1, 2)*2).tolist()},
        "depth": (evaluate_depth(uv.reshape(-1, 2), operators)*2).tolist(),
        "pivot": list(pivot), "neutral_pose": {"yaw": 0., "pitch": 0., "roll": 0.},
        "host": None,
    }
    fit["content_sha256"] = json_digest(fit)
    return fit


def node(uid, vertices, tx=0, ty=0):
    matrix = np.eye(4)
    matrix[:2, 3] = [tx, ty]
    return {"uuid": uid, "type": "Part", "enabled_effective": True,
            "mesh": {"vertices": vertices, "vertex_count": len(vertices), "origin_nonzero": False},
            "nominal_world_matrix": matrix.tolist(), "bounds": {"status": "nominal_base_affine"}}


def shared_fixture():
    model = {"nodes": [
        node(11, [[.5, .5], [.8, .5], [.5, .8]]),
        node(22, [[0, .5], [.3, .5], [0, .8]], tx=.5),
    ]}
    structure = {"surfaces": [{"id": "shared"}],
                 "part_assignments": [{"part": 11, "surface": "shared"},
                                      {"part": 22, "surface": "shared"}]}
    specs = {"shared": {"fit": make_fit(), "source_to_model": np.eye(3).tolist(), "parent": None}}
    return model, structure, specs


class SharedSceneTests(unittest.TestCase):
    def test_two_parts_register_to_one_field_and_preserve_seam(self):
        model, structure, specs = shared_fixture()
        scene = register_scene(model, structure, specs)
        self.assertEqual(scene["status"], "registered_nominal_unreviewed")
        self.assertEqual(len(scene["surfaces"]), 1)
        self.assertEqual(scene["coverage"]["registered_parts"], 2)
        np.testing.assert_array_equal(scene["parts"]["11"]["material_uv"], scene["parts"]["22"]["material_uv"])
        result = evaluate_scene(scene, {"shared": {"yaw": 25, "roll": 8}})
        np.testing.assert_array_equal(result["parts"]["11"]["world_xyz"], result["parts"]["22"]["world_xyz"])

    def test_neutral_preserves_original_world_xy_and_local_values(self):
        model, structure, specs = shared_fixture()
        scene = register_scene(model, structure, specs)
        result = evaluate_scene(scene, include_local=True)
        for uid in ("11", "22"):
            np.testing.assert_array_equal(
                result["parts"][uid]["world_xy"], np.asarray(scene["parts"][uid]["nominal_world_xyz"])[:, :2])
            np.testing.assert_allclose(
                result["parts"][uid]["local_xy_displacements_in_nominal_frame"], 0, atol=1e-15)
        self.assertEqual(result["validation"]["max_projected_displacement"], 0)

    def test_similarity_rotates_source_axes_and_scales_depth(self):
        model = {"nodes": [node(1, [[9, 11], [9, 12], [8, 11]])]}
        structure = {"part_assignments": {"1": "s"}}
        specs = {"s": {"fit": make_fit(.1), "source_to_model": [[0, -2, 10], [2, 0, 10], [0, 0, 1]],
                        "parent": None, "depth_origin": 3}}
        scene = register_scene(model, structure, specs)
        points = np.asarray(scene["parts"]["1"]["rest_world_xyz"])
        np.testing.assert_allclose(points[:, 2], 3.4)
        result = evaluate_scene(scene)
        np.testing.assert_array_equal(np.asarray(result["parts"]["1"]["world_xyz"])[:, :2], points[:, :2])

    def test_parent_rigid_rotation_applies_once(self):
        model = {"nodes": [node(1, [[.5, .5], [.8, .5], [.5, .8]], tx=2)]}
        structure = {"surfaces": [{"id": "parent"}, {"id": "child"}], "part_assignments": {"1": "child"}}
        specs = {
            "parent": {"fit": make_fit(0), "source_to_model": np.eye(3).tolist(), "parent": None},
            "child": {"fit": make_fit(0), "source_to_model": [[1, 0, 2], [0, 1, 0], [0, 0, 1]],
                      "parent": "parent"},
        }
        scene = register_scene(model, structure, specs)
        output = evaluate_scene(scene, {"parent": {"roll": 90}})
        np.testing.assert_allclose(output["parts"]["1"]["world_xy"][0], [-.5, 2.5], atol=1e-14)

    def test_parent_and_child_rotate_about_their_own_rest_pivots(self):
        model = {"nodes": [node(1, [[.5, .5], [.8, .5], [.5, .8]], tx=2)]}
        structure = {"part_assignments": {"1": "child"}}
        specs = {
            "parent": {"fit": make_fit(0), "source_to_model": np.eye(3).tolist(), "parent": None},
            "child": {"fit": make_fit(0), "source_to_model": [[1, 0, 2], [0, 1, 0], [0, 0, 1]],
                      "parent": "parent"},
        }
        scene = register_scene(model, structure, specs)
        output = evaluate_scene(scene, {"parent": {"roll": 90}, "child": {"roll": 90}})
        np.testing.assert_allclose(output["parts"]["1"]["world_xy"][0], [-.5, 1.5], atol=1e-14)

    def test_source_matrix_must_be_positive_uniform_similarity(self):
        for matrix in ([[1, 0, 0], [0, 2, 0], [0, 0, 1]],
                       [[-1, 0, 0], [0, 1, 0], [0, 0, 1]],
                       [[1, .2, 0], [0, 1, 0], [0, 0, 1]]):
            model, structure, specs = shared_fixture()
            specs["shared"]["source_to_model"] = matrix
            with self.subTest(matrix=matrix), self.assertRaises(GeometryError):
                register_scene(model, structure, specs)

    def test_unknown_part_and_surface_mapping_fail(self):
        model, structure, specs = shared_fixture()
        structure["part_assignments"][0]["part"] = 999
        with self.assertRaisesRegex(GeometryError, "observed Part"):
            register_scene(model, structure, specs)
        model, structure, specs = shared_fixture()
        structure["part_assignments"][0]["surface"] = "not-declared"
        with self.assertRaisesRegex(GeometryError, "undeclared"):
            register_scene(model, structure, specs)

    def test_missing_parent_declaration_is_unresolved_not_assumed_root(self):
        model, structure, specs = shared_fixture()
        del specs["shared"]["parent"]
        scene = register_scene(model, structure, specs)
        self.assertEqual(scene["status"], "unresolved")
        self.assertTrue(any("parent" in r.get("fields", []) for r in scene["unresolved"]))
        with self.assertRaisesRegex(GeometryError, "unresolved"):
            evaluate_scene(scene)

    def test_missing_surface_and_unassigned_part_are_reported(self):
        model, structure, specs = shared_fixture()
        structure["part_assignments"].pop()
        scene = register_scene(model, structure, {})
        kinds = {item["kind"] for item in scene["unresolved"]}
        self.assertIn("unassigned_active_part", kinds)
        self.assertIn("missing_surface_specification", kinds)
        self.assertEqual(scene["coverage"]["registered_parts"], 0)

    def test_outside_material_chart_fails(self):
        model, structure, specs = shared_fixture()
        model["nodes"][0]["mesh"]["vertices"][0] = [3, 3]
        with self.assertRaisesRegex(GeometryError, "outside"):
            register_scene(model, structure, specs)

    def test_unknown_bounds_and_uninterpreted_mesh_origin_fail(self):
        model, structure, specs = shared_fixture()
        model["nodes"][0]["bounds"]["status"] = "unknown"
        with self.assertRaisesRegex(GeometryError, "unknown"):
            register_scene(model, structure, specs)
        model, structure, specs = shared_fixture()
        model["nodes"][0]["mesh"]["origin_nonzero"] = True
        with self.assertRaisesRegex(GeometryError, "origin"):
            register_scene(model, structure, specs)

    def test_parent_cycle_fails(self):
        model, structure, specs = shared_fixture()
        structure["surfaces"].append({"id": "other"})
        specs["shared"]["parent"] = "other"
        specs["other"] = {**deepcopy(specs["shared"]), "parent": "shared"}
        with self.assertRaisesRegex(GeometryError, "cycle"):
            register_scene(model, structure, specs)

    def test_signed_artifacts_are_not_silently_reused_after_edit(self):
        model, structure, specs = shared_fixture()
        specs["shared"]["fit"]["parameters"]["modified"] = 1
        with self.assertRaisesRegex(ValueError, "integrity"):
            register_scene(model, structure, specs)
        model, structure, specs = shared_fixture()
        scene = register_scene(model, structure, specs)
        scene["parts"]["11"]["material_uv"][0][0] += .01
        with self.assertRaisesRegex(GeometryError, "integrity"):
            evaluate_scene(scene)

    def test_unknown_pose_surface_fails(self):
        scene = register_scene(*shared_fixture())
        with self.assertRaisesRegex(GeometryError, "unknown surface"):
            evaluate_scene(scene, {"missing": {"yaw": 10}})

    def test_repeated_scene_evaluation_is_identical(self):
        scene = register_scene(*shared_fixture())
        a = evaluate_scene(scene, {"shared": {"yaw": -12, "pitch": 7, "roll": 3}})
        b = evaluate_scene(scene, {"shared": {"yaw": -12, "pitch": 7, "roll": 3}})
        self.assertEqual(a, b)

    def test_shared_parts_receive_identical_local_correction_field(self):
        model, structure, specs = shared_fixture()
        fit = specs["shared"]["fit"]
        fit["template"]["correction_rules"] = [{
            "type": "local", "center": [.25, .25], "radius": [.3, .3],
            "direction": [1, 0], "amplitude": .1,
            "driver": {"axis": "roll", "basis": "sin"},
        }]
        fit["content_sha256"] = json_digest({k:v for k,v in fit.items() if k != "content_sha256"})
        scene = register_scene(model, structure, specs)
        result = evaluate_scene(scene, {"shared": {"roll": 30}})
        np.testing.assert_array_equal(result["parts"]["11"]["world_xyz"], result["parts"]["22"]["world_xyz"])
        expected_x = .5*np.cos(np.pi/6)-.5*np.sin(np.pi/6) + .1
        self.assertAlmostEqual(result["parts"]["11"]["world_xy"][0][0], expected_x)

    def test_host_surface_uses_recorded_field_and_requires_provenance(self):
        model, structure, specs = shared_fixture()
        fit = specs["shared"]["fit"]
        fit["template"]["geometry"]["operators"] = [{"type": "host_offset", "offset": .01}]
        fit["host"] = {"mapping": "same_material_uv", "sha256": "synthetic-host-proof"}
        fit["depth"] = [.04]*len(fit["depth"])
        fit["content_sha256"] = json_digest({k:v for k,v in fit.items() if k != "content_sha256"})
        scene = register_scene(model, structure, specs)
        self.assertEqual(scene["parts"]["11"]["depth_method"], "sampled_signed_host_fit")
        np.testing.assert_allclose(np.asarray(scene["parts"]["11"]["rest_world_xyz"])[:,2], .04)
        fit["host"] = None
        fit["content_sha256"] = json_digest({k:v for k,v in fit.items() if k != "content_sha256"})
        with self.assertRaisesRegex(GeometryError, "provenance"):
            register_scene(model, structure, specs)


if __name__ == "__main__":
    unittest.main()
