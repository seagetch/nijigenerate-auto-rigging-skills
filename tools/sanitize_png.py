#!/usr/bin/env python3
"""Remove PNG text/EXIF/time metadata without recompressing image data."""
import argparse
from pathlib import Path
import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"
PRIVATE_CHUNKS = {b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"}


def sanitize(data):
    if not data.startswith(SIGNATURE):
        raise ValueError("Not a PNG")
    output = bytearray(SIGNATURE)
    offset = len(SIGNATURE)
    removed = []
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("Truncated PNG chunk")
        size = struct.unpack_from(">I", data, offset)[0]
        end = offset + size + 12
        if end > len(data):
            raise ValueError("Truncated PNG chunk data")
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:end - 4]
        crc = struct.unpack_from(">I", data, end - 4)[0]
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            raise ValueError("PNG CRC mismatch")
        if kind in PRIVATE_CHUNKS:
            removed.append(kind.decode("ascii"))
        else:
            output.extend(data[offset:end])
        offset = end
        if kind == b"IEND":
            if offset != len(data):
                removed.append("trailing-data")
            return bytes(output), removed
    raise ValueError("Missing PNG end chunk")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--write", action="store_true", help="Remove metadata in place; otherwise check only")
    args = parser.parse_args()
    dirty = 0
    for file in args.files:
        if file.is_symlink():
            raise ValueError("Refusing a symlink")
        clean, removed = sanitize(file.read_bytes())
        if removed:
            dirty += 1
            if args.write:
                file.write_bytes(clean)
            print(f"{file.name}: {', '.join(removed)}")
    print(f"PNG files checked: {len(args.files)}; files with private metadata: {dirty}")
    return int(bool(dirty and not args.write))


if __name__ == "__main__":
    raise SystemExit(main())
