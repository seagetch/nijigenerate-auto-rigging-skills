import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from riglib.structure import infer_structure, observe_groups


def fixture():
    nodes = [{"uuid":0,"type":"Node","name":"root","parent":None}]
    for i,(name,box) in enumerate((("surface a",[40,0,60,25]),("surface b",[30,30,70,75])),1):
        nodes.extend([{"uuid":i,"type":"GridDeformer","name":name,"parent":0},
                      {"uuid":i+10,"type":"Part","name":"paint","parent":i,
                       "bounds":{"nominal_world_xy":box}}])
    spec = {"id":"anonymous","primary_slots":[
        {"id":"upper","template_id":"face_head","name_patterns":[],"position":[.5,.15],"size":[.5,.3]},
        {"id":"lower","template_id":"torso","name_patterns":[],"position":[.5,.7],"size":[1,.6]}],
        "relations":[{"a":"upper","b":"lower","kind":"above","weight":100}],
        "secondary_rules":[],"ambiguity_margin":.1,"beam_width":64}
    return {"source":{"metadata_sha256":"fixture"},"nodes":nodes},spec


def shared_carrier_fixture():
    observation = {"source":{"metadata_sha256":"shared-carrier"},"nodes":[
        {"uuid":0,"type":"Node","name":"root","parent":None},
        {"uuid":100,"type":"GridDeformer","name":"body","parent":0},
        {"uuid":1,"type":"Part","name":"torso","parent":100,"bounds":[0,20,100,100]},
        {"uuid":2,"type":"Part","name":"neck","parent":1,"bounds":[40,0,60,20]},
    ]}
    specification = {"id":"shared-carrier-test","primary_slots":[
        {"id":"torso","template_id":"torso","name_patterns":["body|torso"],
         "position":[.5,.6],"size":[1,.8]},
        {"id":"neck","template_id":"neck","name_patterns":["neck"],
         "position":[.5,.1],"size":[.2,.2]}],"secondary_rules":[]}
    return observation,specification


def scaffold_fixture():
    observation,specification=fixture()
    specification["normalization"]={"coordinate_system":"primary_scaffold_hypotheses",
        "required_slots":["upper","lower"],"hypothesis_limit":3,"iterations":2}
    return observation,specification


