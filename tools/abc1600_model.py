#!/usr/bin/env python3
"""Build the portable ABC1600 model and a test reference from local MAME methods."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import re
import random
import struct
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/"build/abc1600-model"
MAME=ROOT/"mame/src/mame/luxor/abc1600_mmu.cpp"
NATIVE=BUILD/"model.so"
REFERENCE=BUILD/"mame-reference.so"
FIELDS="version task boote magic cause reset_button partst cause_reads segment_writes page_high_writes page_low_writes task_writes ram_reads ram_writes bus_errors unsupported_io last_address last_physical last_fc last_write last_target".split()

class Status(C.Structure):
    _fields_=[(n,C.c_uint32) for n in FIELDS]

class Video(C.Structure):
    _fields_=[(n,C.c_uint16) for n in 'xsize ysize xto xfrom ty fy wrm gmdi'.split()]+[(n,C.c_uint8) for n in 'direction flag clocks_disabled display crtc_address'.split()]+[("crtc",C.c_uint8*32),("ms",C.c_uint8*16),("ds",C.c_uint8*16)]+[(n,C.c_uint32) for n in 'ticks moves busy row column'.split()]

class ModelState(C.Structure):
    _fields_=[("status",Status),("segment",C.c_uint8*1024),("page",C.c_uint16*1024),
              ("cio",C.c_uint8*48),("cio_pointer",C.c_uint8),("cio_state0",C.c_uint8),
              ("cio_output",C.c_uint8*3),("io_reads",C.c_uint32),("io_writes",C.c_uint32),
              ("dart",(C.c_uint8*8)*2),("dart_pointer",C.c_uint8*2),("dart_rr0",C.c_uint8*2),
              ("keyboard_polls",C.c_uint32),("keyboard_tx_count",C.c_uint32),("keyboard_tx",C.c_uint8*256),("video",Video),
              ("scc",(C.c_uint8*16)*2),("scc_pointer",C.c_uint8*2)]

def fingerprint():
    files=[MAME,ROOT/"tools/tests/mame_abc1600_adapter.cpp.in",ROOT/"firmware/dispatcher/abc1600_memory.c",
           ROOT/"firmware/dispatcher/abc1600_memory.h",ROOT/"firmware/dispatcher/cpu68008.h"]
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}

def extract(source,name):
    match=re.search(r"^[^\n]*abc1600_mmu_device::"+re.escape(name)+r"\([^\n]*\)(?: const)?\n\{",source,re.M)
    if not match:raise ValueError(f"MAME method not found: {name}")
    start=match.start();opening=source.index("{",match.start());depth=1;end=opening+1
    while depth:
        if source[end]=="{":depth+=1
        elif source[end]=="}":depth-=1
        end+=1
    return source[start:end]

def prepare():
    BUILD.mkdir(parents=True,exist_ok=True)
    subprocess.run(["cc","-shared","-fPIC","-O2","-std=c11","-Wall","-Wextra","-Werror",
                    str(ROOT/"firmware/dispatcher/abc1600_memory.c"),"-o",str(NATIVE)],check=True)
    names=["mac_r","mac_w","mmu::ifc2","mmu::force_task0","mmu::get_task","mmu::get_segment_address",
           "mmu::get_physical_address","mmu::mmu_read","mmu::mmu_write","cause_r","task_w",
           "segment_r","segment_w","page_hi_r","page_lo_r","page_hi_w","page_lo_w"]
    source=MAME.read_text();methods="\n\n".join(extract(source,n) for n in names)
    shell=(ROOT/"tools/tests/mame_abc1600_adapter.cpp.in").read_text().replace("@METHODS@",methods)
    (BUILD/"mame-reference.cpp").write_text(shell)
    subprocess.run(["c++","-shared","-fPIC","-O2","-std=c++17",str(BUILD/"mame-reference.cpp"),
                    "-o",str(REFERENCE)],check=True)
    revision=subprocess.check_output(["git","-C",str(ROOT/"mame"),"rev-parse","HEAD"],text=True).strip()
    (BUILD/"sources.json").write_text(json.dumps(dict(mame_revision=revision,methods=names,sha256=fingerprint()),indent=2)+"\n")

def require_current():
    manifest=BUILD/"sources.json"
    if not NATIVE.exists() or not REFERENCE.exists() or not manifest.exists() or json.loads(manifest.read_text())["sha256"]!=fingerprint():
        raise ValueError("Run python3 tools/abc1600_model.py to rebuild the current MAME/model reference")

class Model:
    def __init__(self,rom,reference=False):
        require_current();self.reference=reference
        self.rom=(C.c_uint8*len(rom)).from_buffer_copy(rom);self.ram=(C.c_uint8*1572864)()
        self.lib=C.CDLL(str(REFERENCE if reference else NATIVE));self.state=ModelState()
        if reference:
            self.lib.mame_abc_init.argtypes=[C.c_void_p,C.c_void_p]
            self.lib.mame_abc_access.argtypes=[C.c_uint32,C.c_uint32,C.c_bool,C.POINTER(C.c_uint8)]
            self.lib.mame_abc_segments.restype=C.POINTER(C.c_uint8*1024)
            self.lib.mame_abc_pages.restype=C.POINTER(C.c_uint16*1024)
            self.lib.mame_abc_regs.argtypes=[C.c_void_p]
            self.lib.mame_abc_init(self.rom,self.ram)
        else:
            self.lib.abc1600_memory_init.argtypes=[C.POINTER(ModelState)]
            self.lib.abc1600_memory_access.argtypes=[C.POINTER(ModelState),C.c_void_p,C.c_void_p,C.c_uint32,C.c_uint32,C.c_bool,C.POINTER(C.c_uint8)]
            self.lib.abc1600_memory_init(C.byref(self.state))

    def access(self,address,fc,write=False,value=0):
        byte=C.c_uint8(value)
        status=(self.lib.mame_abc_access(address,fc,write,C.byref(byte)) if self.reference else
                self.lib.abc1600_memory_access(C.byref(self.state),self.rom,self.ram,address,fc,write,C.byref(byte)))
        return status,byte.value

    def tables(self):
        if self.reference:return bytes(self.lib.mame_abc_segments().contents),struct.pack("<1024H",*self.lib.mame_abc_pages().contents)
        return bytes(self.state.segment),struct.pack("<1024H",*self.state.page)

    def registers(self):
        if self.reference:
            out=(C.c_uint32*5)();self.lib.mame_abc_regs(out);return list(out)
        s=self.state.status;return [s.task,s.boote,s.magic,s.cause,s.cause_reads]

    def status(self):return {n:getattr(self.state.status,n) for n in FIELDS}

def check():
    rom=(ROOT/"roms/abc1600/ABC1600ROM.bin").read_bytes()
    native=Model(rom);reference=Model(rom,reference=True);count=0
    def access(address,fc,write=False,value=0):
        nonlocal count
        actual=native.access(address,fc,write,value);gold=reference.access(address,fc,write,value)
        if actual[0]!=gold[0] or (not write and not actual[0] and actual[1]!=gold[1]):
            raise AssertionError((hex(address),fc,write,value,actual,gold))
        if native.registers()!=reference.registers():raise AssertionError("MAME register-state mismatch")
        count+=1
    for address in range(0,0x20000,257):
        access(address,6);access(address,5)
    # Program every task/segment selector, including the SEGA19 address-bit-8 selection.
    for task in range(16):
        access(0x80005,5,True,0xc0|task)
        for segment in range(32):
            address=0x80003|((segment&15)<<15)|((segment>>4)<<8)
            access(address,5,True,(task*7+segment)&127);access(address,5)
    access(0x80005,5,True,0xc0)
    # All 1024 page entries; read high-byte replicated X20 bits back too.
    for block in range(64):
        access(0x80003,5,True,block)
        for page in range(16):
            address=0x80000|(page<<11)
            access(address,5,True,(block+page)&255)
            access(address+1,5,True,(block*19+page)&255)
            access(address,5);access(address+1,5)
    rng=random.Random(0xabc1600)
    for i in range(10000):
        if i%11==0:access(0x80005,5,True,rng.randrange(256))
        address=rng.randrange(1048576);fc=rng.choice((1,2,5,6));write=bool(rng.getrandbits(1))
        access(address,fc,write,rng.randrange(256))
    if native.tables()!=reference.tables() or bytes(native.ram)!=bytes(reference.ram):
        raise AssertionError("MAME table/RAM mismatch")
    result=dict(passed=True,accesses=count,mame_revision=json.loads((BUILD/"sources.json").read_text())["mame_revision"],
                counters=native.status())
    (BUILD/"report.json").write_text(json.dumps(result,indent=2)+"\n");return result

if __name__=="__main__":
    prepare();print(json.dumps(check(),indent=2))
