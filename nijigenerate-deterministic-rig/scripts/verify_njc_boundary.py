#!/usr/bin/env python3
"""AST audit of current scripts: native model I/O belongs to the NJC client.

This bounded static audit is not a proof about arbitrary Python, dynamic aliases,
external dependencies, renamed files or concurrent filesystem changes. It parses
current Python source only, never imports project operations or opens models.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path, PureWindowsPath
import re

from riglib.data import write_json


SCRIPTS = Path(__file__).resolve().parent
NETWORK_ROOTS = {"urllib", "urllib3", "requests", "http", "httpx", "socket", "aiohttp", "websockets"}
MODEL_READERS = {"read_model_metadata", "observe_model"}
MODEL_NAMES = {"model", "model_path", "model_file", "inp", "inx", "inp_path", "inx_path"}
CLIENT_NAMES = {"client", "njc_client", "njc"}
GENERIC_FILE_HELPERS = {"read_json", "write_json", "digest"}
PATH_OPERATIONS = {"read_text", "read_bytes", "write_text", "write_bytes", "open", "rename", "replace"}
STREAM_OPERATIONS = {"read", "write", "readinto", "readline", "readlines", "writelines"}
COPY_OPERATIONS = {"shutil.copy", "shutil.copy2", "shutil.copyfile", "shutil.copytree", "shutil.move",
                   "os.rename", "os.replace", "os.link", "os.symlink"}


def _native_literal(value):
    if not isinstance(value, str):
        return False
    leaf = PureWindowsPath(value).name.split(":", 1)[0].rstrip(" .")
    return PureWindowsPath(leaf).suffix.casefold() in {".inp", ".inx"} or bool(
        re.search(r"\.(?:inp|inx)(?::[^\\/]*)?$", value, re.I))


def _local_nodes(scope):
    """Walk one lexical scope; nested functions/classes are audited separately."""
    pending = list(reversed(scope.body))
    while pending:
        node = pending.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            pending.extend(reversed(list(ast.iter_child_nodes(node))))


def _target_names(node):
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.Tuple, ast.List)):
        return set().union(*(_target_names(item) for item in node.elts))
    return set()


def audit_source(source, filename):
    """Return findings for supplied Python text, without executing it."""
    findings = []
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as error:
        return [{"file": filename, "line": error.lineno or 1, "rule": "syntax_error",
                 "message": error.msg, "severity": "error"}]
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split(".")[0]] = item.name if item.asname else item.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            for item in node.names:
                aliases[item.asname or item.name] = (node.module + "." if node.module else "") + item.name

    def symbol(node):
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return symbol(node.value) + "." + node.attr
        if isinstance(node, ast.Call):
            return symbol(node.func) + "()"
        if isinstance(node, ast.Subscript):
            return symbol(node.value) + "[" + ast.dump(node.slice, include_attributes=False) + "]"
        return "?"

    def path_sources(node):
        if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)):
            return {symbol(node)}
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"resolve", "absolute", "with_suffix", "with_name"}:
                return path_sources(node.func.value)
            if node.args and symbol(node.func).rsplit(".", 1)[-1] in {"Path", "str", "fspath"}:
                return path_sources(node.args[0])
        return set()

    def add(node, rule, message):
        findings.append({"file": filename, "line": getattr(node, "lineno", 1),
                         "rule": rule, "message": message, "severity": "error"})

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [item.name for item in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for name in names:
                if name.split(".")[0] in NETWORK_ROOTS:
                    add(node, "direct_transport_import", f"Direct transport import {name}; use the NJC subprocess client.")
        if isinstance(node, ast.Call):
            name = symbol(node.func)
            if name.split(".")[0] in NETWORK_ROOTS:
                add(node, "direct_transport_call", f"Direct transport call {name}; use the NJC subprocess client.")
            if name in {"__import__", "importlib.import_module"}:
                module = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else None
                if isinstance(module, str) and module.split(".")[0] in NETWORK_ROOTS:
                    add(node, "dynamic_transport_import", f"Dynamic transport import {module} is forbidden.")
            if name.rsplit(".", 1)[-1] in MODEL_READERS:
                clients = [kw.value for kw in node.keywords if kw.arg == "client"]
                if not clients or isinstance(clients[0], ast.Constant) and clients[0].value is None:
                    add(node, "model_reader_without_client", f"{name} requires an explicit non-None client= argument.")

    scopes = [tree] + [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    for scope in scopes:
        nodes = list(_local_nodes(scope))
        tainted, clients = set(), set(CLIENT_NAMES)
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = scope.args.posonlyargs + scope.args.args + scope.args.kwonlyargs
            tainted.update(arg.arg for arg in args if arg.arg in MODEL_NAMES)
            if scope.name in MODEL_READERS and args:
                tainted.add(args[0].arg)

        def is_tainted(expr):
            if isinstance(expr, ast.Call) and symbol(expr.func).rsplit(".", 1)[-1] in MODEL_READERS | {"_non_model_path"}:
                return False
            for item in ast.walk(expr):
                if isinstance(item, (ast.Name, ast.Attribute, ast.Subscript)) and symbol(item) in tainted:
                    return True
                if isinstance(item, ast.Attribute) and item.attr in MODEL_NAMES:
                    return True
                if isinstance(item, ast.Constant) and _native_literal(item.value):
                    return True
            return False

        # A path passed to a model reader, or checked for a model suffix, is a
        # model-path source regardless of what its variable happens to be named.
        for node in nodes:
            if isinstance(node, ast.Call) and symbol(node.func).rsplit(".", 1)[-1] in MODEL_READERS and node.args:
                tainted.update(path_sources(node.args[0]))
            if isinstance(node, ast.Compare) and any(isinstance(item, ast.Constant) and _native_literal(item.value)
                                                     for item in ast.walk(node)):
                for item in ast.walk(node):
                    if isinstance(item, ast.Attribute) and item.attr == "suffix":
                        tainted.update(path_sources(item.value))

        # A finite monotone propagation across assignments and with-bound streams.
        for _ in range(len(nodes) + 1):
            previous = (len(tainted), len(clients))
            for node in nodes:
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    value = node.value
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    names = set().union(*(_target_names(target) for target in targets))
                    if value is not None and is_tainted(value): tainted.update(names)
                    if isinstance(value, ast.Call) and symbol(value.func).rsplit(".", 1)[-1] == "Live":
                        clients.update(names)
                    if isinstance(value, ast.Name) and value.id in clients: clients.update(names)
                elif isinstance(node, ast.withitem) and node.optional_vars and is_tainted(node.context_expr):
                    tainted.update(_target_names(node.optional_vars))
            if previous == (len(tainted), len(clients)): break

        for node in nodes:
            if not isinstance(node, ast.Call): continue
            name = symbol(node.func)
            method = name.rsplit(".", 1)[-1]
            receiver = node.func.value if isinstance(node.func, ast.Attribute) else None
            client_call = isinstance(receiver, ast.Name) and receiver.id in clients
            paths = []
            if name in COPY_OPERATIONS:
                paths = node.args[:2] + [kw.value for kw in node.keywords if kw.arg in {"src", "dst"}]
            elif name in {"open", "builtins.open", "io.open", "os.open", "os.read", "os.write"}:
                paths = node.args[:1] + [kw.value for kw in node.keywords if kw.arg in {"file", "path"}]
            elif method in GENERIC_FILE_HELPERS:
                paths = node.args[:1] + [kw.value for kw in node.keywords if kw.arg == "path"]
            elif not client_call and receiver is not None and method in PATH_OPERATIONS | STREAM_OPERATIONS:
                paths = [receiver]
                if method in {"open", "rename", "replace"}: paths += node.args[:1]
            elif not client_call and method in {"save", "load", "imread", "imwrite"}:
                paths = node.args[:1]
            if any(is_tainted(path) for path in paths):
                add(node, "direct_native_model_io", f"Native-model path reaches {name}; all model reads/writes/copies must use NJC.")
            if name in {"subprocess.run", "subprocess.Popen", "subprocess.call", "os.system"}:
                gateway = filename.replace("\\", "/").endswith("riglib/live.py")
                if not gateway and node.args and is_tainted(node.args[0]):
                    add(node, "model_path_external_process", f"Model path reaches {name} outside the NJC client adapter.")

    if filename.replace("\\", "/").endswith("riglib/data.py"):
        definitions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        for helper in sorted(GENERIC_FILE_HELPERS):
            function = definitions.get(helper)
            if function is None or not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                                           and node.func.id == "_non_model_path" for node in ast.walk(function)):
                add(function or tree, "generic_model_suffix_guard_missing", f"{helper} must call _non_model_path before filesystem access.")
    unique = {(item["line"], item["rule"], item["message"]): item for item in findings}
    return sorted(unique.values(), key=lambda item: (item["line"], item["rule"], item["message"]))


def audit_scripts():
    findings, files = [], []
    for path in sorted(SCRIPTS.rglob("*.py")):
        # Refuse symlink escape; the audit does not follow arbitrary source roots.
        relative = path.relative_to(SCRIPTS).as_posix()
        if not path.resolve().is_relative_to(SCRIPTS):
            findings.append({"file": relative, "line": 1, "rule": "source_scope_escape",
                             "message": "Python source resolves outside scripts.", "severity": "error"})
            continue
        files.append(relative)
        findings.extend(audit_source(path.read_text(encoding="utf-8-sig"), relative))
    return {"schema_version": "rig-njc-boundary-audit/1", "passed": not findings,
            "scope": "current deterministic-rig/scripts Python source only",
            "files_scanned": files, "findings": findings,
            "model_files_read": False, "model_files_written": False,
            "model_operations_executed": False, "complete_python_security_proof": False,
            "limitations": ["AST and bounded intraprocedural path flow do not resolve arbitrary dynamic dispatch or external dependencies.",
                            "Explicit client= is a checked API contract, not runtime type attestation.",
                            "Path suffix guards do not identify model bytes renamed to another extension or defeat concurrent symlink replacement."]}


def self_test():
    fixtures = [
        ("transport_alias", "import urllib.request as transport\ntransport.urlopen('http://localhost')", "direct_transport_call"),
        ("requests_alias", "from requests import post as send\nsend('http://localhost')", "direct_transport_call"),
        ("socket_alias", "import socket as network\nnetwork.socket()", "direct_transport_call"),
        ("dynamic_network", "__import__('requests')", "dynamic_transport_import"),
        ("model_literal", "from pathlib import Path\nPath('x.INX').read_bytes()", "direct_native_model_io"),
        ("class_body_model_io", "from pathlib import Path\nclass Bad:\n data=Path('x.inp').read_bytes()", "direct_native_model_io"),
        ("model_alias", "from pathlib import Path\ndef read_model_metadata(path,client=None):\n p=Path(path)\n with p.open('rb') as stream: return stream.read()", "direct_native_model_io"),
        ("model_copy", "from shutil import copyfile as cp\ndef work(source,destination):\n read_model_metadata(source,client=client)\n cp(source,destination)", "direct_native_model_io"),
        ("reader_without_client", "from riglib.model import read_model_metadata as read\nread(path)", "model_reader_without_client"),
        ("reader_none_client", "observe_model(path,client=None)", "model_reader_without_client"),
        ("generic_model_read", "read_json('x.inp')", "direct_native_model_io"),
        ("client_allowed", "from riglib.live import Live\ndef work(path):\n client=Live(executable)\n client.open(path)\n return read_model_metadata(path,client=client)", None),
        ("internal_json_allowed", "from pathlib import Path\nPath('internal.json').write_text('model.inx')", None),
        ("argument_object_not_a_path", "def run(args):\n observe_model(args.model,client=client)\n write_json(args.output, {})", None),
        ("strings_not_code", "text='import requests; Path(\"x.inx\").read_bytes()'\n# socket.socket()", None),
    ]
    results = []
    for label, source, rule in fixtures:
        found = audit_source(source, "fixture.py")
        if rule is None and found or rule is not None and not any(row["rule"] == rule for row in found):
            raise AssertionError(f"boundary self-test {label} failed: {found}")
        results.append(label)

    from riglib.data import read_json, digest, _non_model_path
    from tempfile import TemporaryDirectory
    from unittest.mock import patch
    from contextlib import ExitStack
    # Even a regression must not create/open a test INX/INP. Every filesystem
    # operation reachable from the negative tests is disabled before calling.
    with ExitStack() as stack:
        for method in ("read_text", "write_text", "open", "mkdir", "resolve"):
            stack.enter_context(patch.object(Path, method,
                side_effect=AssertionError("blocked suffix reached filesystem operation")))
        for value in ("never-created.inx", "never-created.INP", "never-created.InX. ", "never-created.inp:stream", ".inp"):
            for label, operation in (("read", lambda: read_json(value)), ("write", lambda: write_json(value, {})),
                                     ("digest", lambda: digest(value))):
                try:
                    operation()
                except ValueError as error:
                    if "NJC" not in str(error): raise
                else:
                    raise AssertionError(f"native suffix was not blocked: {label}")
                results.append("suffix_" + label + "_" + value)
    with patch.object(Path, "resolve", return_value=Path("never-created.inp")):
        try:
            _non_model_path("alias.json")
        except ValueError:
            results.append("resolved_model_alias_rejected")
        else:
            raise AssertionError("resolved model alias was not blocked")
    with TemporaryDirectory(prefix="rig-njc-boundary-json-") as directory:
        path = Path(directory) / "internal.json"
        write_json(path, {"internal": True})
        if read_json(path) != {"internal": True} or len(digest(path)) != 64:
            raise AssertionError("internal JSON helpers failed")
        results.append("internal_json_roundtrip")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    report = audit_scripts()
    if args.self_test:
        report["self_tests"] = self_test()
    if args.output:
        write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
