"""Exercise the firmware ring policy and raw capture/VCD integrity."""
import ctypes
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from ice import CAPTURE_FIELDS, capture_vcd, validate_capture


class Window(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint32) for n in
                "capacity pre next count trigger post_left total".split()] + [
                    ("triggered", ctypes.c_bool), ("done", ctypes.c_bool)]


class CaptureWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        binary = Path(cls.temp.name) / "window.so"
        subprocess.run(["cc", "-shared", "-fPIC", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "firmware/dispatcher/capture_window.c"), "-o", str(binary)], check=True)
        cls.lib = ctypes.CDLL(str(binary))
        cls.lib.capture_window_init.argtypes = [ctypes.POINTER(Window), ctypes.c_uint32, ctypes.c_uint32]
        cls.lib.capture_window_push.argtypes = [ctypes.POINTER(Window), ctypes.c_bool]
        cls.lib.capture_window_push.restype = ctypes.c_uint32
        for name in ("capture_window_start", "capture_window_trigger"):
            getattr(cls.lib, name).argtypes = [ctypes.POINTER(Window)]
            getattr(cls.lib, name).restype = ctypes.c_uint32
        cls.lib.capture_timing_window.argtypes = [ctypes.POINTER(ctypes.c_uint32)] + [ctypes.c_uint32]*7 + [ctypes.POINTER(ctypes.c_uint32)]
        cls.lib.capture_timing_window.restype = ctypes.c_bool

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def make(self, capacity, percent):
        w = Window()
        self.assertTrue(self.lib.capture_window_init(ctypes.byref(w), capacity, percent))
        return w

    def push(self, w, match=False):
        return self.lib.capture_window_push(ctypes.byref(w), match)

    def test_wrapped_history_and_exact_trigger_positions(self):
        for capacity in (1, 2, 7, 10, 99, 100, 1024, 65536):
            for percent in (10, 50, 90):
                with self.subTest(capacity=capacity, percent=percent):
                    w = self.make(capacity, percent)
                    ring = [None] * capacity
                    trigger = capacity * 3 + 17
                    for seq in range(trigger + capacity - w.pre):
                        slot = self.push(w, seq == trigger)
                        ring[slot] = seq
                    self.assertTrue(w.done)
                    self.assertEqual(w.count, capacity)
                    self.assertEqual(self.lib.capture_window_trigger(ctypes.byref(w)), capacity*percent//100)
                    start = self.lib.capture_window_start(ctypes.byref(w))
                    ordered = ring[start:] + ring[:start]
                    self.assertEqual(ordered, list(range(trigger-w.pre, trigger+capacity-w.pre)))
                    self.assertEqual(self.push(w, True), 0xffffffff)

    def test_waits_for_history_when_match_already_present(self):
        w = self.make(100, 90)
        for _ in range(90):
            self.push(w, True)
            self.assertFalse(w.triggered)
        self.push(w, True)
        self.assertTrue(w.triggered)
        for _ in range(9):
            self.push(w)
        self.assertTrue(w.done)
        self.assertEqual(self.lib.capture_window_trigger(ctypes.byref(w)), 90)

    def test_stop_retains_partial_before_and_after_trigger(self):
        w = self.make(100, 10)
        for _ in range(3):
            self.push(w)
        self.assertEqual(w.count, 3)
        self.assertEqual(self.lib.capture_window_trigger(ctypes.byref(w)), 0xffffffff)
        for _ in range(7):
            self.push(w)
        self.push(w, True)
        for _ in range(4):
            self.push(w)
        self.assertEqual(w.count, 15)
        self.assertEqual(self.lib.capture_window_trigger(ctypes.byref(w)), 10)
        self.assertFalse(w.done)

    def test_bounds(self):
        for capacity, percent in ((0, 10), (65537, 50), (100, 0), (100, 100), (100, 11)):
            self.assertFalse(self.lib.capture_window_init(ctypes.byref(Window()), capacity, percent))

    def test_partial_discards_history_beyond_selected_pretrigger(self):
        w = self.make(128, 10)
        ring = [None]*128
        for seq in range(32):
            ring[self.push(w, seq == 16)] = seq
        self.assertEqual(w.count, 28)
        self.assertEqual(self.lib.capture_window_trigger(ctypes.byref(w)), 12)
        start = self.lib.capture_window_start(ctypes.byref(w))
        self.assertEqual([ring[(start+i)%128] for i in range(w.count)], list(range(4, 32)))

    def test_hardware_trigger_window_is_exact_across_ring_wrap(self):
        for edge in (12, 4000, 8185):
            for percent in (10, 50, 90):
                ring = (ctypes.c_uint32*8192)(*([1 << 29]*8192))
                for at in range(50):
                    ring[(edge+at)%8192] = 0
                pre = 4096*percent//100
                start = ctypes.c_uint32()
                self.assertTrue(self.lib.capture_timing_window(ring, 8192, (edge+7)%8192,
                    (edge+4096-pre+80)%8192, 4096, pre, 29, 0, ctypes.byref(start)))
                self.assertEqual((start.value+pre)%8192, edge)

    def test_hardware_trigger_refuses_missing_ambiguous_or_incomplete_windows(self):
        ring = (ctypes.c_uint32*8192)(*([1 << 29]*8192))
        start = ctypes.c_uint32()
        def locate(end=5000):
            return self.lib.capture_timing_window(ring, 8192, 3007, end, 4096, 2048, 29, 0, ctypes.byref(start))
        self.assertFalse(locate())
        ring[3000] = 0
        self.assertFalse(locate(end=3010))
        ring[3010] = 0
        self.assertFalse(locate(end=5200))


def record(raw, count, state=True, **updates):
    r = dict(zip(CAPTURE_FIELDS, [0x43415032, 1, 0, 0, 5 if state else 2, count,
                                 12 if state else 4, 150000000, 0xffffffff, 0, 2,
                                 len(raw), zlib.crc32(raw), max(1, count), 50, 0]))
    r.update(updates)
    return r


class VCD(unittest.TestCase):
    def test_memory_timing_is_uniform_with_bus_names(self):
        raw = struct.pack("<2I", 0xf0000000, 0xd0000000)
        r = record(raw, 2, state=False, app=4, flags=17, trigger=1)
        vcd = capture_vcd(r, raw)
        self.assertIn(b"$var wire 20 a A", vcd)
        self.assertIn(b"$var wire 1 ds DS_N", vcd)
        self.assertIn(b"#6666\n1t", vcd)
        for updates in ({"app": 2}, {"capacity": 4097}, {"hz": 1000000}, {"stride": 12}):
            with self.assertRaises(ValueError):
                validate_capture(dict(r, **updates))

    def test_state_timestamps_include_long_idle_gap_and_trigger(self):
        raw = struct.pack("<9I", 0x31234567, 100, 0, 0x71234568, 175, 0, 0x11234569, 150000100, 0)
        r = record(raw, 3, trigger=1, flags=1)
        vcd = capture_vcd(r, raw).decode()
        self.assertIn("#0\n0t", vcd)
        self.assertIn("#500000\n1t", vcd)
        self.assertIn("#1000000000000", vcd)
        self.assertIn("$var wire 20 a A", vcd)

    def test_timing_upper_bank_and_single_sample(self):
        raw = struct.pack("<I", 0x1001)
        vcd = capture_vcd(record(raw, 1, state=False, bank=1, trigger=0, flags=1), raw)
        self.assertIn(b"GPIO44", vcd)
        self.assertIn(b"#0\n1t", vcd)
        self.assertIn(b"1g44", vcd)

    def test_empty_partial(self):
        self.assertTrue(capture_vcd(record(b"", 0), b"").endswith(b"#0\n0t\n"))

    def test_corruption_bounds_and_nonmonotonic_time(self):
        raw = struct.pack("<6I", 0, 100, 0, 1, 99, 0)
        with self.assertRaises(ValueError):
            capture_vcd(record(raw, 2), raw)
        raw = struct.pack("<I", 7)
        r = record(raw, 1, state=False)
        with self.assertRaises(ValueError):
            capture_vcd(r, b"\0"*4)
        for updates in ({"capacity": 65537}, {"count": 2}, {"trigger": 1, "flags": 1},
                        {"stride": 12}, {"pre_percent": 20}, {"flags": 1}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                validate_capture(dict(r, **updates))


if __name__ == "__main__":
    unittest.main()
