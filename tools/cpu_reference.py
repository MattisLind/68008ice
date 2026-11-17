#!/usr/bin/env python3
"""Compare implemented instruction forms against pinned Musashi in isolated RAM.

Run --prepare once to fetch/build the independent test-only reference. It is
never linked into RP2350 firmware. The matrix compares D0-D7, A0-A7, PC, SR and
every byte in a 1 MiB RAM after one instruction, independently of PIO timing.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/tests"))
from test_cpu68008 import CPU

REVISION = "313ebf1bd9f4d0d93341eb5ce21fd8a119e9dbdd"
ARCHIVE_SHA256 = "8bed9e28e7e5377256d41aff80a99c9e917a24e7392d9219e1c45c40ad4000e5"
BUILD = ROOT / "build/cpu-reference"
SOURCE = BUILD / ("Musashi-" + REVISION)
LIBRARY = BUILD / "reference.so"
MANIFEST = BUILD / "core-sources.json"


def source_fingerprint():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (ROOT / "firmware/dispatcher/cpu68008.c", ROOT / "firmware/dispatcher/cpu68008.h",
             ROOT / "tools/tests/musashi_adapter.c")}


def require_current_library():
    if not LIBRARY.exists() or not MANIFEST.exists() or json.loads(MANIFEST.read_text()) != source_fingerprint():
        raise ValueError("Run python3 tools/cpu_reference.py --prepare to build the current CPU core/reference")


def prepare():
    BUILD.mkdir(parents=True, exist_ok=True)
    archive = BUILD / "musashi.tar.gz"
    if not archive.exists():
        urllib.request.urlretrieve(f"https://codeload.github.com/kstenerud/Musashi/tar.gz/{REVISION}", archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Musashi archive hash mismatch")
    if not SOURCE.exists():
        with tarfile.open(archive) as bundle:
            for member in bundle.getmembers():
                if member.issym() or member.islnk() or not (BUILD / member.name).resolve().is_relative_to(BUILD.resolve()):
                    raise ValueError("Unsafe archive entry")
            bundle.extractall(BUILD, filter="data")
    # Preserve and inspect the upstream MIT notices in m68k.h/source files.
    subprocess.run(["cc", "-O2", "m68kmake.c", "-o", "m68kmake"], cwd=SOURCE, check=True)
    subprocess.run([str(SOURCE / "m68kmake")], cwd=SOURCE, check=True)
    subprocess.run(["cc", "-shared", "-fPIC", "-O2", "-DM68K_EMULATE_FC=1", "-I", str(SOURCE), "-I", str(ROOT / "firmware/dispatcher"),
                    str(SOURCE / "m68kcpu.c"), str(SOURCE / "m68kops.c"), str(SOURCE / "m68kdasm.c"),
                    str(SOURCE / "softfloat/softfloat.c"), str(ROOT / "tools/tests/musashi_adapter.c"),
                    str(ROOT / "firmware/dispatcher/cpu68008.c"), "-lm", "-o", str(LIBRARY)], check=True)
    MANIFEST.write_text(json.dumps(source_fingerprint(), indent=2) + "\n")


def modes(size, destination=False, btst=False, dynamic=False):
    result = [(m, r) for m in range(7) for r in range(8) if not (m == 1 and (size == 1 or btst))]
    result += [(7, r) for r in range(2 if destination else 5)]
    if btst and not dynamic and (7, 4) in result:
        result.remove((7, 4))
    return result


def extension(mode, reg, size, value=0x89abcdef, index=0x7000):
    if mode == 5: return struct.pack(">H", 0xffe0)
    if mode == 6 or (mode, reg) == (7, 3): return struct.pack(">H", index | 0xf0)
    if mode == 7:
        if reg == 0: return bytes.fromhex("f000")
        if reg == 1: return bytes.fromhex("00005000")
        if reg == 2: return bytes.fromhex("0080")
        if reg == 4: return value.to_bytes(4, "big") if size == 4 else (value & 0xffff).to_bytes(2, "big")
    return b""


class Matrix:
    def __init__(self):
        self.lib = C.CDLL(str(LIBRARY))
        self.lib.compare_instruction.argtypes = [C.c_void_p, C.POINTER(CPU), C.c_void_p, C.c_void_p]
        self.ram = bytearray(bytes(range(256)) * 4096)
        self.buffer = (C.c_uint8 * len(self.ram)).from_buffer(self.ram)
        self.expected = (C.c_uint32 * 18)()
        self.difference = C.c_uint32()
        self.counts = {}

    def check(self, family, opcode, extra=b"", value=0x89abcdef, sr=0x271f, pc=0x200, d_override=None):
        c = CPU(version=2, state=2, pc=pc, sr=sr, ssp=0x2e00)
        for i in range(8): c.d[i] = value; c.a[i] = 0x2000 + i * 0x200
        c.d[7] = 0xfffffff0  # Aligned, negative word/long index; preserved in expected state.
        for reg, data in (d_override or {}).items(): c.d[reg] = data
        code = struct.pack(">H", opcode) + extra
        original = self.ram[pc:pc+len(code)]
        self.ram[pc:pc+len(code)] = code
        result = self.lib.compare_instruction(self.buffer, C.byref(c), self.expected, C.byref(self.difference))
        self.ram[pc:pc+len(code)] = original
        if result:
            actual = dict(d=list(c.d), a=list(c.a), pc=c.pc, sr=c.sr, state=c.state, fault=c.fault)
            expected = dict(d=list(self.expected[:8]), a=list(self.expected[8:16]), pc=self.expected[16], sr=self.expected[17])
            raise AssertionError(json.dumps(dict(family=family, code=code.hex(), flags=hex(sr), result=result,
                                                memory_difference=hex(self.difference.value), actual=actual, expected=expected), indent=2))
        self.counts[family] = self.counts.get(family, 0) + 1

    def run(self):
        for size, field in ((1, 0), (2, 1), (4, 2)):
            for mode, reg in modes(size, destination=True, btst=True):
                for flags in (0, 15, 16, 31):
                    self.check("CLR", 0x4200 | field << 6 | mode << 3 | reg, extension(mode, reg, size), sr=0x2700 | flags)
        # Complete legal source/destination EA cross-product, all size forms.
        for size, field in ((1, 1), (2, 3), (4, 2)):
            for sm, sr in modes(size):
                for dm, dr in modes(size, destination=True):
                    for value in (0, 0x80008000, 0xffffffff):
                        self.check("MOVE/MOVEA", field << 12 | dr << 9 | dm << 6 | sm << 3 | sr,
                                   extension(sm, sr, size, value) + extension(dm, dr, size, value), value=value)
        for dynamic in (False, True):
            for mode, reg in modes(1, btst=True, dynamic=dynamic):
                for source in (range(8) if dynamic else (0,)):
                    for bit in (0, 7, 8, 31, 32, 255, 0xffffffff):
                        extra = b"" if dynamic else struct.pack(">H", bit & 255)
                        op = (0x100 | source << 9 if dynamic else 0x800) | mode << 3 | reg
                        self.check("BTST", op, extra + extension(mode, reg, 1), value=bit)
        # All CCR combinations and byte/word branch encodings, including BSR.
        for cc in range(16):
            for flags in range(32):
                for displacement in (-128, -2, 2, 126, -32768, 0, 32766):
                    word = displacement not in (-128, -2, 2, 126)
                    self.check("BRA/BSR/Bcc", 0x6000 | cc << 8 | (0 if word else displacement & 255),
                               struct.pack(">h", displacement) if word else b"", sr=0x2700 | flags, pc=0x40000)
        for mode, reg in [(m, r) for m in (2, 5, 6) for r in range(8)] + [(7, r) for r in range(4)]:
            self.check("JMP", 0x4ec0 | mode << 3 | reg, extension(mode, reg, 4))
        # Exercise every brief-index register and W/L selector for An and PC bases.
        for base_mode, base_reg in [(6, r) for r in range(8)] + [(7, 3)]:
            for address_index in (0, 1):
                for index_reg in range(8):
                    for long_index in (0, 1):
                        index = address_index << 15 | index_reg << 12 | long_index << 11
                        for size, field in ((1, 1), (2, 3), (4, 2)):
                            self.check("indexed MOVE", field << 12 | base_mode << 3 | base_reg,
                                       extension(base_mode, base_reg, size, index=index), value=0x80008000)
        for size, field in ((1, 0), (2, 1), (4, 2)):
            sign = 1 << (size*8-1)
            for mode, reg in modes(size, destination=True):
                for sub in (0, 1):
                    for amount in range(1, 9):
                        for value in (0, 1, sign-1, sign, (sign<<1)-1):
                            self.check("ADDQ/SUBQ", 0x5000 | (amount&7)<<9 | sub<<8 | field<<6 | mode<<3 | reg,
                                       extension(mode, reg, size), value=value)
            for mode, reg in modes(size, destination=True, btst=True):
                for immediate in (0, sign-1, sign, (sign<<1)-1):
                    self.check("ANDI", 0x0200 | field<<6 | mode<<3 | reg,
                               extension(7,4,size,immediate)+extension(mode,reg,size))
        for flags in range(32):
            for immediate in range(256):
                self.check("ANDI CCR",0x023c,struct.pack(">H",immediate),sr=0x2700|flags)
            for immediate in (0xffff,0x2700,0x071f,0xffef):
                self.check("ANDI SR",0x027c,struct.pack(">H",immediate),sr=0x2700|flags)
        for size, field in ((2,0), (4,1)):
            for mode, reg in modes(size):
                for dst in range(8):
                    self.check("SUBA",0x90c0 | dst<<9 | field<<8 | mode<<3 | reg,extension(mode,reg,size))
        for cc in range(16):
            for flags in range(32):
                for reg in range(8):
                    for counter in (0,1,0xffff,0xabcd0001):
                        self.check("DBcc",0x50c8 | cc<<8 | reg,bytes.fromhex("fff0"),sr=0x2700|flags,
                                   d_override={reg:counter})
        for size, field in ((1,0),(2,1),(4,2)):
            for left in (0,1):
                for dst in range(8):
                    for source in range(8):
                        self.check("LSR/LSL immediate",0xe008 | source<<9 | left<<8 | field<<6 | dst)
                        for count in (0,1,8,16,32,33,63,64,0xffffffff):
                            self.check("LSR/LSL register",0xe028 | source<<9 | left<<8 | field<<6 | dst,
                                       d_override={source:count})
            for mode, reg in modes(2,destination=True,btst=True):
                if mode==0:continue
                for left in (0,1):
                    self.check("LSR/LSL memory",0xe2c0 | left<<8 | mode<<3 | reg,extension(mode,reg,2))
        return dict(reference="Musashi 68000 instruction semantics", revision=REVISION,
                    archive_sha256=ARCHIVE_SHA256, cases=self.counts, total=sum(self.counts.values()), passed=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--output", type=Path, default=BUILD / "report.json")
    args = parser.parse_args()
    if args.prepare: prepare()
    require_current_library()
    result = Matrix().run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
