"""Numerical invariants for the shared semantic-grid kernel; no live app use."""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from riglib.geometry import (
    GeometryError, apply_local_corrections, evaluate_depth, fit_guide_grid,
    inverse_grid, make_uv_grid, rotate_points, rotate_project, rotation_matrix,
    sample_grid, validate_grid,
)


class GuideGridTests(unittest.TestCase):
    def test_neutral_bounds_with_nonuniform_lines(self):
        u, v = [0, .2, 1], [0, .7, 1]
        actual = fit_guide_grid(u, v, [10, 20, 210, 120], [])
        expected = make_uv_grid(u, v)*[200, 100]+[10, 20]
        np.testing.assert_array_equal(actual, expected)
        self.assertTrue(validate_grid(actual)["local_orientation_preserved"])

    def test_tps_affine_fit_reproduces_neutral_landmarks(self):
        material = make_uv_grid([0, .5, 1], [0, .5, 1])
        matrix = np.array([[1.2, .3], [-.1, 1.1]])
        targets = material @ matrix.T + [8, 5]
        landmarks = [{"uv": material[r, c].tolist(), "xy": targets[r, c].tolist()}
                     for r, c in [(0, 0), (0, 2), (2, 0), (2, 2)]]
        fit = fit_guide_grid([0, .5, 1], [0, .5, 1], [0, 0, 1, 1], landmarks)
        np.testing.assert_allclose(fit, targets, atol=1e-13)

    def test_tps_landmark_order_does_not_change_output(self):
        landmarks = [
            {"uv": [0, 0], "xy": [0, 0]}, {"uv": [1, 0], "xy": [2, 0]},
            {"uv": [0, 1], "xy": [0, 2]}, {"uv": [1, 1], "xy": [2, 2]},
            {"uv": [.5, .5], "xy": [1.1, 1]},
        ]
        a = fit_guide_grid([0, .5, 1], [0, .5, 1], [0, 0, 2, 2], landmarks)
        b = fit_guide_grid([0, .5, 1], [0, .5, 1], [0, 0, 2, 2], list(reversed(landmarks)))
        np.testing.assert_array_equal(a, b)
        np.testing.assert_allclose(a[1, 1], [1.1, 1], atol=1e-13)

    def test_single_landmark_uses_neutral_displacement(self):
        actual = fit_guide_grid([0, .5, 1], [0, .5, 1], [0, 0, 2, 4],
                                [{"uv": [.5, .5], "xy": [11, -3]}])
        expected = make_uv_grid([0, .5, 1], [0, .5, 1])*[2, 4]+[10, -5]
        np.testing.assert_allclose(actual, expected)

    def test_idw_exact_hit_and_finite_elsewhere(self):
        actual = fit_guide_grid([0, .5, 1], [0, .5, 1], [0, 0, 1, 1],
                                [{"uv": [0, 0], "xy": [.05, 0]},
                                 {"uv": [1, 1], "xy": [1, 1.05]}], method="idw")
        np.testing.assert_array_equal(actual[0, 0], [.05, 0])
        np.testing.assert_array_equal(actual[-1, -1], [1, 1.05])
        self.assertTrue(np.all(np.isfinite(actual)))

    def test_conflicting_duplicate_landmarks_rejected(self):
        with self.assertRaisesRegex(GeometryError, "conflicting"):
            fit_guide_grid([0, 1], [0, 1], [0, 0, 1, 1],
                           [{"uv": [0, 0], "xy": [0, 0]},
                            {"uv": [0, 0], "xy": [1, 0]}])

    def test_reflection_and_fold_are_rejected(self):
        with self.assertRaisesRegex(GeometryError, "folded"):
            fit_guide_grid([0, 1], [0, 1], [0, 0, 1, 1],
                           [{"uv": [0, 0], "xy": [1, 0]},
                            {"uv": [1, 0], "xy": [0, 0]},
                            {"uv": [0, 1], "xy": [1, 1]}])
        with self.assertRaisesRegex(GeometryError, "folded"):
            validate_grid([[[0, 0], [1, 0]], [[0, 1], [-.1, .9]]])

    def test_nonfinite_or_invalid_guide_inputs_rejected(self):
        for u in ([0, 0, 1], [0, .5], [0, math.nan, 1]):
            with self.subTest(u=u), self.assertRaises(GeometryError):
                make_uv_grid(u, [0, 1])
        with self.assertRaises(GeometryError):
            fit_guide_grid([0, 1], [0, 1], [0, 0, 0, 1], [])

    def test_nonuniform_bilinear_sampling_matches_affine_field(self):
        u, v = [0, .1, .6, 1], [0, .8, 1]
        mesh = make_uv_grid(u, v)
        values = mesh[..., 0]*2 + mesh[..., 1]*3 + 5
        query = np.array([[0, 0], [1, 1], [.35, .4], [.8, .95]])
        actual = sample_grid(values, u, v, query)
        np.testing.assert_allclose(actual, 2*query[:, 0]+3*query[:, 1]+5)
        with self.assertRaises(GeometryError):
            sample_grid(values, u, v, [[1.1, .5]])

    def test_inverse_roundtrip_of_nonrectangular_valid_grid(self):
        u, v = [0, .5, 1], [0, .4, 1]
        grid = make_uv_grid(u, v)
        grid[1, 1] += [.08, -.02]
        query = np.array([[.1, .2], [.8, .1], [.45, .6], [.7, .8], [1, 1], [.5, .4]])
        xy = sample_grid(grid, u, v, query)
        recovered = inverse_grid(grid, u, v, xy)
        np.testing.assert_allclose(recovered, query, atol=2e-9)

    def test_inverse_outside_fails_instead_of_clipping(self):
        with self.assertRaisesRegex(GeometryError, "outside"):
            inverse_grid(make_uv_grid([0, 1], [0, 1]), [0, 1], [0, 1], [[2, .5]])


