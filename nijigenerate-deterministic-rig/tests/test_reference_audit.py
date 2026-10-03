import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_references import summarize
from riglib.landmarks import propose_landmarks
from riglib.structure import infer_structure


class ReferenceAccountingTests(unittest.TestCase):
    def fixture(self):
        observation = {"source": {"metadata_sha256": "synthetic"}, "parameters": [], "nodes": [
            {"uuid": 0, "name": "root", "type": "Node", "parent": None},
            {"uuid": 1, "name": "body", "type": "GridDeformer", "parent": 0},
            {"uuid": 2, "name": "paint", "type": "Part", "parent": 1, "bounds": [0, 0, 1, 1]},
        ]}
        spec = {"id": "test", "primary_slots": [{"id": "body", "template_id": "torso", "name_patterns": ["body"]}]}
        structure = infer_structure(observation, spec)
        catalog = {"torso": {"id": "torso", "landmarks": [{"id": "anchor", "uv": [.5, .5], "required": True}]}}
        landmarks = propose_landmarks(observation, structure, catalog)
        return observation, structure, landmarks

    def test_proposal_with_unresolved_role_is_accounted_without_fit_claim(self):
        result = summarize(*self.fixture())
        self.assertTrue(result["checks_passed"])
        self.assertEqual(result["counts"]["missing_required_roles"], 1)
        self.assertEqual(result["counts"]["landmark_states"], {"template_prior": 1})

    def test_duplicate_part_assignment_fails_accounting(self):
        observation, structure, landmarks = self.fixture()
        structure["part_assignments"].append(copy.deepcopy(structure["part_assignments"][0]))
        result = summarize(observation, structure, landmarks)
        self.assertFalse(result["checks_passed"])
        self.assertFalse(result["checks"]["every_active_part_owned_once"])

    def test_prior_relabelled_as_measurement_fails_accounting(self):
        observation, structure, landmarks = self.fixture()
        next(iter(landmarks["surfaces"].values()))["landmarks"][0]["measurement_based"] = True
        self.assertFalse(summarize(observation, structure, landmarks)["checks_passed"])

    def test_shared_grouping_bug_cannot_hide_missing_enabled_part(self):
        observation, structure, landmarks = self.fixture()
        # Simulate both grouping and inference losing a source Part.
        structure["part_assignments"] = []
        with patch("audit_references.observe_groups", return_value=([], [])):
            result = summarize(observation, structure, landmarks)
        self.assertFalse(result["checks"]["every_active_part_owned_once"])
        self.assertFalse(result["checks"]["observation_groups_cover_active_parts"])
        self.assertFalse(result["checks"]["excluded_parts_partition_source"])

    def test_disabled_part_must_be_explicitly_excluded(self):
        observation, structure, landmarks = self.fixture()
        observation["nodes"].append({"uuid": 3, "type": "Part", "parent": 1, "name": "reference",
                                     "enabled_effective": False, "bounds": [0, 0, 1, 1]})
        self.assertFalse(summarize(observation, structure, landmarks)["checks_passed"])
        structure["excluded_parts"] = [{"part": 3, "reason": "disabled_in_source"}]
        self.assertTrue(summarize(observation, structure, landmarks)["checks_passed"])


if __name__ == "__main__":
    unittest.main()
