import copy
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from riglib.landmarks import propose_landmarks


def matrix(x=0, y=0, sx=1, sy=1):
    return [[sx, 0, 0, x], [0, sy, 0, y], [0, 0, 1, 0], [0, 0, 0, 1]]


def part(uuid, name, box, vertices=None, transform=None, enabled=True):
    item = {"uuid": uuid, "name": name, "type": "Part",
            "bounds": {"nominal_world_xy": box},
            "enabled_effective": enabled,
            "nominal_world_matrix": transform if transform is not None else matrix()}
    if vertices is not None:
        item["mesh"] = {"vertices": vertices}
    return item


def bone(uuid, name, x, y, parent=None, observed=True):
    return {"uuid": uuid, "name": name, "type": "DepthBone", "parent": parent,
            "nominal_world_matrix": matrix(x, y) if observed else None}


def template(tid, definitions):
    return {"id": tid, "version": "1.0.0",
            "landmarks": [{"id": rid, "uv": uv, "required": required}
                          for rid, uv, required in definitions]}


FACE = template("face_head", [
    ("eye_a", [.3, .36], True), ("eye_b", [.7, .36], True),
    ("nose_tip", [.5, .55], True), ("chin", [.5, 1], True),
    ("brow_a", [.3, .24], False), ("brow_b", [.7, .24], False),
])
SKIRT = template("skirt", [
    ("waist_a", [0, 0], True), ("waist_b", [1, 0], True),
    ("hem_a", [0, 1], True), ("hem_b", [1, 1], True),
])
ARM = template("arm", [("root", [.5, 0], True), ("joint", [.5, .5], True),
                       ("end", [.5, 1], True), ("bend_side", [.1, .5], False)])
LEG = template("leg", ARM["landmarks"] and [
    ("root", [.5, 0], True), ("joint", [.5, .5], True), ("end", [.5, 1], True)])
EYE = template("eye_opening", [
    ("canthus_a", [0, .5], True), ("canthus_b", [1, .5], True),
    ("upper_center", [.5, .35], True), ("lower_center", [.5, .65], True),
])


def scene(nodes, tid="face_head", box=(0, 0, 100, 100), part_ids=None):
    if part_ids is None:
        part_ids = [n["uuid"] for n in nodes if n["type"] == "Part"]
    observation = {"nodes": nodes, "source": {"metadata_sha256": "synthetic"}}
    structure = {
        "groups": [{"id": "g1", "parts": part_ids, "bounds": list(box) if box is not None else None}],
        "surfaces": [{"id": "surface:g1", "group": "g1", "template_id": tid}],
    }
    return observation, structure


def resolved(output):
    return {row["role"]: row for row in output["surfaces"]["surface:g1"]["landmarks"]}


def face_parts():
    return [
        part(1, "face", [0, 0, 100, 100]),
        part(2, "sclera_R", [15, 25, 40, 45]),
        part(3, "iris_R", [20, 28, 29, 42]),
        part(4, "sclera_L", [62, 25, 86, 45]),
        part(5, "iris_L", [70, 28, 79, 42]),
        part(6, "nose", [47, 50, 53, 60]),
        part(7, "brow_R", [15, 17, 39, 21]),
        part(8, "brow_L", [63, 17, 86, 21]),
    ]