class DepthFieldTests(unittest.TestCase):
    def test_ellipse_section_edges_center_and_profile(self):
        query = [[0, 0], [.5, 0], [1, 0], [.5, 1], [.5, .5]]
        actual = evaluate_depth(query, [{"type": "section_surface", "depth": "d",
                                         "depth_profile": [[0, 1], [1, 2]]}], {"d": .2})
        np.testing.assert_allclose(actual, [0, .2, 0, .4, .3])

    def test_angular_flared_front_and_back_sign(self):
        front = evaluate_depth([[0, .5], [.5, .5], [1, .5]],
                               [{"type": "section_surface", "cross_section": "angular",
                                 "depth": .3, "theta_degrees": [-90, 90]}])
        back = evaluate_depth([[.5, .5]], [
            {"type": "flared_shell", "cross_section": "angular",
             "depth": .3, "theta_degrees": [90, 270]}])
        np.testing.assert_allclose(front, [0, .3, 0], atol=1e-16)
        np.testing.assert_allclose(back, [-.3], atol=1e-16)

    def test_compact_relief_exact_zero_outside_and_at_support_boundary(self):
        actual = evaluate_depth([[.5, .5], [.75, .5], [1, 1]], [
            {"type": "compact_relief", "center": [.5, .5],
             "radius": [.25, .4], "height": .1}])
        np.testing.assert_array_equal(actual, [.1, 0, 0])

    def test_rotated_anisotropic_relief_changes_support(self):
        query = [[.5, .7]]
        op = {"type": "compact_relief", "radius": [.1, .4], "height": 1}
        self.assertGreater(evaluate_depth(query, [op])[0], 0)
        self.assertEqual(evaluate_depth(query, [{**op, "rotation_degrees": 90}])[0], 0)

    def test_swept_section_profiles(self):
        actual = evaluate_depth([[.5, 0], [.7, 1]], [
            {"type": "swept_surface", "depth": .2,
             "center_u_profile": [[0, .5], [1, .7]],
             "radius_u_profile": [[0, .3], [1, .2]],
             "center_depth_profile": [[0, 0], [1, .1]],
             "depth_profile": [[0, 1], [1, .5]]}])
        np.testing.assert_allclose(actual, [.2, .2])

    def test_composed_host_and_relief_do_not_reinvent_host(self):
        query = [[.5, .5], [0, 0]]
        actual = evaluate_depth(query, [
            {"type": "host_offset", "offset": .01},
            {"type": "compact_relief", "height": .03, "radius": [.2, .2]},
        ], host_depth=[.2, .1])
        np.testing.assert_allclose(actual, [.24, .11])
        with self.assertRaisesRegex(GeometryError, "host_depth"):
            evaluate_depth(query, [{"type": "host_offset", "offset": .01}])

    def test_bend_and_wave_anchor_fade(self):
        bend = evaluate_depth([[0, 0], [1, .5], [1, 1]],
                              [{"type": "bend", "amplitude": .4, "power": 2}])
        np.testing.assert_allclose(bend, [0, .1, .4])
        wave = evaluate_depth([[.25, 0], [.25, 1], [.75, 1]], [
            {"type": "wave", "amplitude": .2, "frequency": 1, "fade_axis": "v"}])
        np.testing.assert_allclose(wave, [0, .2, -.2], atol=1e-16)

    def test_ribbon_chart_separation(self):
        result = evaluate_depth([[.2, .5], [.8, .5]], [{
            "type": "ribbon_network", "ribbons": [
                {"support": [0, 0, .4, 1], "depth": .1},
                {"support": [.6, 0, 1, 1], "depth": .2},
            ]}])
        np.testing.assert_allclose(result, [.1, .2])

    def test_incompatible_ribbon_overlap_is_not_averaged(self):
        with self.assertRaisesRegex(GeometryError, "overlap"):
            evaluate_depth([[.5, .5]], [{
                "type": "ribbon_network", "ribbons": [
                    {"support": [0, 0, .7, 1], "depth": .1},
                    {"support": [.3, 0, 1, 1], "depth": .2},
                ]}])

    def test_all_typed_operator_aliases_execute(self):
        for kind in ["section", "flared_shell", "swept_tube", "ribbon"]:
            with self.subTest(kind=kind):
                np.testing.assert_allclose(
                    evaluate_depth([[.5, .5]], [{"type": kind, "depth": .1}]), [.1])

    def test_invalid_operator_parameter_or_profile_rejected(self):
        bad = [
            {"type": "not_implemented"},
            {"type": "section_surface", "depth": "missing"},
            {"type": "section_surface", "radius_u": 0},
            {"type": "compact_relief", "height": 1, "radius": [0, 1]},
            {"type": "section_surface", "depth_profile": [[1, 1], [0, 2]]},
            {"type": "constant", "value": math.nan},
        ]
        for op in bad:
            with self.subTest(op=op), self.assertRaises(GeometryError):
                evaluate_depth([[.5, .5]], [op])

    def test_depth_queries_cannot_contain_nan_or_leave_chart(self):
        for uv in ([[math.nan, 0]], [[0, -1]], [[1, 2]], [[1, 2, 3]]):
            with self.subTest(uv=uv), self.assertRaises(GeometryError):
                evaluate_depth(uv, [])

    def test_unknown_operator_fields_cannot_be_silently_ignored(self):
        with self.assertRaisesRegex(GeometryError, "unknown"):
            evaluate_depth([[.5, .5]], [{"type": "section_surface", "deph": .9}])
        with self.assertRaisesRegex(GeometryError, "unknown"):
            evaluate_depth([[.5, .5]], [{"type": "ribbon_network", "ribbons": [
                {"depth": .1, "twist": 45}]}])


