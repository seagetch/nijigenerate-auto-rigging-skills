from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from riglib.njc import (STATE_SCHEMA, DEPTH_TOOL, DEFORM_TOOL, PlanError, ExecutionStopped,
                        axis_calibration_sha256, vertices_sha256, normalize_state,
                        export_plan, validate_plan, execute_plan)


def snapshot():
    calibration = {
        "status": "verified", "frame": "carrier-local", "parent_state_sha256": "a"*64,
        "xy_units": "model-unit", "depth_units": "njc-depth-unit",
        "world_to_local_xy": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "depth_scale": 1, "depth_sign": 1,
    }
    return {
        "schema_version": STATE_SCHEMA, "model_id": "test-model", "complete": True,
        "evaluation_settled": True, "drivers_enabled": False,
        "protected_state": {"hierarchy": [{"uuid": 12, "parent": 1}],
                            "topology": [[0, 1, 2]], "unrelated_binding": [4, 5]},
        "carriers": [{"uuid": 12, "node_type": "GridDeformer", "depth_mapped": True,
                      "vertices": [[0, 0], [1, 0], [0, 1]], "depths": [0, 0, 0],
                      "parent_state_sha256": "a"*64, "axis_calibration": calibration}],
        "parameters": [{"uuid": 45, "actual_axes": [[-2, 0, 2], [-3, 0, 3]]}],
        "deform_keys": [{"target": 12, "parameter": 45, "actual_parameter_value": [2, -3],
                         "is_set": True, "values": [0, 0, 0, 0, 0, 0]}],
    }


def sampled(state, kind="depth"):
    carrier = state["carriers"][0]
    result = {
        "kind": kind, "target": carrier["uuid"],
        "expected_vertices_sha256": vertices_sha256(carrier["vertices"]),
        "sampling": {"vertex_order": "carrier", "frame": "carrier-local",
                     "units": "njc-depth-unit" if kind == "depth" else "model-unit",
                     "value_semantics": "absolute-depth" if kind == "depth" else "deform-offsets",
                     "axis_calibration_sha256": axis_calibration_sha256(carrier["axis_calibration"])},
        "values": [0, 0.5, 0] if kind == "depth" else [0, 0, 2, -1, 0, 0],
        "allowed_vertices": [1], "expected_changed_vertices": 1,
    }
    if kind == "deform":
        result.update(parameter=45, actual_parameter_value=[2, -3])
    return result


class MemoryBackend:
    """Test adapter only, never the user's live model."""
    def __init__(self, state):
        self.state = deepcopy(state)
        self.calls = []
        self.foreign_on_call = False
        self.raise_after_mutation = False

    def snapshot(self):
        return deepcopy(self.state)

    def call(self, tool, args):
        self.calls.append((tool, deepcopy(args)))
        if tool == DEPTH_TOOL:
            next(c for c in self.state["carriers"] if c["uuid"] == args["target"])["depths"] = args["depths"]
        elif tool == DEFORM_TOOL:
            context = args["context"]
            key = next(k for k in self.state["deform_keys"] if k["target"] == context["nodes"][0]
                       and k["parameter"] == context["parameters"][0]
                       and k["actual_parameter_value"] == context["parameterValue"])
            key["values"], key["is_set"] = args["values"], True
        else:
            raise AssertionError("unexpected test tool")
        if self.foreign_on_call:
            self.state["protected_state"]["unrelated_binding"][0] += 1
        if self.raise_after_mutation:
            raise TimeoutError("response lost after mutation")
        return {"isError": False}


