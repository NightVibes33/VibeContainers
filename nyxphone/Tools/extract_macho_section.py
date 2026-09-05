#!/usr/bin/env python3
"""Extract one section from a little-endian 64-bit Mach-O object."""
import struct
import sys
from pathlib import Path

if len(sys.argv) != 4:
    raise SystemExit("usage: extract_macho_section.py OBJECT SECTION OUTPUT")
source, wanted, output = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
data = source.read_bytes()
if len(data) < 32 or struct.unpack_from("<I", data)[0] != 0xFEEDFACF:
    raise SystemExit("input is not a little-endian Mach-O 64 object")
_, _, _, _, ncmds, sizeofcmds, _, _ = struct.unpack_from("<IiiIIIII", data)
offset = 32
limit = offset + sizeofcmds
for _ in range(ncmds):
    if offset + 8 > limit:
        break
    command, command_size = struct.unpack_from("<II", data, offset)
    if command == 0x19:
        section_count = struct.unpack_from("<I", data, offset + 64)[0]
        section_offset = offset + 72
        for _ in range(section_count):
            name = data[section_offset:section_offset + 16].split(b"\0", 1)[0].decode()
            size = struct.unpack_from("<Q", data, section_offset + 40)[0]
            file_offset = struct.unpack_from("<I", data, section_offset + 48)[0]
            if name == wanted:
                payload = data[file_offset:file_offset + size]
                if len(payload) != size:
                    raise SystemExit("section extends beyond object")
                output.write_bytes(payload)
                print(f"{name}: {size} bytes")
                raise SystemExit(0)
            section_offset += 80
    if command_size < 8:
        break
    offset += command_size
raise SystemExit(f"section not found: {wanted}")
