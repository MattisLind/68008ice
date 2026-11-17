"""Execute the actual portable C reset/STOP interpreter with a recording bus."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from cpu_check import verify_boot_trace


class CPU(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in "version state ssp pc sr opcode instructions reads resets fault address fc reset_seen halt_asserted reset_level halt_level".split()] + [("d", C.c_uint32*8), ("a", C.c_uint32*8), ("usp", C.c_uint32), ("writes", C.c_uint32), ("instruction_pc", C.c_uint32)]


class Interpreter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        binary = Path(cls.temp.name) / "cpu.so"
        subprocess.run(["cc", "-shared", "-fPIC", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "firmware/dispatcher/cpu68008.c"), "-o", str(binary)], check=True)
        cls.lib = C.CDLL(str(binary))
        cls.callback = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_uint32, C.c_uint32, C.POINTER(C.c_uint8))
        cls.lib.cpu68008_init.argtypes = [C.POINTER(CPU)]
        for name in ("cpu68008_reset", "cpu68008_step"):
            getattr(cls.lib, name).argtypes = [C.POINTER(CPU), cls.callback, C.c_void_p]
            getattr(cls.lib, name).restype = C.c_int

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.cpu = CPU()
        self.lib.cpu68008_init(C.byref(self.cpu))
        self.memory = bytearray(1024)
        self.memory[:8] = bytes.fromhex("00000400 00000100")
        self.memory[0x100:0x106] = bytes.fromhex("4e72 2700 4e71")
        self.accesses = []
        self.fail_address, self.failure = None, 0

        def read(ctx, address, fc, value):
            self.accesses.append((address, fc))
            if address == self.fail_address:
                return self.failure
            value[0] = self.memory[address % len(self.memory)]
            return 0

        self.read = self.callback(read)

    def reset(self):
        return self.lib.cpu68008_reset(C.byref(self.cpu), self.read, None)

    def step(self):
        return self.lib.cpu68008_step(C.byref(self.cpu), self.read, None)

    def test_reset_then_stop_fetches_only_external_bytes(self):
        self.assertEqual(self.cpu.state, 0)
        self.assertEqual(self.accesses, [])
        self.assertEqual(self.reset(), 0)
        self.assertEqual((self.cpu.ssp, self.cpu.pc, self.cpu.sr), (0x400, 0x100, 0x2700))
        self.assertEqual(self.step(), 0)
        self.assertEqual((self.cpu.state, self.cpu.pc, self.cpu.instructions), (3, 0x104, 1))
        self.assertEqual(self.cpu.halt_asserted, 0)
        self.assertEqual(self.accesses, [(a, 6) for a in [*range(8), *range(0x100, 0x104)]])
        self.step()
        self.assertEqual(len(self.accesses), 12)

    def test_nop_before_stop_and_new_reset(self):
        self.memory[0x100:0x106] = bytes.fromhex("4e71 4e72 2700")
        self.reset(); self.step()
        self.assertEqual((self.cpu.state, self.cpu.pc), (2, 0x102))
        self.step()
        self.assertEqual((self.cpu.state, self.cpu.pc, self.cpu.instructions), (3, 0x106, 2))
        self.reset()
        self.assertEqual((self.cpu.state, self.cpu.pc, self.cpu.resets), (2, 0x100, 2))

    def test_registers_preserved_and_external_address_wraps_at_20_bits(self):
        self.memory[4:8] = bytes.fromhex("fff00100")
        self.reset(); self.step()
        self.assertEqual(self.cpu.pc, 0xfff00104)
        self.assertEqual(self.cpu.state, 3)
        self.assertEqual(self.accesses[-4:], [(a, 6) for a in range(0x100, 0x104)])

    def test_reset_vector_bus_error_asserts_halt(self):
        for address in range(8):
            with self.subTest(address=address):
                self.fail_address, self.failure = address, 4
                self.assertEqual(self.reset(), 4)
                self.assertEqual((self.cpu.state, self.cpu.fault, self.cpu.halt_asserted), (4, 1, 1))
                self.assertEqual(self.cpu.reads, address)

    def test_timeout_abort_reset_and_external_halt_are_distinct(self):
        for failure, state in ((1, 5), (2, 5), (3, 0), (5, 5)):
            with self.subTest(failure=failure):
                self.fail_address, self.failure = 4, failure
                self.assertEqual(self.reset(), failure)
                self.assertEqual(self.cpu.state, state)
                self.assertEqual(self.cpu.halt_asserted, 0)
                self.assertEqual(self.cpu.reads, 4)

    def test_program_bus_error_is_not_mislabeled_as_double_fault(self):
        self.reset()
        self.fail_address, self.failure = 0x100, 4
        self.assertEqual(self.step(), 4)
        self.assertEqual((self.cpu.state, self.cpu.halt_asserted), (5, 0))

    def test_odd_pc_and_unsupported_opcode_fail_without_false_stop(self):
        self.memory[7] = 1
        self.reset()
        self.assertEqual((self.cpu.state, self.cpu.fault), (5, 2))
        self.assertEqual(len(self.accesses), 8)
        self.memory[7] = 0
        self.memory[0x100:0x102] = bytes.fromhex("4afc")
        self.reset(); self.step()
        self.assertEqual((self.cpu.state, self.cpu.fault), (5, 3))
        self.assertEqual(self.cpu.instructions, 0)

    def test_stop_sr_and_extension_failure(self):
        self.reset()
        self.fail_address, self.failure = 0x103, 1
        self.assertEqual(self.step(), 1)
        self.assertEqual(self.cpu.state, 5)
        self.fail_address = None
        self.memory[0x102:0x104] = bytes.fromhex("a700")
        self.reset(); self.step()
        self.assertEqual((self.cpu.state, self.cpu.fault), (5, 4))


class PhysicalTrace(unittest.TestCase):
    def test_reset_program_trace_and_faults(self):
        rom = bytearray(1024)
        rom[:8] = bytes.fromhex("00000400 00000100")
        rom[0x100:0x104] = bytes.fromhex("4e72 2700")
        addresses = [*range(8), *range(0x100, 0x104)]
        words = [a | (rom[a] << 20) | (7 << 28) for a in addresses]
        raw = lambda values: b"".join(struct.pack("<3I", v, i + 1, 0) for i, v in enumerate(values))
        self.assertEqual(verify_boot_trace(raw(words), rom, "stop"), addresses)
        # AS may still be LOW in the selected DS-release snapshot.
        self.assertEqual(verify_boot_trace(raw([words[0] & ~(1 << 28)] + words[1:]), rom, "stop"), addresses)
        for broken in (words[1:], words + words[-1:], [words[0] ^ (1 << 20)] + words[1:],
                       [words[0] ^ (1 << 30)] + words[1:], [words[0] | (1 << 31)] + words[1:],
                       [words[0] & ~(1 << 29)] + words[1:]):
            with self.assertRaises(ValueError):
                verify_boot_trace(raw(broken), rom, "stop")