class RotationTests(unittest.TestCase):
    def test_nonzero_neutral_preserves_every_coordinate_exactly(self):
        points = np.array([[.1, -.3, .7], [50, -2, 10]])
        pose = {"yaw": 23, "pitch": -9, "roll": 12}
        result = rotate_points(points, pose, [3, 1, 2], pose)
        np.testing.assert_array_equal(result, points)
        np.testing.assert_array_equal(rotate_project(points, pose, neutral_angles=pose), points[:, :2])

    def test_yaw_direction_and_orthographic_projection(self):
        actual = rotate_points([[1, 0, 0], [0, 0, 1]], {"yaw": 90})
        np.testing.assert_allclose(actual, [[0, 0, -1], [1, 0, 0]], atol=1e-15)
        np.testing.assert_allclose(rotate_project([[0, 0, 1]], {"yaw": 90}), [[1, 0]], atol=1e-15)

    def test_relative_rotation_preserves_distances_to_pivot(self):
        points = np.random.default_rng(41).normal(size=(25, 3))
        pivot = np.array([.3, -.7, 1])
        actual = rotate_points(points, {"yaw": -27, "pitch": 14, "roll": 8}, pivot,
                               {"yaw": 12, "pitch": -4, "roll": 19})
        np.testing.assert_allclose(np.linalg.norm(actual-pivot, axis=1),
                                   np.linalg.norm(points-pivot, axis=1), atol=2e-15)

    def test_rotation_matrix_is_proper_orthogonal(self):
        matrix = rotation_matrix({"yaw": 30, "pitch": -20, "roll": 17})
        np.testing.assert_allclose(matrix.T @ matrix, np.eye(3), atol=3e-16)
        self.assertAlmostEqual(np.linalg.det(matrix), 1)

    def test_nonfinite_and_unsupported_pose_axis_rejected(self):
        with self.assertRaises(GeometryError):
            rotate_project([[0, 0, 0]], {"yaw": math.inf})
        with self.assertRaises(GeometryError):
            rotate_project([[0, 0, 0]], {"closure": 1})


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.rule = {
            "type": "local", "center": [.5, .5], "radius": [.5, .5],
            "direction": [2, 0], "amplitude": "a",
            "driver": {"axis": "yaw", "basis": "sin"},
        }

    def test_scaled_amplitude_and_support_boundaries(self):
        uv = np.array([[.5, .5], [0, .5], [1, .5], [.5, 0], [.5, 1]])
        xy = uv*100
        out = apply_local_corrections(xy, uv, {"yaw": 90}, [self.rule], {"a": .1}, scale=100)
        np.testing.assert_array_equal(out[1:], xy[1:])
        np.testing.assert_allclose(out[0], xy[0]+[10, 0])

    def test_nonzero_neutral_pose_has_zero_correction(self):
        uv = np.array([[.5, .5], [.3, .6]])
        xy = uv*71.3
        q0 = {"yaw": 17, "pitch": 11}
        out = apply_local_corrections(xy, uv, q0, [self.rule], {"a": .2}, q0, scale=200)
        np.testing.assert_array_equal(out, xy)

    def test_positive_sin_and_driver_sign_select_sides(self):
        right = {**self.rule, "driver": {"axis": "yaw", "basis": "positive_sin"}}
        left = {**self.rule, "driver": {"axis": "yaw", "basis": "positive_sin", "scale": -1}}
        a = apply_local_corrections([[0, 0]], [[.5, .5]], {"yaw": -90}, [right], {"a": 1})
        b = apply_local_corrections([[0, 0]], [[.5, .5]], {"yaw": -90}, [left], {"a": 1})
        np.testing.assert_array_equal(a, [[0, 0]])
        np.testing.assert_allclose(b, [[1, 0]])

    def test_pinned_domain_boundary_is_zero_inside_wide_support(self):
        rule = {**self.rule, "radius": [2, 2], "pin_edges": ["u0"]}
        actual = apply_local_corrections([[0, 0]], [[0, .5]], {"yaw": 90}, [rule], {"a": 1})
        np.testing.assert_array_equal(actual, [[0, 0]])

    def test_each_pose_basis_executes_with_neutral_subtraction(self):
        for basis in ("sin", "sin2", "linear", "positive_sin"):
            rule = {**self.rule, "driver": {"axis": "pitch", "basis": basis}}
            with self.subTest(basis=basis):
                actual = apply_local_corrections(
                    [[0, 0]], [[.5, .5]], {"pitch": 30}, [rule], {"a": 1})
                self.assertGreater(actual[0, 0], 0)
                self.assertEqual(actual[0, 1], 0)

    def test_invalid_rules_rejected_even_at_neutral(self):
        bad = [
            {**self.rule, "direction": [0, 0]},
            {**self.rule, "driver": {"basis": "invented"}},
            {**self.rule, "radius": [-1, 1]},
            {**self.rule, "pin_edges": ["x0"]},
        ]
        for rule in bad:
            with self.subTest(rule=rule), self.assertRaises(GeometryError):
                apply_local_corrections([[0, 0]], [[.5, .5]], {}, [rule], {"a": 1})

    def test_dimension_and_scale_mismatch_fail(self):
        with self.assertRaises(GeometryError):
            apply_local_corrections([[0, 0]], [[.5, .5], [0, 0]], {}, [], {})
        with self.assertRaises(GeometryError):
            apply_local_corrections([[0, 0]], [[.5, .5]], {}, [], {}, scale=0)

    def test_unknown_correction_fields_and_malformed_pins_fail(self):
        for patch in ({"amplitdue": .1}, {"driver": {"basis": "sin", "time": 2}},
                      {"pin_edges": [{"u0": True}]}):
            with self.subTest(patch=patch), self.assertRaises(GeometryError):
                apply_local_corrections([[0, 0]], [[.5, .5]], {},
                                        [{**self.rule, **patch}], {"a": 1})


if __name__ == "__main__":
    unittest.main()
