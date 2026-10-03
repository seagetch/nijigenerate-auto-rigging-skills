"""Subprocess transport stubs only: no model files, fixtures or live mutation."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from riglib.live import Live, NJCRequestTooLarge, NJCTransportError, COMMAND_LINE_UTF16_LIMIT


def response(result):
    return subprocess.CompletedProcess([], 0, json.dumps({"jsonrpc": "2.0", "id": 2, "result": result}), "")


class NJCTransportTests(unittest.TestCase):
    def setUp(self):
        # Existing interpreter is a path-only stand-in; subprocess is always
        # mocked. Nothing pretends to create or serialize a character model.
        self.client = Live(sys.executable)

    def test_literal_json_uses_one_njc_process_and_no_shell(self):
        data = {"name": 'quote " 日本語 \\ with spaces', "values": [0, 1.5, -2]}
        with patch("riglib.live.subprocess.run", return_value=response({"content": [{"text": '{"succeeded":true}'}]})) as run:
            self.assertEqual(self.client.call("Example", **data), {"succeeded": True})
        run.assert_called_once()
        argv = run.call_args.args[0]
        self.assertEqual(argv[:4], [self.client.executable, "tools", "call", "Example"])
        self.assertEqual(argv[4], "--json")
        self.assertEqual(json.loads(argv[5]), data)
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_preflight_is_offline_and_counts_windows_quoting(self):
        args = ["tools", "call", "Example"]
        data = {"value": '\\" ' * 100 + "😀" * 20}
        argv = [self.client.executable, *args, "--json", json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))]
        with patch("riglib.live.subprocess.run") as run:
            audit = self.client.preflight(args, data)
        run.assert_not_called()
        self.assertEqual(audit["command_line_utf16_units"], len(subprocess.list2cmdline(argv).encode("utf-16-le")) // 2 + 1)
        self.assertFalse(audit["request_sent"])

    def test_overlong_ascii_payload_is_rejected_before_start(self):
        with patch("riglib.live.subprocess.run") as run:
            with self.assertRaisesRegex(NJCRequestTooLarge, "Request was not sent"):
                self.client.call("Example", text="x" * COMMAND_LINE_UTF16_LIMIT)
        run.assert_not_called()

    def test_non_bmp_characters_count_as_two_utf16_units(self):
        data = {"text": "😀" * 15500}
        self.assertLess(len(json.dumps(data, ensure_ascii=False)), COMMAND_LINE_UTF16_LIMIT)
        with patch("riglib.live.subprocess.run") as run:
            with self.assertRaises(NJCRequestTooLarge):
                self.client.preflight_call("Example", **data)
        run.assert_not_called()

    def test_quote_expansion_can_exceed_capacity(self):
        data = {"text": '"' * 10500}
        self.assertLess(len(json.dumps(data)), COMMAND_LINE_UTF16_LIMIT)
        with patch("riglib.live.subprocess.run") as run:
            with self.assertRaises(NJCRequestTooLarge):
                self.client.call("Example", **data)
        run.assert_not_called()

    def test_capacity_guard_applies_to_read_and_rpc_too(self):
        with patch("riglib.live.subprocess.run") as run:
            for args, data in [(["read", "x" * COMMAND_LINE_UTF16_LIMIT], None),
                               (["rpc", "tools/call"], {"value": "x" * COMMAND_LINE_UTF16_LIMIT})]:
                with self.assertRaises(NJCRequestTooLarge):
                    self.client.invoke(args, data)
        run.assert_not_called()

    def test_nan_and_invalid_argument_types_never_start(self):
        with patch("riglib.live.subprocess.run") as run:
            for args, data in [(["tools", "call", "X"], {"value": float("nan")}),
                               ("read value", None), (["read", "bad\x00argument"], None),
                               (["tools", "call", "X"], [])]:
                with self.assertRaises(ValueError):
                    self.client.invoke(args, data)
        run.assert_not_called()

    def test_timeout_is_not_retried(self):
        with patch("riglib.live.subprocess.run", side_effect=subprocess.TimeoutExpired(["njc"], 120)) as run:
            with self.assertRaisesRegex(NJCTransportError, "completion is unknown"):
                self.client.call("Example")
        run.assert_called_once()

    def test_nonzero_exit_is_not_retried(self):
        with patch("riglib.live.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "failure")) as run:
            with self.assertRaisesRegex(NJCTransportError, "failure"):
                self.client.find("*")
        run.assert_called_once()

    def test_protocol_and_command_failures_are_rejected(self):
        payloads = ['not-json', '[]', '{}', '{"error":{"message":"failure"}}',
                    '{"result":{"isError":true,"content":[]}}',
                    '{"result":{"content":[{"text":"{\\"succeeded\\":false}"}]}}',
                    '{"result":{"content":[{"text":"{\\"result\\":{\\"succeeded\\":false}}"}]}}',
                    '{"result":{},"result":{}}', '{"result":NaN}']
        for raw in payloads:
            with self.subTest(raw=raw), patch("riglib.live.subprocess.run", return_value=subprocess.CompletedProcess([], 0, raw, "")) as run:
                with self.assertRaises(NJCTransportError):
                    self.client.invoke(["read", "resource://test"])
                run.assert_called_once()

    def test_null_nested_result_is_not_an_attribute_error(self):
        with patch("riglib.live.subprocess.run", return_value=response({"content": [{"text": '{"result":null}'}]})):
            self.assertEqual(self.client.read(12), {"result": None})

    def test_tools_list_and_plain_resource_text_are_preserved(self):
        with patch("riglib.live.subprocess.run", return_value=response({"tools": []})):
            self.assertEqual(self.client.invoke(["tools", "list"]), {"tools": []})
        with patch("riglib.live.subprocess.run", return_value=response({"contents": [{"text": "resource guide text"}]})):
            self.assertEqual(self.client.read("resource://test"), "resource guide text")

    def test_open_save_are_njc_requests_without_python_file_access(self):
        # The named INX is deliberately not created, inspected or opened.
        missing = Path("not-a-generated-model.inx")
        with patch("riglib.live.subprocess.run", return_value=response({"content": [{"text": '{"succeeded":true}'}]})) as run:
            self.client.open(missing)
            self.client.save(missing)
        self.assertEqual(run.call_count, 2)
        self.assertEqual([c.args[0][3] for c in run.call_args_list], ["FileCommand_OpenFile", "FileCommand_SaveFile"])
        for call in run.call_args_list:
            self.assertEqual(json.loads(call.args[0][-1]), {"file": str(missing.resolve())})


if __name__ == "__main__":
    unittest.main()
