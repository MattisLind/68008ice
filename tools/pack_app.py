#!/usr/bin/env python3
"""Package a fixed-address, freestanding Cortex-M33 application and embed it."""
import pathlib
import struct
import sys
import zlib

raw, output, app = sys.argv[1:]
code = pathlib.Path(raw).read_bytes()
assert 0 < len(code) <= 16384
image = struct.pack('<7I', 0x41505031, 2, int(app), 0x20030000, 1,
                    len(code), zlib.crc32(code)) + code
pathlib.Path(output + '.app').write_bytes(image)
pathlib.Path(output + '.h').write_text(
    f'static const unsigned char app_image_{app}[] __attribute__((aligned(4)))={{' +
    ','.join(str(b) for b in image) + '};\n')