class LandmarkProposalTests(unittest.TestCase):
    def test_face_features_use_geometry_screen_order_not_lr_suffix(self):
        obs, structure = scene(face_parts())
        out = propose_landmarks(obs, structure, [FACE])
        found = resolved(out)
        self.assertEqual(found["eye_a"]["xy"], [27.5, 35])
        self.assertEqual(found["eye_b"]["xy"], [74, 35])
        self.assertEqual(found["eye_a"]["evidence"]["selected_source_uuid"], 2)
        self.assertEqual(found["eye_a"]["state"], "measured_bbox_proxy")
        self.assertEqual(found["nose_tip"]["xy"], [50, 55])
        self.assertEqual(found["brow_a"]["xy"], [27, 19])
        self.assertEqual(out["surfaces"]["surface:g1"]["missing_roles"], [])
        self.assertFalse(out["source_fit_verified"])

    def test_iris_displacement_does_not_move_sclera_center(self):
        nodes = face_parts()
        nodes[2]["bounds"]["nominal_world_xy"] = [28, 28, 38, 43]
        obs, structure = scene(nodes)
        found = resolved(propose_landmarks(obs, structure, {"face_head": FACE}))
        self.assertEqual(found["eye_a"]["xy"], [27.5, 35])
        self.assertEqual(found["eye_a"]["evidence"]["source_uuids"], [2, 3])

    def test_chin_is_explicit_bbox_proxy_not_true_contour(self):
        obs, structure = scene(face_parts())
        chin = resolved(propose_landmarks(obs, structure, [FACE]))["chin"]
        self.assertEqual(chin["xy"], [50, 100])
        self.assertEqual(chin["state"], "measured_bbox_proxy")
        self.assertFalse(chin["evidence"]["boundary_certified"])
        self.assertIn("not_true_contour", chin["evidence"]["method"])

    def test_unseparated_nose_remains_prior_and_missing(self):
        nodes = [n for n in face_parts() if n["uuid"] != 6]
        obs, structure = scene(nodes)
        out = propose_landmarks(obs, structure, [FACE])
        nose = resolved(out)["nose_tip"]
        self.assertEqual(nose["state"], "template_prior")
        self.assertEqual(nose["candidate_state"], "template_prior")
        self.assertFalse(nose["measurement_based"])
        self.assertFalse(nose["evidence"]["measurement"])
        self.assertEqual(nose["evidence"]["source_uuids"], [])
        self.assertIn("nose_tip", out["surfaces"]["surface:g1"]["missing_roles"])

    def test_does_not_borrow_a_feature_from_another_surface(self):
        nodes = face_parts()
        obs, structure = scene(nodes, part_ids=[1, 2, 3, 4, 5, 7, 8])
        out = propose_landmarks(obs, structure, [FACE])
        self.assertIn("nose_tip", out["surfaces"]["surface:g1"]["missing_roles"])
        self.assertEqual(resolved(out)["nose_tip"]["state"], "template_prior")

    def test_disabled_feature_is_not_measurement(self):
        nodes = face_parts()
        nodes[5]["enabled_effective"] = False
        obs, structure = scene(nodes)
        out = propose_landmarks(obs, structure, [FACE])
        self.assertIn("nose_tip", out["surfaces"]["surface:g1"]["missing_roles"])
        self.assertNotIn(6, out["surfaces"]["surface:g1"]["source_uuids"])

    def test_ambiguous_three_eye_clusters_are_not_forced_to_a_pair(self):
        nodes = face_parts() + [part(20, "sclera_extra", [44, 78, 54, 86])]
        obs, structure = scene(nodes)
        out = propose_landmarks(obs, structure, [FACE])
        self.assertIn("eye_a", out["surfaces"]["surface:g1"]["missing_roles"])
        self.assertIn("eye_b", out["surfaces"]["surface:g1"]["missing_roles"])
        self.assertEqual(resolved(out)["eye_a"]["state"], "template_prior")

    def test_eye_white_alias_and_explicit_corner_parts(self):
        nodes = [
            part(1, "eye-white", [10, 30, 90, 70]),
            part(2, "eye_corner_R", [7, 48, 11, 52]),
            part(3, "eye_corner_L", [89, 49, 93, 53]),
        ]
        obs, structure = scene(nodes, "eye_opening")
        out = propose_landmarks(obs, structure, [EYE])
        found = resolved(out)
        self.assertEqual(found["canthus_a"]["xy"], [9, 50])
        self.assertEqual(found["canthus_b"]["xy"], [91, 51])
        self.assertEqual(found["upper_center"]["xy"], [50, 30])
        self.assertEqual(out["surfaces"]["surface:g1"]["missing_roles"], [])

    def test_skirt_uses_transformed_group_mesh_band_points(self):
        nodes = [
            part(1, "panel_a", [20, 30, 80, 230],
                 [[10, 0], [30, 0], [0, 100], [40, 100]], matrix(20, 30, 2, 2)),
            part(2, "panel_b", [100, 30, 140, 234],
                 [[40, 0], [50, 2], [60, 102]], matrix(20, 30, 2, 2)),
        ]
        obs, structure = scene(nodes, "skirt", (20, 30, 140, 234))
        out = propose_landmarks(obs, structure, [SKIRT])
        found = resolved(out)
        self.assertEqual(found["waist_a"]["xy"], [40, 30])
        self.assertEqual(found["waist_b"]["xy"], [120, 34])
        self.assertEqual(found["hem_a"]["xy"], [20, 230])
        self.assertEqual(found["hem_b"]["xy"], [140, 234])
        self.assertEqual(found["waist_b"]["evidence"]["source_uuids"], [2])
        self.assertEqual(found["hem_b"]["state"], "measured_mesh_band_proxy")
        self.assertFalse(found["hem_b"]["evidence"]["boundary_certified"])
        self.assertEqual(out["surfaces"]["surface:g1"]["missing_roles"], [])

    def test_skirt_bbox_without_mesh_is_prior_not_measured_waist(self):
        obs, structure = scene([part(1, "skirt", [0, 0, 100, 100])], "skirt")
        out = propose_landmarks(obs, structure, [SKIRT])
        self.assertEqual(len(out["surfaces"]["surface:g1"]["missing_roles"]), 4)
        self.assertTrue(all(r["state"] == "template_prior" for r in resolved(out).values()))

    def test_arm_bone_chain_uses_spatial_side_not_suffix(self):
        nodes = [part(1, "arm_R", [0, 0, 20, 100]),
                 bone(10, "UpperArm.L", 10, 0),
                 bone(11, "Forearm.L", 11, 50, 10),
                 bone(12, "Hand.L", 10, 100, 11),
                 bone(20, "UpperArm.R", 90, 0),
                 bone(21, "Forearm.R", 89, 50, 20),
                 bone(22, "Hand.R", 90, 100, 21)]
        obs, structure = scene(nodes, "arm", (0, 0, 20, 100))
        out = propose_landmarks(obs, structure, [ARM])
        found = resolved(out)
        self.assertEqual(found["root"]["evidence"]["source_uuids"], [10])
        self.assertEqual(found["joint"]["xy"], [11, 50])
        self.assertEqual(found["end"]["evidence"]["source_uuids"], [12])
        self.assertEqual(found["root"]["state"], "measured_bone_origin_proxy")
        self.assertEqual(out["surfaces"]["surface:g1"]["missing_roles"], [])

    def test_no_bones_means_all_required_joint_roles_missing(self):
        obs, structure = scene([part(1, "arm", [0, 0, 20, 100])], "arm", (0, 0, 20, 100))
        out = propose_landmarks(obs, structure, [ARM])
        self.assertEqual(set(out["surfaces"]["surface:g1"]["missing_roles"]), {"root", "joint", "end"})
        self.assertTrue(all(r["state"] == "template_prior" for r in resolved(out).values()))

    def test_unknown_locked_foot_matrix_does_not_become_a_measured_endpoint(self):
        nodes = [part(1, "leg", [0, 0, 20, 100]),
                 bone(10, "Thigh.L", 10, 0),
                 bone(11, "Shin.L", 10, 50, 10),
                 bone(12, "Foot.L", 10, 100, 11, observed=False)]
        obs, structure = scene(nodes, "leg", (0, 0, 20, 100))
        out = propose_landmarks(obs, structure, [LEG])
        self.assertEqual(resolved(out)["end"]["state"], "template_prior")
        self.assertEqual(out["surfaces"]["surface:g1"]["missing_roles"], ["end"])

    def test_tied_bone_roots_remain_ambiguous(self):
        nodes = [part(1, "arm", [0, 0, 20, 100]),
                 bone(10, "UpperArm.L", 0, 0),
                 bone(20, "UpperArm.R", 20, 0)]
        obs, structure = scene(nodes, "arm", (0, 0, 20, 100))
        out = propose_landmarks(obs, structure, [ARM])
        self.assertEqual(resolved(out)["root"]["state"], "template_prior")

    def test_unknown_surface_template_is_preserved_without_invented_roles(self):
        obs, structure = scene([part(1, "unknown", [0, 0, 100, 100])], None)
        out = propose_landmarks(obs, structure, [FACE])
        record = out["surfaces"]["surface:g1"]
        self.assertIsNone(record["template_id"])
        self.assertEqual(record["landmarks"], [])
        self.assertEqual(record["diagnostics"][0]["kind"], "unresolved_surface_template")

    def test_zero_bounds_produce_missing_instead_of_division_or_fake_geometry(self):
        obs, structure = scene([part(1, "face", [2, 2, 2, 2])], box=(2, 2, 2, 2))
        out = propose_landmarks(obs, structure, [FACE])
        self.assertEqual(out["surfaces"]["surface:g1"]["landmarks"], [])
        self.assertEqual(len(out["surfaces"]["surface:g1"]["missing_roles"]), 4)

    def test_invalid_nonfinite_geometry_is_rejected(self):
        obs, structure = scene(face_parts())
        structure["groups"][0]["bounds"][0] = math.nan
        with self.assertRaisesRegex(ValueError, "finite"):
            propose_landmarks(obs, structure, [FACE])
        obs, structure = scene([part(1, "skirt", [0, 0, 100, 100],
                                     [[0, 0], [math.inf, 1]])], "skirt")
        with self.assertRaisesRegex(ValueError, "finite"):
            propose_landmarks(obs, structure, [SKIRT])

    def test_unknown_source_uuid_and_duplicate_template_are_rejected(self):
        obs, structure = scene(face_parts())
        structure["groups"][0]["parts"].append(999)
        with self.assertRaisesRegex(ValueError, "unknown source"):
            propose_landmarks(obs, structure, [FACE])
        obs, structure = scene(face_parts())
        with self.assertRaisesRegex(ValueError, "duplicate template"):
            propose_landmarks(obs, structure, [FACE, FACE])

    def test_input_order_does_not_change_proposals(self):
        obs, structure = scene(face_parts())
        first = propose_landmarks(obs, structure, [FACE])
        obs["nodes"].reverse()
        structure["groups"][0]["parts"].reverse()
        second = propose_landmarks(obs, structure, [FACE])
        self.assertEqual(first, second)
        json.dumps(first, allow_nan=False)

    def test_proposal_does_not_mutate_inputs(self):
        obs, structure = scene(face_parts())
        before = copy.deepcopy((obs, structure, FACE))
        propose_landmarks(obs, structure, [FACE])
        self.assertEqual(before, (obs, structure, FACE))


if __name__ == "__main__":
    unittest.main()
