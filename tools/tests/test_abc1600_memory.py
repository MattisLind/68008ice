"""Portable ABC1600 MAC and generic memory behavior, without hardware/MAME build."""
import ctypes as C
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tools"))
from abc1600_model import ModelState
from test_memory_image import Image

class MemoryModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();binary=Path(cls.temp.name)/"models.so"
        subprocess.run(["cc","-shared","-fPIC","-std=c11","-Wall","-Wextra","-Werror",
                        str(ROOT/"firmware/dispatcher/abc1600_memory.c"),str(ROOT/"firmware/dispatcher/generic_memory.c"),
                        "-o",str(binary)],check=True)
        cls.lib=C.CDLL(str(binary));cls.lib.abc1600_memory_init.argtypes=[C.POINTER(ModelState)]
        cls.lib.abc1600_memory_access.argtypes=[C.POINTER(ModelState),C.c_void_p,C.c_void_p,C.c_uint32,C.c_uint32,C.c_bool,C.POINTER(C.c_uint8)]
        cls.lib.generic_memory_access.argtypes=[C.POINTER(Image),C.c_void_p,C.c_uint32,C.c_uint32,C.c_bool,C.POINTER(C.c_uint8)]
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.model=ModelState();self.lib.abc1600_memory_init(C.byref(self.model))
        self.rom=(C.c_uint8*16384).from_buffer_copy((ROOT/"roms/abc1600/ABC1600ROM.bin").read_bytes())
        self.ram=(C.c_uint8*1048576)()
    def access(self,a,write=False,value=0,fc=5):
        byte=C.c_uint8(value)
        status=self.lib.abc1600_memory_access(C.byref(self.model),self.rom,self.ram,a,fc,write,C.byref(byte))
        return status,byte.value
    def test_boot_overlay_mirrors_and_real_cause_register(self):
        for a in (0,6,0x46,0x100):
            for mirror in range(0,0x20000,0x4000):self.assertEqual(self.access(a+mirror,fc=6),(0,self.rom[a]))
        self.assertEqual(self.access(0x80007),(0,2));self.assertEqual(self.model.status.cause_reads,1)
        self.model.status.reset_button=1
        self.assertEqual(self.access(0x80007),(0,3))
    def test_task_segment_page_registers_and_page_high_replication(self):
        self.access(0x80005,True,0xc3)
        self.assertEqual((self.model.status.task,self.model.status.boote,self.model.status.magic),(3,0,0))
        self.access(0x80103,True,0x2a)
        self.assertEqual(self.model.segment[3*32+16],0x2a)
        self.assertEqual(self.access(0x80103),(0,0xaa))
        self.access(0x80100,True,0x42);self.access(0x80101,True,0x35)
        self.assertEqual(self.model.page[0x2a*16],0x4235)
        self.assertEqual(self.access(0x80100),(0,0x7e))
        self.assertEqual(self.access(0x80101),(0,0x35))
    def configure_ram(self,high=0x40):
        self.access(0x80003,True,0) # Task-zero segment-zero -> page block zero.
        self.access(0x80000,True,high);self.access(0x80001,True,1) # Physical page 1.
    def test_rom_overlay_reads_and_translated_writes_are_distinct(self):
        self.configure_ram()
        self.assertEqual(self.access(0,True,0xa5)[0],0)
        self.assertEqual(self.ram[0x800],0xa5)
        self.assertEqual(self.access(0,fc=6),(0,self.rom[0]))
        self.access(0x80005,True,0x80) # Disable overlay, task zero.
        self.assertEqual(self.access(0,fc=6),(0,0xa5))
    def test_protection_and_cause_bits(self):
        self.configure_ram(0)
        self.access(0x80005,True,0x80)
        self.assertEqual(self.access(0,True,99)[0],4)
        self.assertEqual(self.ram[0x800],0)
        self.assertEqual(self.model.status.cause,4)
        self.access(0x80000,True,0xc0)
        self.assertEqual(self.access(0,fc=6)[0],4)
        self.assertEqual(self.access(0x80007),(0,6))
        self.model.status.partst=1
        self.assertEqual(self.access(0x80007),(0,2))
    def test_user_program_mac_read_uses_register_data_decode(self):
        self.access(0x80005,True,0xc1) # Task 1, MAGIC=0, overlay enabled.
        self.model.segment[32]=1;self.model.segment[48]=2
        self.model.page[16]=0x4011;self.model.page[32]=0x4022
        self.assertEqual(self.access(0x80001,fc=6),(0,0x11))
        self.assertEqual(self.access(0x80001,fc=2),(0,0x22))
    def test_generic_memory_has_no_abc1600_registers_or_mirrors(self):
        image=Image(version=1,capacity=1048576,bytes=16384,ready=1)
        data=C.c_uint8(0xa5)
        self.assertEqual(self.lib.generic_memory_access(C.byref(image),self.ram,0x80007,5,True,C.byref(data)),0)
        data.value=0
        self.assertEqual(self.lib.generic_memory_access(C.byref(image),self.ram,0x80007,5,False,C.byref(data)),0)
        self.assertEqual(data.value,0xa5)
        self.assertEqual(self.access(0x80007),(0,2))
        self.assertEqual(self.lib.generic_memory_access(C.byref(image),self.ram,0,5,True,C.byref(data)),4)
