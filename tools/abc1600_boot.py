#!/usr/bin/env python3
"""Bounded host ROM boot using production CPU/memory code and Musashi oracle.

This validates functional execution; external PIO timing requires a bench run.
"""
import ctypes as C
import hashlib
import json
from pathlib import Path
import subprocess
from abc1600_model import ModelState
from cpu_reference import CPU, LIBRARY, ROOT, require_current_library

BUILD=ROOT/'build/abc1600-boot'

def main():
    require_current_library();BUILD.mkdir(parents=True,exist_ok=True)
    subprocess.run(['cc','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror','-I'+str(ROOT/'firmware/dispatcher'),
                    str(ROOT/'tools/tests/abc1600_boot_adapter.c'),str(ROOT/'firmware/dispatcher/cpu68008.c'),
                    str(ROOT/'firmware/dispatcher/abc1600_memory.c'),'-o',str(BUILD/'boot.so')],check=True)
    lib=C.CDLL(str(BUILD/'boot.so'));ref=C.CDLL(str(LIBRARY))
    lib.boot_cpu.restype=C.POINTER(CPU);lib.boot_memory.restype=C.POINTER(ModelState)
    lib.boot_ram.restype=C.POINTER(C.c_uint8*1572864)
    rom=(ROOT/'roms/abc1600/ABC1600ROM.bin').read_bytes();image=(C.c_uint8*len(rom)).from_buffer_copy(rom)
    lib.boot_reset(image);lib.boot_run(2000000,0x554)
    cpu=CPU.from_buffer_copy(lib.boot_cpu().contents);model=ModelState.from_buffer_copy(lib.boot_memory().contents)
    ram=bytes(lib.boot_ram().contents)
    if cpu.pc!=0x554 or cpu.state!=2:raise AssertionError(f'Boot failed: {cpu.pc:#x}, fault {cpu.fault}')
    expected=[*cpu.d,*cpu.a,cpu.pc,cpu.sr]
    # Independent CPU, separate cold start; both use the production peripheral
    # model. MAME MAC differential checks are provided by abc1600_model.py.
    reader=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint32,C.c_uint32,C.POINTER(C.c_uint8))
    writer=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint32,C.c_uint32,C.c_uint8)
    read=reader(('boot_read',lib));write=writer(('boot_write',lib));gold=(C.c_uint32*18)()
    ref.reference_machine_reset.argtypes=[reader,writer,C.c_void_p,C.c_void_p]
    lib.boot_reset(image)
    if ref.reference_machine_reset(read,write,None,gold):raise AssertionError('Reference reset failed')
    count=ref.reference_machine_run(2000000,0x554,gold)
    if list(gold)!=expected:raise AssertionError(f'CPU/Musashi mismatch: {list(gold)} != {expected}')
    if bytes(lib.boot_ram().contents)!=ram:raise AssertionError('CPU/Musashi RAM or VRAM mismatch')
    # Resume production interpreter from its own cold start, verify repeated
    # reads of RR0 with Rx character available clear, and watchdog service.
    lib.boot_reset(image);lib.boot_run(2000000,0x554)
    before=ModelState.from_buffer_copy(lib.boot_memory().contents)
    lib.boot_run(700,0xffffffff);after=lib.boot_memory().contents;c=lib.boot_cpu().contents
    if c.state!=2 or not 0x554<=c.pc<=0x56e or after.keyboard_polls-before.keyboard_polls!=100:
        raise AssertionError('Keyboard polling loop did not repeat 100 times')
    if after.status.cause_reads-before.status.cause_reads!=100:raise AssertionError('Watchdog polling mismatch')
    result=dict(passed=True,validation='host functional execution; PIO bench verification pending',
                instructions_to_keyboard=cpu.instructions,musashi_instructions=count,pc=hex(cpu.pc),
                keyboard_poll_address='0x7f201 (physical 0x1ff201, DART B RR0)',
                keyboard_rx_available=False,poll_iterations=100,watchdog_reads=100,
                rom_sha256=hashlib.sha256(rom).hexdigest(),ram_vram_sha256=hashlib.sha256(ram).hexdigest(),
                d=list(cpu.d),a=list(cpu.a),sr=cpu.sr,reads=cpu.reads,writes=cpu.writes,
                video_moves=model.video.moves,unsupported_io=model.status.unsupported_io)
    (BUILD/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    (BUILD/'vram.bin').write_bytes(ram[1048576:]);print(json.dumps(result,indent=2))

if __name__=='__main__':main()