class NJCExportTests(unittest.TestCase):
    def test_export_is_deterministic_and_explicit(self):
        state = snapshot()
        plan = export_plan(state, [sampled(state), sampled(state, "deform")])
        self.assertEqual(plan, export_plan(deepcopy(state), [sampled(state), sampled(state, "deform")]))
        self.assertEqual(validate_plan(plan)["command_count"], 2)
        depth, deform = plan["commands"]
        self.assertEqual(depth["arguments"]["context"], {"nodes": [12], "parameters": [],
                         "parameterValue": [], "armedParameters": [], "bindings": []})
        self.assertEqual(deform["arguments"]["context"]["parameterValue"], [2, -3])
        self.assertEqual(deform["arguments"]["values"], [0, 0, 2, -1, 0, 0])
        self.assertFalse(plan["guarantees"]["atomic"])
        self.assertEqual(state["carriers"][0]["depths"], [0, 0, 0])

    def test_reordered_carrier_vertices_are_not_template_correspondence(self):
        state = snapshot()
        target = sampled(state)
        state["carriers"][0]["vertices"].reverse()
        with self.assertRaisesRegex(PlanError, "vertex count/order"):
            export_plan(state, [target])

    def test_sparse_nonfinite_or_wrong_units_are_rejected(self):
        state = snapshot()
        for field, value in (("values", [0.5]), ("values", [0, float("nan"), 0])):
            target = sampled(state)
            target[field] = value
            with self.assertRaises(PlanError):
                export_plan(state, [target])
        target = sampled(state)
        target["sampling"]["units"] = "source-pixel"
        with self.assertRaisesRegex(PlanError, "units"):
            export_plan(state, [target])

    def test_axis_calibration_and_depth_capability_are_required(self):
        state = snapshot()
        target = sampled(state)
        state["carriers"][0]["axis_calibration"]["depth_sign"] = -1
        with self.assertRaisesRegex(PlanError, "axis calibration differs"):
            export_plan(state, [target])
        state = snapshot()
        state["carriers"][0].update(node_type="Part", depth_mapped=False, depths=None)
        with self.assertRaisesRegex(PlanError, "DepthMapped"):
            export_plan(state, [sampled(state)])
        state = snapshot()
        state["carriers"][0]["parent_state_sha256"] = "b"*64
        with self.assertRaisesRegex(PlanError, "parent state"):
            normalize_state(state)

    def test_parameter_indices_are_not_actual_values(self):
        state = snapshot()
        target = sampled(state, "deform")
        target["actual_parameter_value"] = [1, 0]
        with self.assertRaisesRegex(PlanError, "not an index"):
            export_plan(state, [target])

    def test_pose_positions_cannot_be_exported_as_offsets_implicitly(self):
        state = snapshot()
        target = sampled(state, "deform")
        target["sampling"]["value_semantics"] = "absolute-positions"
        with self.assertRaisesRegex(PlanError, "value_semantics"):
            export_plan(state, [target])

    def test_readback_with_reenabled_drivers_is_saved_and_frozen(self):
        state = snapshot()
        plan = export_plan(state, [sampled(state)])
        backend = MemoryBackend(state)
        original_call = backend.call

        def changed_driver(tool, arguments):
            result = original_call(tool, arguments)
            backend.state["drivers_enabled"] = True
            return result

        backend.call = changed_driver
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ExecutionStopped, "drivers") as raised:
                execute_plan(plan, backend, folder)
            saved = json.loads(Path(raised.exception.journal_path).read_text())
            self.assertTrue(saved["frozen"])
            self.assertTrue(saved["observed_unvalidated_state"]["drivers_enabled"])

    def test_outside_subset_and_wrong_moved_count_are_rejected(self):
        state = snapshot()
        target = sampled(state)
        target["values"][0] = 0.1
        with self.assertRaisesRegex(PlanError, "allowed subset"):
            export_plan(state, [target])
        target = sampled(state)
        target["expected_changed_vertices"] = 2
        with self.assertRaisesRegex(PlanError, "changed vertex count"):
            export_plan(state, [target])

    def test_arbitrary_commands_or_implicit_context_cannot_be_injected(self):
        state = snapshot()
        plan = export_plan(state, [sampled(state)])
        plan["commands"][0]["tool"] = "FileCommand_OpenFile"
        with self.assertRaisesRegex(PlanError, "deterministic compilation"):
            validate_plan(plan)
        plan = export_plan(state, [sampled(state)])
        del plan["commands"][0]["arguments"]["context"]
        with self.assertRaises(PlanError):
            validate_plan(plan)

    def test_complete_settled_driver_free_snapshot_is_required(self):
        for field, value in (("complete", False), ("evaluation_settled", False), ("drivers_enabled", True)):
            state = snapshot()
            state[field] = value
            with self.assertRaises(PlanError):
                export_plan(state, [sampled(state)])

    def test_success_is_journaled_and_replay_is_rejected(self):
        state = snapshot()
        plan = export_plan(state, [sampled(state), sampled(state, "deform")])
        backend = MemoryBackend(state)
        with tempfile.TemporaryDirectory() as folder:
            receipt = execute_plan(plan, backend, folder)
            self.assertEqual(receipt["status"], "verified")
            self.assertEqual(len(backend.calls), 2)
            self.assertFalse(list(Path(folder).glob("*.lock")))
            with self.assertRaisesRegex(PlanError, "already attempted"):
                execute_plan(plan, backend, folder)
            self.assertEqual(len(backend.calls), 2)
            self.assertEqual(json.loads(Path(receipt["journal_path"]).read_text())["status"], "verified")

    def test_stale_prestate_never_sends_a_command(self):
        state = snapshot()
        plan = export_plan(state, [sampled(state)])
        backend = MemoryBackend(state)
        backend.state["protected_state"]["unrelated_binding"][0] += 1
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ExecutionStopped, "pre-state") as raised:
                execute_plan(plan, backend, folder)
            self.assertFalse(backend.calls)
            saved = json.loads(Path(raised.exception.journal_path).read_text())
            self.assertEqual(saved["status"], "rejected_before_write")
            self.assertFalse(saved["frozen"])

    def test_foreign_readback_change_freezes_after_one_call(self):
        state = snapshot()
        plan = export_plan(state, [sampled(state), sampled(state, "deform")])
        backend = MemoryBackend(state)
        backend.foreign_on_call = True
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ExecutionStopped, "readback") as raised:
                execute_plan(plan, backend, folder)
            self.assertEqual(len(backend.calls), 1)
            saved = json.loads(Path(raised.exception.journal_path).read_text())
            self.assertTrue(saved["frozen"])
            self.assertIn("observed_state", saved)
            self.assertTrue(list(Path(folder).glob("*.lock")))
            new_state = normalize_state(backend.state)
            other = sampled(new_state)
            other["values"] = [0, 0.8, 0]
            other_plan = export_plan(new_state, [other])
            with self.assertRaisesRegex(ExecutionStopped, "active or frozen"):
                execute_plan(other_plan, backend, folder)
            self.assertEqual(len(backend.calls), 1)

    def test_timeout_after_mutation_records_readback_and_never_retries(self):
        state = snapshot()
        plan = export_plan(state, [sampled(state), sampled(state, "deform")])
        backend = MemoryBackend(state)
        backend.raise_after_mutation = True
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ExecutionStopped, "response lost") as raised:
                execute_plan(plan, backend, folder)
            saved = json.loads(Path(raised.exception.journal_path).read_text())
            self.assertTrue(saved["frozen"])
            self.assertEqual(saved["observed_state"]["carriers"][0]["depths"], [0, 0.5, 0])
            self.assertEqual(len(backend.calls), 1)
            self.assertFalse(saved["automatic_retry_allowed"])
            self.assertFalse(saved["automatic_rollback_attempted"])


if __name__ == "__main__":
    unittest.main()