class StructureTests(unittest.TestCase):
    def test_whole_graph_geometry_assigns_anonymous_groups(self):
        obs,spec=fixture()
        out=infer_structure(obs,spec)
        self.assertEqual(out["hypotheses"][0]["assignment"],{"upper":"1","lower":"2"})
        self.assertEqual(out["coverage"]["active_parts"],2)

    def test_many_parts_share_one_surface_and_exclusion_inherits(self):
        obs,spec=fixture()
        obs["nodes"].append({"uuid":50,"type":"Part","name":"outline","parent":1,
                             "bounds":{"nominal_world_xy":[40,0,60,25]}})
        obs["nodes"][3]["enabled_local"]=False
        out=infer_structure(obs,spec)
        self.assertEqual(len({p["surface"] for p in out["part_assignments"]}),1)
        self.assertEqual(out["coverage"]["active_parts"],2)
        self.assertEqual(len(out["excluded_parts"]),1)

    def test_node_order_does_not_change_proposal(self):
        obs,spec=fixture()
        a=infer_structure(obs,spec)
        obs["nodes"].reverse()
        b=infer_structure(obs,spec)
        self.assertEqual(a,b)

    def test_conflicting_structural_hints_are_rejected(self):
        obs,spec=fixture()
        with self.assertRaises(ValueError):
            infer_structure(obs,spec,{"primary_assignments":{"upper":"1","lower":"1"}})

    def test_missing_geometry_is_not_fabricated(self):
        obs,spec=fixture()
        for node in obs["nodes"]:
            node.pop("bounds",None)
        out=infer_structure(obs,spec)
        self.assertGreater(len(out["questions"]),0)
        self.assertTrue(all(g["bounds"] is None for g in out["groups"]))

    def test_duplicate_uuid_and_cycles_fail(self):
        obs,_=fixture()
        obs["nodes"].append(copy.deepcopy(obs["nodes"][0]))
        with self.assertRaises(ValueError): observe_groups(obs)
        obs,_=fixture();obs["nodes"][0]["parent"]=1
        with self.assertRaises(ValueError): observe_groups(obs)

    def test_semantic_subgroup_splits_neck_from_shared_torso_carrier(self):
        obs,spec=shared_carrier_fixture()
        out=infer_structure(obs,spec)
        self.assertEqual(len(out["observation_seeds"]),1)
        selected=out["hypotheses"][0]["assignment"]
        candidates={group["id"]:group for group in out["group_candidates"]}
        self.assertEqual(candidates[selected["torso"]]["parts"],[1])
        self.assertEqual(candidates[selected["neck"]]["parts"],[2])
        self.assertEqual(len(out["surfaces"]),2)
        self.assertTrue(out["coverage"]["unique_part_ownership"])
        self.assertEqual(out["coverage"]["active_parts"],2)

    def test_multiple_carriers_can_merge_into_one_shared_surface(self):
        obs={"source":{},"nodes":[
            {"uuid":0,"type":"Node","name":"root","parent":None},
            {"uuid":10,"type":"GridDeformer","name":"body upper","parent":0},
            {"uuid":11,"type":"Part","name":"paint a","parent":10,"bounds":[0,0,100,50]},
            {"uuid":20,"type":"GridDeformer","name":"body lower","parent":0},
            {"uuid":21,"type":"Part","name":"paint b","parent":20,"bounds":[0,50,100,100]},
        ]}
        spec={"id":"union-test","primary_slots":[
            {"id":"body","template_id":"torso","name_patterns":["body"],
             "position":[.5,.5],"size":[1,1]}],"secondary_rules":[]}
        out=infer_structure(obs,spec)
        self.assertEqual(len(out["observation_seeds"]),2)
        self.assertEqual(len(out["surfaces"]),1)
        self.assertEqual(out["groups"][0]["candidate_kind"],"same_role_seed_union")
        self.assertEqual(out["groups"][0]["parts"],[11,21])
        self.assertEqual(len({row["surface"] for row in out["part_assignments"]}),1)

    def test_overlapping_candidate_hints_are_rejected(self):
        obs,spec=shared_carrier_fixture()
        with self.assertRaisesRegex(ValueError,"overlapping"):
            infer_structure(obs,spec,{"primary_assignments":{"torso":"100","neck":"native:2"}})

    def test_every_global_hypothesis_has_disjoint_part_ownership(self):
        obs,spec=shared_carrier_fixture()
        out=infer_structure(obs,spec)
        candidates={g["id"]:set(g["parts"]) for g in out["group_candidates"]}
        for hypothesis in out["hypotheses"]:
            owned=set()
            for gid in hypothesis["assignment"].values():
                if gid is None: continue
                self.assertFalse(owned & candidates[gid])
                owned |= candidates[gid]

    def test_candidate_budget_dedup_and_97_part_coverage(self):
        obs={"source":{},"nodes":[
            {"uuid":0,"type":"Node","name":"root","parent":None},
            {"uuid":1000,"type":"GridDeformer","name":"body","parent":0}]}
        obs["nodes"].extend({"uuid":i+1,"type":"Part","name":"segment "+str(i),
                             "parent":1000,"bounds":[i,0,i+1,10]} for i in range(97))
        spec={"id":"bounded","max_group_candidates":32,
              "primary_slots":[{"id":"body","template_id":"torso","name_patterns":["body"]}],
              "secondary_rules":[{"id":"piece","template_id":"surface_layer",
                                   "name_patterns":["segment"],"kind":"shared_offset","host_slots":["body"]}]}
        out=infer_structure(obs,spec)
        self.assertLessEqual(len(out["group_candidates"]),32)
        self.assertGreater(out["candidate_generation"]["dropped_at_limit"],0)
        memberships=[tuple(sorted(g["parts"])) for g in out["group_candidates"]]
        self.assertEqual(len(memberships),len(set(memberships)))
        assigned=[row["part"] for row in out["part_assignments"]]
        self.assertEqual(len(assigned),97)
        self.assertEqual(len(set(assigned)),97)
        self.assertEqual(set(assigned),set(range(1,98)))

    def test_required_host_absent_is_counted_and_questioned(self):
        obs={"source":{},"nodes":[
            {"uuid":0,"type":"Node","name":"root","parent":None},
            {"uuid":10,"type":"GridDeformer","name":"frill","parent":0},
            {"uuid":11,"type":"Part","name":"paint","parent":10,"bounds":[0,0,1,1]}]}
        spec={"id":"no-host","missing_slot_cost":1,
              "primary_slots":[{"id":"body","template_id":"torso","name_patterns":["^body$"],
                                 "position":[1000,1000],"size":[1,1]}],
              "secondary_rules":[{"id":"frill","template_id":"frill","name_patterns":["frill"],
                                   "kind":"shared_offset","host_slots":["body"]}]}
        out=infer_structure(obs,spec)
        self.assertTrue(any(q["kind"]=="attachment_host_missing" for q in out["questions"]))
        self.assertEqual(out["coverage"]["unresolved_attachments"],1)
        self.assertEqual(out["coverage"]["unresolved_surfaces"],1)
        self.assertEqual(len(out["connections"]),1)
        self.assertIsNone(out["connections"][0]["host"])

    def test_ambiguous_host_is_counted_not_just_unknown_template(self):
        obs={"source":{},"nodes":[{"uuid":0,"type":"Node","name":"root","parent":None}]}
        for i,name in enumerate(("host a","host b","frill"),1):
            obs["nodes"].extend([{"uuid":i,"type":"GridDeformer","name":name,"parent":0},
                                 {"uuid":i+10,"type":"Part","name":"paint","parent":i,"bounds":[0,0,1,1]}])
        spec={"id":"ambiguous-host","primary_slots":[
            {"id":"a","template_id":"torso","name_patterns":["host a"]},
            {"id":"b","template_id":"torso","name_patterns":["host b"]}],
            "secondary_rules":[{"id":"frill","template_id":"frill","name_patterns":["frill"],
                                 "kind":"shared_offset","host_slots":["a","b"]}]}
        out=infer_structure(obs,spec)
        self.assertEqual(out["coverage"]["unresolved_attachments"],1)
        self.assertTrue(any(q["kind"]=="attachment_host" for q in out["questions"]))

    def test_split_merge_output_is_invariant_to_native_node_order(self):
        obs,spec=shared_carrier_fixture()
        a=infer_structure(obs,spec)
        obs["nodes"].reverse()
        b=infer_structure(obs,spec)
        self.assertEqual(a,b)

    def test_scaffold_assigns_anonymous_groups_without_name_requirements(self):
        obs,spec=scaffold_fixture()
        out=infer_structure(obs,spec)
        self.assertEqual(out["hypotheses"][0]["assignment"],{"upper":"1","lower":"2"})
        frame=out["normalization"]["selected_frame"]
        self.assertEqual(frame["bounds"],[30,0,70,75])
        self.assertEqual(frame["kind"],"primary_scaffold_candidate")
        self.assertFalse(frame["anatomical_bounds_verified"])

    def test_unrelated_extreme_appendage_does_not_move_scaffold_frame(self):
        obs,spec=scaffold_fixture()
        # Labels are weak supporting evidence in this synthetic example.
        spec["primary_slots"][0]["name_patterns"]=["surface a"]
        spec["primary_slots"][1]["name_patterns"]=["surface b"]
        baseline=infer_structure(obs,spec)
        for box in ([70,-500,10000,100],[-10000,-500,0,100],[0,-10000,100,0]):
            with self.subTest(box=box):
                extended=copy.deepcopy(obs)
                extended["nodes"].extend([
                    {"uuid":3,"type":"GridDeformer","name":"unclassified appendage","parent":0},
                    {"uuid":13,"type":"Part","name":"paint","parent":3,"bounds":box}])
                actual=infer_structure(extended,spec)
                self.assertNotEqual(actual["normalization"]["observed_bounds"],baseline["normalization"]["observed_bounds"])
                self.assertEqual(actual["hypotheses"][0],baseline["hypotheses"][0])
                self.assertEqual(actual["normalization"]["selected_frame"],baseline["normalization"]["selected_frame"])
                self.assertEqual(actual["coverage"]["active_parts"],3)

    def test_each_retained_hypothesis_uses_its_own_scaffold_frame(self):
        obs,spec=scaffold_fixture()
        out=infer_structure(obs,spec)
        groups={group["id"]:group for group in out["group_candidates"]}
        for row in out["normalization"]["frame_hypotheses"]:
            frame=row["frame"]
            if frame["fallback"]: continue
            boxes=[groups[row["assignment"][sid]]["bounds"] for sid in spec["normalization"]["required_slots"]]
            self.assertEqual(frame["bounds"],[min(b[0] for b in boxes),min(b[1] for b in boxes),
                                              max(b[2] for b in boxes),max(b[3] for b in boxes)])

    def test_missing_required_scaffold_slot_reports_explicit_fallback(self):
        obs,spec=scaffold_fixture()
        obs["nodes"]=[node for node in obs["nodes"] if node["uuid"] not in (2,12)]
        out=infer_structure(obs,spec)
        frame=out["normalization"]["selected_frame"]
        self.assertEqual(frame["kind"],"enabled_observation_bounds")
        self.assertTrue(frame["fallback"])
        self.assertTrue(any(row["reason"]=="unassigned" for row in frame["fallback_reasons"]))
        self.assertTrue(any(q["kind"]=="scaffold_normalization_fallback" for q in out["questions"]))

    def test_unknown_or_degenerate_core_geometry_does_not_create_frame(self):
        for bounds in (None,[10,20,10,30]):
            with self.subTest(bounds=bounds):
                obs,spec=scaffold_fixture()
                obs["nodes"][-1]["bounds"]=bounds
                out=infer_structure(obs,spec,{"primary_assignments":{"upper":"1","lower":"2"}})
                frame=out["normalization"]["selected_frame"]
                self.assertTrue(frame["fallback"])
                self.assertEqual(frame["fallback_reasons"],[{"slot":"lower","reason":"missing_or_degenerate_geometry"}])

    def test_competing_scaffold_frames_keep_scores_and_ambiguity(self):
        obs,spec=scaffold_fixture()
        spec["primary_slots"][0]["name_patterns"]=["surface a"]
        spec["primary_slots"][1]["name_patterns"]=["surface b"]
        obs["nodes"].extend([
            {"uuid":3,"type":"GridDeformer","name":"surface a","parent":0},
            {"uuid":13,"type":"Part","name":"paint","parent":3,"bounds":[40,0,60,25]}])
        out=infer_structure(obs,spec)
        self.assertEqual(out["score_margin"],0)
        self.assertTrue(any(q["kind"]=="normalization_frame" for q in out["questions"]))
        frames=out["normalization"]["frame_hypotheses"]
        self.assertGreater(len({row["frame"]["id"] for row in frames}),1)
        self.assertTrue(all("score" in row and "assignment" in row for row in frames))
        evaluated=out["normalization"]["evaluated_frames"]
        self.assertEqual(len(evaluated),len({tuple(frame["bounds"]) for frame in evaluated}))
        self.assertLessEqual(len(evaluated),1+spec["normalization"]["iterations"]*spec["normalization"]["hypothesis_limit"])

    def test_scaffold_translation_uniform_scale_and_order_invariance(self):
        obs,spec=scaffold_fixture()
        baseline=infer_structure(obs,spec)
        transformed=copy.deepcopy(obs)
        for node in transformed["nodes"]:
            if "bounds" in node:
                b=node["bounds"]["nominal_world_xy"]
                node["bounds"]["nominal_world_xy"]=[b[0]*3+17,b[1]*3-29,b[2]*3+17,b[3]*3-29]
        transformed["nodes"].reverse()
        actual=infer_structure(transformed,spec)
        self.assertEqual(actual["hypotheses"][0]["assignment"],baseline["hypotheses"][0]["assignment"])
        self.assertAlmostEqual(actual["hypotheses"][0]["score"],baseline["hypotheses"][0]["score"])
        self.assertEqual(actual["normalization"]["selected_frame"]["bounds"],[107,-29,227,196])
        obs["nodes"].reverse()
        self.assertEqual(infer_structure(obs,spec),baseline)

    def test_appendage_cannot_enlarge_merge_gap(self):
        obs={"source":{},"nodes":[{"uuid":0,"type":"Node","name":"root","parent":None}]}
        for gid,name,box in ((10,"body a",[0,0,100,100]),(20,"body b",[0,300,100,400])):
            obs["nodes"].extend([{"uuid":gid,"type":"GridDeformer","name":name,"parent":0},
                                 {"uuid":gid+1,"type":"Part","name":"paint","parent":gid,"bounds":box}])
        spec={"id":"merge-local","primary_slots":[{"id":"body","template_id":"torso","name_patterns":["body"]}],"secondary_rules":[]}
        baseline=infer_structure(obs,spec)
        obs["nodes"].extend([{"uuid":30,"type":"GridDeformer","name":"unclassified","parent":0},
                             {"uuid":31,"type":"Part","name":"paint","parent":30,"bounds":[0,0,10000,100]}])
        actual=infer_structure(obs,spec)
        for out in (baseline,actual):
            self.assertFalse(any(set(group["parts"])=={11,21} for group in out["group_candidates"]))

    def test_scaffold_config_rejects_unknown_slots_and_unbounded_search(self):
        for key,value in (("required_slots",["absent"]),("required_slots",["upper","upper"]),
                          ("iterations",100),("hypothesis_limit",0),("coordinate_system","guessed_body")):
            with self.subTest(key=key,value=value):
                obs,spec=scaffold_fixture();spec["normalization"][key]=value
                with self.assertRaises(ValueError): infer_structure(obs,spec)

    def test_host_scores_use_scaffold_scale_not_extreme_appendage_extent(self):
        obs={"source":{},"nodes":[{"uuid":0,"type":"Node","name":"root","parent":None}]}
        for gid,name,box in ((1,"host a",[0,0,10,10]),(2,"host b",[20,0,30,10]),(3,"frill",[2,2,4,4])):
            obs["nodes"].extend([{"uuid":gid,"type":"GridDeformer","name":name,"parent":0},
                                 {"uuid":gid+10,"type":"Part","name":"paint","parent":gid,"bounds":box}])
        spec={"id":"host-frame","normalization":{"coordinate_system":"primary_scaffold_hypotheses",
              "required_slots":["a","b"]},"primary_slots":[
              {"id":"a","template_id":"torso","name_patterns":["host a"],"position":[.17,.5],"size":[.33,1]},
              {"id":"b","template_id":"torso","name_patterns":["host b"],"position":[.83,.5],"size":[.33,1]}],
              "secondary_rules":[{"id":"frill","template_id":"frill","name_patterns":["frill"],
                                   "host_slots":["a","b"],"kind":"shared_offset"}]}
        baseline=infer_structure(obs,spec)
        obs["nodes"].extend([{"uuid":4,"type":"GridDeformer","name":"unclassified appendage","parent":0},
                             {"uuid":14,"type":"Part","name":"paint","parent":4,"bounds":[1000,1000,1100,1100]}])
        actual=infer_structure(obs,spec)
        get_frill=lambda out: next(surface for surface in out["surfaces"] if surface["structural_role"]=="frill")
        self.assertEqual(get_frill(actual)["host_ranking"],get_frill(baseline)["host_ranking"])
        self.assertEqual(get_frill(actual)["proposed_host"],get_frill(baseline)["proposed_host"])


if __name__ == "__main__": unittest.main()
