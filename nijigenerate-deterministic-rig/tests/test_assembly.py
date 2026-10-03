import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from riglib.assembly import assemble_model, landmark_observation_structure
from riglib.data import json_digest


def fixture():
    return {"source": {"metadata_sha256": "synthetic-independent-fixture"}, "nodes": [
        {"uuid": 0, "type": "Node", "name": "root", "parent": None},
        {"uuid": 1, "type": "Part", "name": "face", "parent": 0, "bounds": [20, 0, 80, 50]},
        {"uuid": 2, "type": "Part", "name": "iris_a", "parent": 0, "bounds": [30, 15, 35, 20]},
        {"uuid": 3, "type": "Part", "name": "nose", "parent": 0, "bounds": [48, 24, 52, 28]},
        {"uuid": 4, "type": "Part", "name": "body", "parent": 0, "bounds": [20, 55, 80, 120]},
        {"uuid": 5, "type": "Part", "name": "corset", "parent": 0, "bounds": [15, 75, 85, 110]},
    ]}


def graph_projection(result):
    return {"owners": [o["id"] for o in result["owners"]],
            "charts": [(c["id"], c["owner"], c["usages"]) for c in result["charts"]],
            "support": result["support_relations"]}


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((ROOT / "structures" / "material-roles.json").read_text(encoding="utf-8"))

    def test_flat_parts_share_head_and_body(self):
        result = assemble_model(fixture(), self.spec)
        self.assertEqual(result["coverage"]["owners"], 2)
        self.assertEqual(result["coverage"]["charts"], 2)
        head = next(c for c in result["charts"] if c["id"] == "head/face")
        self.assertEqual(set(head["parts"]), {1, 2, 3})
        core = landmark_observation_structure(result)
        self.assertEqual(next(g for g in core["groups"] if g["id"] == "head/face")["parts"], head["parts"])

    def test_split_material_does_not_add_structure_or_required_roles(self):
        original = fixture()
        split = copy.deepcopy(original)
        split["nodes"][1]["bounds"] = [20, 0, 50, 50]
        split["nodes"].append({"uuid": 20, "type": "Part", "name": "face", "parent": 0, "bounds": [50, 0, 80, 50]})
        a, b = assemble_model(original, self.spec), assemble_model(split, self.spec)
        self.assertEqual(graph_projection(a), graph_projection(b))
        self.assertEqual([c["coverage_bounds"] for c in a["charts"]], [c["coverage_bounds"] for c in b["charts"]])
        self.assertEqual([s["template_id"] for s in landmark_observation_structure(a)["surfaces"]],
                         [s["template_id"] for s in landmark_observation_structure(b)["surfaces"]])

    def test_anonymous_renumbered_materials_use_semantic_evidence(self):
        original = fixture()
        anonymous = copy.deepcopy(original)
        role_by_old_id = {1: "face", 2: "face_feature", 3: "face_feature", 4: "torso", 5: "bodice"}
        annotations = []
        for node in anonymous["nodes"]:
            old = node["uuid"]
            node["name"] = "opaque-" + str(1000 + old)
            node["uuid"] += 1000
            if node["parent"] is not None:
                node["parent"] += 1000
            if node["type"] == "Part":
                annotations.append({"part": node["uuid"], "role": role_by_old_id[old], "provenance": "visual_observation"})
        evidence = {"schema_version": "rig-semantic-evidence/1", "observation_sha256": json_digest(anonymous), "materials": annotations}
        self.assertEqual(graph_projection(assemble_model(original, self.spec)),
                         graph_projection(assemble_model(anonymous, self.spec, evidence)))

    def test_reordered_nodes_are_deterministic_and_source_unchanged(self):
        obs = fixture()
        before = copy.deepcopy(obs)
        a = assemble_model(obs, self.spec)
        self.assertEqual(obs, before)
        obs["nodes"].reverse()
        b = assemble_model(obs, self.spec)
        self.assertEqual(graph_projection(a), graph_projection(b))
        self.assertEqual(a["materials"], b["materials"])
        self.assertEqual(assemble_model(before, self.spec), a)

    def test_native_carrier_does_not_change_physical_owners(self):
        obs = fixture()
        a = assemble_model(obs, self.spec)
        obs["nodes"].append({"uuid": 99, "type": "GridDeformer", "name": "unrelated carrier", "parent": 0})
        for n in obs["nodes"]:
            if n["type"] == "Part":
                n["parent"] = 99
        self.assertEqual(graph_projection(a), graph_projection(assemble_model(obs, self.spec)))

    def test_covering_does_not_certify_hidden_torso(self):
        result = assemble_model(fixture(), self.spec)
        torso = next(o for o in result["owners"] if o["id"] == "torso")
        self.assertNotEqual(torso["material_coverage_bounds"], torso["visible_anatomy_bounds"])
        self.assertIsNone(torso["anatomical_frame"])
        self.assertIsNone(torso["volume_fit"])

    def test_large_appendage_does_not_expand_anatomy_evidence(self):
        obs = fixture()
        original = assemble_model(obs, self.spec)
        obs["nodes"].append({"uuid": 50, "type": "Part", "name": "tail", "parent": 0, "bounds": [-10000, 0, 10000, 50000]})
        result = assemble_model(obs, self.spec)
        self.assertEqual([o["visible_anatomy_bounds"] for o in original["owners"]],
                         [o["visible_anatomy_bounds"] for o in result["owners"]])

    def test_decoration_has_receiver_owner_and_no_anatomy(self):
        obs = fixture()
        obs["nodes"].append({"uuid": 50, "type": "Part", "name": "shadow_hair_face", "parent": 0, "bounds": [0, 0, 100, 100]})
        result = assemble_model(obs, self.spec)
        self.assertEqual(result["coverage"]["owners"], 2)
        head = next(o for o in result["owners"] if o["id"] == "head")
        self.assertNotIn(50, head["anatomy_evidence_parts"])
        self.assertEqual(next(m for m in result["materials"] if m["part"] == 50)["owner"], "head")

    def test_disabled_subtree_is_excluded(self):
        obs = fixture()
        obs["nodes"][0]["enabled_local"] = False
        result = assemble_model(obs, self.spec)
        self.assertEqual(result["coverage"]["active_parts"], 0)
        self.assertEqual(len(result["excluded_parts"]), 5)

    def test_unknown_material_remains_unassigned(self):
        obs = fixture()
        obs["nodes"][1]["name"] = "opaque"
        result = assemble_model(obs, self.spec)
        self.assertEqual(result["coverage"]["unassigned_parts"], 1)
        self.assertFalse(result["fit_ready"])
        self.assertEqual(result["status"], "assembly_proposal")

    def test_rejects_stale_semantic_evidence(self):
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            assemble_model(fixture(), self.spec, {"schema_version": "rig-semantic-evidence/1", "observation_sha256": "wrong"})

    def test_sides_are_opaque_source_tags(self):
        obs = fixture()
        obs["nodes"].append({"uuid": 50, "type": "Part", "name": "opaque", "parent": 0, "bounds": [0, 50, 10, 110]})
        evidence = {"schema_version": "rig-semantic-evidence/1", "observation_sha256": json_digest(obs),
                    "materials": [{"part": 50, "role": "arm", "side_tag": "near", "provenance": "source_annotation"}]}
        result = assemble_model(obs, self.spec, evidence)
        self.assertIn("arm:near", [o["id"] for o in result["owners"]])


if __name__ == "__main__":
    unittest.main()
