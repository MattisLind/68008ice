"""Focused bus/fault tests supplement the independent addressing-mode matrix."""
import ctypes as C
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from test_cpu68008 import CPU

ROOT = Path(__file__).resolve().parents[2]


class Instructions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        binary = Path(cls.temp.name) / "cpu.so"
        subprocess.run(["cc", "-shared", "-fPIC", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "firmware/dispatcher/cpu68008.c"), "-o", str(binary)], check=True)
        cls.lib = C.CDLL(str(binary))
        cls.read_type = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_uint32, C.c_uint32, C.POINTER(C.c_uint8))
        cls.write_type = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint8)
        cls.lib.cpu68008_execute.argtypes = [C.POINTER(CPU), cls.read_type, cls.write_type, C.c_void_p]
        cls.lib.cpu68008_reset.argtypes = [C.POINTER(CPU), cls.read_type, C.c_void_p]

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def setUp(self):
        self.ram = bytearray(1048576)
        self.cpu = CPU(version=2, state=2, pc=0x200, sr=0x271f, ssp=0x4000)
        self.cpu.a[7] = 0x4000
        self.events = []
        self.fail_address = None

        def read(ctx, a, fc, value):
            self.events.append(("r", a, fc))
            if a == self.fail_address: return 4
            value[0] = self.ram[a]
            return 0

        def write(ctx, a, fc, value):
            self.events.append(("w", a, fc))
            if a == self.fail_address: return 4
            self.ram[a] = value
            return 0

        self.read, self.write = self.read_type(read), self.write_type(write)

    def execute(self, code):
        code = bytes.fromhex(code)
        self.ram[self.cpu.pc:self.cpu.pc+len(code)] = code
        return self.lib.cpu68008_execute(C.byref(self.cpu), self.read, self.write, None)

    def test_real_rom_first_five_normal_and_taken(self):
        rom = (ROOT / "roms/abc1600/ABC1600ROM.bin").read_bytes()
        for cause, pcs, opcodes, d7 in (
            (2, [0x48, 0x4e, 0x52, 0x54, 0x56], [0x4287, 0x1e39, 0x0807, 0x66ec, 0x4286], 2),
            (6, [0x48, 0x4e, 0x52, 0x40, 0x10000], [0x4287, 0x1e39, 0x0807, 0x66ec, 0x4ef9], 6)):
            with self.subTest(cause=cause):
                self.ram[:len(rom)] = rom; self.ram[0x80007] = cause
                self.cpu = CPU(version=2, state=0)
                self.assertEqual(self.lib.cpu68008_reset(C.byref(self.cpu), self.read, None), 0)
                self.assertEqual((self.cpu.pc, self.cpu.ssp, self.cpu.a[7]), (0x46, 0x40000, 0x40000))
                for i, (pc, opcode) in enumerate(zip(pcs, opcodes)):
                    self.assertEqual(self.lib.cpu68008_execute(C.byref(self.cpu), self.read, self.write, None), 0)
                    self.assertEqual((self.cpu.pc, self.cpu.opcode, self.cpu.instructions), (pc, opcode, i+1))
                self.assertEqual(self.cpu.d[7], d7)
                self.assertIn(("r", 0x80007, 5), self.events)
                self.assertEqual(self.cpu.writes, 0)

    def test_clr_memory_reads_before_write_and_preserves_extend(self):
        self.cpu.a[0] = 0x300
        self.ram[0x300:0x304] = bytes.fromhex("12345678")
        self.execute("4298")  # CLR.L (A0)+
        self.assertEqual(self.events[2:], [(d, a, 5) for d in ("r", "w") for a in range(0x300, 0x304)])
        self.assertEqual(self.ram[0x300:0x304], bytes(4))
        self.assertEqual((self.cpu.a[0], self.cpu.sr), (0x304, 0x2714))

    def test_predecrement_long_write_order_and_a7_byte_stride(self):
        self.cpu.d[0] = 0x12345678
        self.cpu.a[0] = 0x304
        self.execute("2100")  # MOVE.L D0,-(A0)
        self.assertEqual(self.events[2:], [("w", a, 5) for a in (0x302, 0x303, 0x300, 0x301)])
        self.assertEqual(self.ram[0x300:0x304], bytes.fromhex("12345678"))
        self.execute("1f00")  # MOVE.B D0,-(A7)
        self.assertEqual((self.cpu.a[7], self.cpu.ssp), (0x3ffe, 0x3ffe))
        self.assertEqual(self.ram[0x3ffe], 0x78)

    def test_pc_relative_data_uses_program_fc_and_abs_short_sign_extends(self):
        self.ram[0x204:0x206] = bytes.fromhex("a55a")
        self.execute("303a0002")  # MOVE.W (2,PC),D0, EA is extension-word PC + 2.
        self.assertEqual(self.cpu.d[0], 0xa55a)
        self.assertEqual(self.events[-2:], [("r", 0x204, 6), ("r", 0x205, 6)])
        self.ram[0xff000] = 0xa5
        self.execute("1038f000")
        self.assertEqual(self.cpu.d[0]&255, 0xa5)
        self.assertEqual(self.events[-1], ("r", 0xff000, 5))

    def test_invalid_modes_and_odd_operands_stop_without_writes(self):
        for opcode in ("4208", "427a0000", "08080000", "4ed8", "1040"):
            self.cpu.state = 2; self.cpu.pc = 0x200; self.events.clear()
            self.execute(opcode)
            self.assertEqual((self.cpu.state, self.cpu.fault), (5, 3), opcode)
            self.assertFalse(any(d == "w" for d, _, _ in self.events))
        self.cpu.state = 2; self.cpu.pc = 0x200; self.cpu.a[0] = 0x301
        self.execute("3010")
        self.assertEqual((self.cpu.state, self.cpu.fault), (5, 2))

    def test_operand_bus_error_is_not_a_reset_double_fault(self):
        self.cpu.a[0] = 0x300; self.fail_address = 0x300
        self.assertEqual(self.execute("3010"), 4)
        self.assertEqual((self.cpu.state, self.cpu.fault, self.cpu.instructions, self.cpu.halt_asserted), (5, 1, 0, 0))

    def test_bsr_pushes_return_pc_and_user_function_codes(self):
        self.cpu.sr = 0x0700
        self.execute("61000010")
        self.assertEqual(self.cpu.pc, 0x212)
        self.assertEqual((self.cpu.a[7], self.cpu.usp), (0x3ffc, 0x3ffc))
        self.assertEqual(self.ram[0x3ffc:0x4000], struct.pack(">I", 0x204))
        self.assertEqual(self.events[:4], [("r", a, 2) for a in range(0x200, 0x204)])
        self.assertEqual(self.events[4:], [("w", a, 1) for a in (0x3ffe, 0x3fff, 0x3ffc, 0x3ffd)])
