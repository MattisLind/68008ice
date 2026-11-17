"""ROM upload bounds, incomplete transfer and integrity validation in real C."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[2]


class Image(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in "version capacity bytes crc used ready".split()]


class Upload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        binary = Path(cls.temp.name) / "image.so"
        subprocess.run(["cc", "-shared", "-fPIC", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "firmware/dispatcher/memory_image.c"), str(ROOT / "firmware/dispatcher/protocol.c"),
                        "-o", str(binary)], check=True)
        cls.lib = C.CDLL(str(binary))
        cls.lib.memory_image_begin.argtypes = [C.POINTER(Image), C.c_void_p, C.c_uint32, C.c_uint32]
        cls.lib.memory_image_write.argtypes = [C.POINTER(Image), C.c_void_p, C.c_uint32, C.c_void_p, C.c_uint32]
        cls.lib.memory_image_commit.argtypes = [C.POINTER(Image), C.c_void_p]

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_upload_crc_bounds_and_recovery(self):
        ram = (C.c_uint8*1048576)(); image = Image()
        data = bytes(range(256))*64
        begin = lambda size, crc: self.lib.memory_image_begin(C.byref(image), ram, size, crc)
        write = lambda offset, chunk: self.lib.memory_image_write(C.byref(image), ram, offset, chunk, len(chunk))
        commit = lambda: self.lib.memory_image_commit(C.byref(image), ram)
        for size in (0, 7, 1048577): self.assertEqual(begin(size, 0), 1)
        self.assertEqual(begin(len(data), zlib.crc32(data)), 0)
        self.assertEqual(commit(), 3)
        self.assertEqual(write(1, b"x"), 1)
        self.assertEqual(write(0, b"x"*253), 1)
        for at in range(0, len(data), 252): self.assertEqual(write(at, data[at:at+252]), 0)
        ram[4] ^= 1
        self.assertEqual(commit(), 3)
        self.assertEqual(image.ready, 0)
        ram[4] ^= 1
        self.assertEqual(commit(), 0)
        self.assertEqual(image.ready, 1)
        self.assertEqual(bytes(ram[:len(data)]), data)
        self.assertEqual(write(len(data), b"x"), 1)
        self.assertEqual(begin(8, zlib.crc32(bytes(8))), 0)
        self.assertEqual(image.ready, 0)
        self.assertEqual(bytes(ram[:len(data)]), bytes(len(data)))
