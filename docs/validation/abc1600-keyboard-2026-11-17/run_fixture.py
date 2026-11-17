#!/usr/bin/env python3
"""Explicitly drive the existing two-board 3.3 V bench fixture."""
import sys,time,json
from pathlib import Path
sys.path.insert(0,'tools')
from ice import Device,save_capture
out=Path('build/abc1600-boot');cpu=Device('/dev/cu.usbmodem24401');mem=Device('/dev/cu.usbmodem24301')
try:
 cpu.load('cpu-emulator','flash');mem.load('abc1600-memory','flash');mem.memory_load(Path('roms/abc1600/ABC1600ROM.bin').read_bytes())
 cfg=(4096,50,1000000,0,1,0xfffff,0xfffff,0,600000,500,100000,0)
 cpu.run(0,0,0,300000,5,cfg);cpu.request(5)
 mc=list(cfg);mc[8]=1;mem.run(0,0,0,300000,1,mc)
 while True:
  s=cpu.status();print('progress',s['samples'],s['state'],s['error'],flush=True)
  if s['state'] in (4,5):break
  time.sleep(5)
 received=mem.wait(timeout=10)
 regs=cpu.cpu_registers();signals=mem.boot_status();mac=mem.abc1600_status()
 result=dict(cpu=s,memory=received,registers=regs,signals=signals,mac=mac)
 (out/'bench-report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
 if s['error'] or regs['instructions']!=600000 or not 0x554<=regs['pc']<=0x56e:raise AssertionError('Keyboard wait not reached')
 save_capture(mem,0,out/'keyboard-wait.vcd')
finally:
 cpu.request(7);mem.request(7)

# Compare the saved analyzer window with a fresh production host run.
import ctypes as C,struct
from cpu_reference import CPU
lib=C.CDLL(str((out/'boot.so').resolve()))
lib.boot_cpu.restype=C.POINTER(CPU);lib.boot_events.restype=C.POINTER(C.c_uint32*4096)
lib.boot_reset((C.c_uint8*16384).from_buffer_copy(Path('roms/abc1600/ABC1600ROM.bin').read_bytes()))
lib.boot_run(600000,0xffffffff);c=lib.boot_cpu().contents
for key in 'pc sr instructions reads writes'.split():
 assert regs[key]==getattr(c,key),(key,regs[key],getattr(c,key))
assert regs['d']==list(c.d) and regs['a']==list(c.a)
total=lib.boot_total();events=list(lib.boot_events().contents)
expected=events[total%4096:]+events[:total%4096]
actual=[a&0x4fffffff for a,_,_ in struct.iter_unpack('<3I',(out/'keyboard-wait.bin').read_bytes())]
assert actual==expected and total==signals['cycles']
check=dict(passed=True,instructions=600000,bus_cycles=total,matched_capture_samples=len(actual),registers_match=True)
(out/'capture-check.json').write_text(json.dumps(check,indent=2)+'\n')
print(check)
