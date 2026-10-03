"""NJC-only subprocess transport, with an offline command-size preflight.

The inspected NJC CLI accepts only a literal ``--json`` argument. It has no
stdin, response-file or JSON-file transport. Oversized requests are rejected
before NJC starts; no HTTP fallback, splitting or automatic retry exists here.
Open/save submit NJC commands only. An acknowledgement is not a proof of a
completed document transition; the caller must verify through NJC resources.
"""
import json
from pathlib import Path
import subprocess
from .data import write_json


COMMAND_LINE_UTF16_LIMIT = 30000  # Conservative policy below Windows' process limit.


class NJCRequestTooLarge(ValueError):
    """The installed client's literal-argument transport cannot carry a request."""


class NJCTransportError(RuntimeError):
    """A single NJC invocation failed or returned an invalid protocol envelope."""


def _compact_numbers(value):
    """Lossless JSON number spelling, still one literal NJC request."""
    if isinstance(value,float) and value.is_integer():return int(value)
    if isinstance(value,list):return [_compact_numbers(v) for v in value]
    if isinstance(value,dict):return {k:_compact_numbers(v) for k,v in value.items()}
    return value


def _strict_json(value):
    def reject_constant(constant):
        raise ValueError(f"NJC returned non-finite JSON constant: {constant}")

    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"NJC returned duplicate JSON field: {key}")
            result[key] = item
        return result

    return json.loads(value, parse_constant=reject_constant, object_pairs_hook=unique)


class Live:
    def __init__(self, executable, journal=None):
        self.executable = str(Path(executable).resolve(strict=True))
        self.journal = Path(journal) if journal else None
        self.sequence = 0

    def _prepare(self, args, data=None):
        if not isinstance(args, (list, tuple)) or not args:
            raise ValueError("NJC arguments must be a nonempty list or tuple of strings")
        if any(not isinstance(arg, str) or "\x00" in arg for arg in args):
            raise ValueError("NJC arguments must be strings without NUL characters")
        command = [self.executable, *args]
        encoded = None
        if data is not None:
            if not isinstance(data, dict):
                raise ValueError("NJC --json input must be an object")
            encoded = json.dumps(_compact_numbers(data), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            command += ["--json", encoded]
        # Count the exact Windows quoting representation and UTF-16 code units,
        # including the terminating NUL. len(str) and sum(argv lengths) miss
        # escaped quotes/backslashes, separating spaces and non-BMP characters.
        units = len(subprocess.list2cmdline(command).encode("utf-16-le")) // 2 + 1
        if units > COMMAND_LINE_UTF16_LIMIT:
            raise NJCRequestTooLarge(
                f"NJC request requires {units} UTF-16 command-line units; supported policy limit is "
                f"{COMMAND_LINE_UTF16_LIMIT}. The inspected NJC supports literal --json only, with no "
                "stdin/JSON-file transport. Request was not sent; HTTP, direct INX access, "
                "request splitting and retries are forbidden fallbacks."
            )
        return command, {"transport": "njc_subprocess", "command_line_utf16_units": units,
                         "command_line_utf16_limit": COMMAND_LINE_UTF16_LIMIT,
                         "json_utf8_bytes": len(encoded.encode("utf-8")) if encoded is not None else 0,
                         "argument_count": len(command), "request_sent": False}

    def preflight(self, args, data=None):
        """Validate one request without starting NJC or performing any operation.

        Batch callers should preflight every payload before their first mutation.
        This checks transport capacity, not model preconditions or permissions.
        """
        return self._prepare(args, data)[1]

    def preflight_call(self, tool_name, **kwargs):
        return self.preflight(["tools", "call", tool_name], kwargs)

    def invoke(self, args, data=None):
        command, _ = self._prepare(args, data)
        try:
            run = subprocess.run(command, capture_output=True, encoding="utf-8", errors="strict",
                                 timeout=120, shell=False, stdin=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired as error:
            raise NJCTransportError("NJC timed out; completion is unknown. Request was not retried.") from error
        except (OSError, UnicodeError) as error:
            raise NJCTransportError(f"NJC subprocess failed; not retried: {error}") from error
        if run.returncode:
            raise NJCTransportError(run.stderr or run.stdout or f"NJC exited with code {run.returncode}")
        try:
            payload = _strict_json(run.stdout)
        except (ValueError, TypeError) as error:
            raise NJCTransportError("NJC returned invalid JSON; completion is unknown. Not retried.") from error
        if not isinstance(payload, dict):
            raise NJCTransportError("NJC returned a non-object JSON-RPC envelope")
        if "error" in payload:
            raise NJCTransportError(payload["error"])
        if "result" not in payload:
            raise NJCTransportError("NJC JSON-RPC response has no result")
        result = payload["result"]
        entries = result.get("content", result.get("contents", [])) if isinstance(result, dict) else []
        if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
            raise NJCTransportError("NJC content is not a list of objects")
        decoded = []
        for entry in entries:
            if "text" in entry:
                try:
                    decoded.append(_strict_json(entry["text"]))
                except json.JSONDecodeError:
                    decoded.append(entry["text"])
                except (ValueError, TypeError) as error:
                    raise NJCTransportError("NJC content contains invalid structured JSON") from error
        output = decoded[0] if len(decoded) == 1 else (decoded or result)
        if self.journal:
            self.journal.mkdir(parents=True, exist_ok=True)
            self.sequence += 1
            write_json(self.journal / f"{self.sequence:06d}.json", {"args": args, "input": data, "output": output})
        nested = output.get("result") if isinstance(output, dict) else None
        if ((isinstance(result, dict) and result.get("isError")) or
            (isinstance(output, dict) and (output.get("succeeded") is False or output.get("status") == "error")) or
            (isinstance(nested, dict) and nested.get("succeeded") is False)):
            raise NJCTransportError(output)
        return output

    def call(self, tool_name, **kwargs):
        return self.invoke(["tools", "call", tool_name], kwargs)

    def read(self, uid):
        return self.invoke(["read", str(uid)])

    def find(self, selector):
        return self.invoke(["find", selector])

    def binding_resources(self):
        """Enumerate live bindings even when resources/list was startup-cached."""
        result = []
        seen = set()
        def visit(item):
            if item.get('typeId') == 'Binding':
                uri = item.get('uri', '')
                if not uri.startswith('resource://nijigenerate/bindings/get?'):
                    raise NJCTransportError('Binding discovery omitted its descriptor URI')
                if uri not in seen:
                    result.append({'uri':uri}); seen.add(uri)
            for child in item.get('children') or []:
                visit(child)
        for item in self.find('Binding')['items']:
            visit(item)
        return result

    def save(self, path):
        return self.call("FileCommand_SaveFile", file=str(Path(path).resolve()))

    def open(self, path):
        # No Python read, parse, existence check or validation of an INX file.
        return self.call("FileCommand_OpenFile", file=str(Path(path).resolve()))


def created_id(result):
    items = result.get("result", {}).get("created", [])
    if len(items) != 1 or "uuid" not in items[0]:
        raise RuntimeError(f"Expected exactly one created resource: {result}")
    return items[0]["uuid"]
