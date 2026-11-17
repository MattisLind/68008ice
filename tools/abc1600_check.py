#!/usr/bin/env python3
"""Verify ABC1600 ROM execution over PIO, or the five-instruction generic fixture."""
import argparse
import csv
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import time
import zlib
from ice import Device, DeviceError, decode_cpu_registers, save_capture
from cpu_reference import CPU, LIBRARY, ROOT, require_current_library
from abc1600_model import Model, require_current as require_current_model


def expected_abc1600_boot(rom,instructions=105):
    """Firmware CPU+MAC versus independent Musashi+unmodified MAME methods."""
    require_current_library();require_current_model()
    lib=C.CDLL(str(LIBRARY));native=Model(rom);reference=Model(rom,reference=True)
    reader_type=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint32,C.c_uint32,C.POINTER(C.c_uint8))
    writer_type=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint32,C.c_uint32,C.c_uint8)
    lib.cpu68008_reset.argtypes=[C.POINTER(CPU),reader_type,C.c_void_p]
    lib.cpu68008_execute.argtypes=[C.POINTER(CPU),reader_type,writer_type,C.c_void_p]
    lib.reference_machine_reset.argtypes=[reader_type,writer_type,C.c_void_p,C.c_void_p]
    lib.reference_machine_step.argtypes=[C.c_void_p]
    events=[]
    def read(ctx,address,fc,data):
        status,value=native.access(address,fc);data[0]=value
        events.append(dict(address=address,fc=fc,data=value,read=True));return status
    def write(ctx,address,fc,data):
        events.append(dict(address=address,fc=fc,data=data,read=False))
        return native.access(address,fc,True,data)[0]
    def ref_read(ctx,address,fc,data):
        status,value=reference.access(address,fc);data[0]=value;return status
    def ref_write(ctx,address,fc,data):return reference.access(address,fc,True,data)[0]
    reader,writer=reader_type(read),writer_type(write)
    ref_reader,ref_writer=reader_type(ref_read),writer_type(ref_write)
    cpu=CPU(version=2,state=0);gold=(C.c_uint32*18)()
    if lib.cpu68008_reset(C.byref(cpu),reader,None) or lib.reference_machine_reset(ref_reader,ref_writer,None,gold):
        raise ValueError("CPU or reference reset failed")
    snapshots=[decode_cpu_registers(bytes(cpu))]
    def compare(step):
        actual=[*cpu.d,*cpu.a,cpu.pc,cpu.sr]
        if actual!=list(gold):raise ValueError(f"CPU/Musashi mismatch at instruction {step}: {actual} != {list(gold)}")
        if native.tables()!=reference.tables() or native.registers()!=reference.registers():
            raise ValueError(f"MAC/MAME mismatch at instruction {step}")
    compare(0)
    for step in range(1,instructions+1):
        status=lib.cpu68008_execute(C.byref(cpu),reader,writer,None)
        if status or cpu.state!=2:
            raise ValueError(f"Execution failed at instruction {step}, PC {cpu.instruction_pc:#x}, opcode {cpu.opcode:#06x}, bus {status}, fault {cpu.fault}")
        if lib.reference_machine_step(gold):raise ValueError(f"MAME reference bus error at instruction {step}")
        compare(step);snapshots.append(decode_cpu_registers(bytes(cpu)))
    if bytes(native.ram)!=bytes(reference.ram):raise ValueError("Translated RAM differs from MAME reference")
    return snapshots,events,native.status(),native.tables()


def expected_boot(rom, cause):
    """Run the firmware core in host RAM; verify each step against Musashi too."""
    require_current_library()
    lib = C.CDLL(str(LIBRARY))
    read_type = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_uint32, C.c_uint32, C.POINTER(C.c_uint8))
    write_type = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint8)
    lib.cpu68008_reset.argtypes = [C.POINTER(CPU), read_type, C.c_void_p]
    lib.cpu68008_execute.argtypes = [C.POINTER(CPU), read_type, write_type, C.c_void_p]
    lib.compare_instruction.argtypes = [C.c_void_p, C.POINTER(CPU), C.c_void_p, C.c_void_p]
    ram = bytearray(1048576); ram[:len(rom)] = rom; ram[0x80007] = cause
    buffer = (C.c_uint8*len(ram)).from_buffer(ram)
    events = []

    def read(ctx, address, fc, data):
        data[0] = ram[address]; events.append(dict(address=address, fc=fc, data=ram[address], read=True)); return 0

    def write(ctx, address, fc, data):
        return 6  # Deny unexpected writes; execute() then fails the test.

    reader, writer = read_type(read), write_type(write)
    cpu = CPU(version=2, state=0)
    if lib.cpu68008_reset(C.byref(cpu), reader, None) or cpu.pc != 0x46 or cpu.ssp != 0x40000:
        raise ValueError("Unexpected reset vectors")
    snapshots = [decode_cpu_registers(bytes(cpu))]
    for _ in range(5):
        candidate = CPU.from_buffer_copy(cpu)
        reference = (C.c_uint32*18)(); difference = C.c_uint32()
        if lib.compare_instruction(buffer, C.byref(candidate), reference, C.byref(difference)):
            raise ValueError(f"ROM instruction disagrees with Musashi at {cpu.pc:#x}")
        if lib.cpu68008_execute(C.byref(cpu), reader, writer, None) or cpu.state != 2:
            raise ValueError(f"Unsupported ROM instruction at {cpu.instruction_pc:#x}")
        snapshots.append(decode_cpu_registers(bytes(cpu)))
    return snapshots, events


def verify_state_capture(record, raw, events):
    if record["stride"] != 12 or record["count"] != len(events) or record["first_sequence"]:
        raise ValueError("Capture did not retain the complete reset/instruction sequence")
    if record["edge_config"] != 2:
        raise ValueError("Expected DS release capture")
    decoded = []
    first = None
    for i, (value, lo, hi) in enumerate(struct.iter_unpack("<3I", raw)):
        actual = dict(address=value&0xfffff, data=(value>>20)&255, read=bool(value&(1<<30)))
        # AS and DS have independent pad synchronizers. At the selected DS
        # release sample AS can still show its previous level for one clock.
        if any(actual[k] != events[i][k] for k in actual) or not value&(1<<29) or value&(1<<31):
            raise ValueError(f"Bus sample {i} differs: {actual}, expected {events[i]}")
        ticks = lo | hi<<32
        if first is None: first = ticks
        decoded.append(dict(sample=i, relative_ps=(ticks-first)*10**12//record["hz"], **actual))
    return decoded


def run_case(cpu, memory, rom, cause, output):
    expected, events = expected_boot(rom, cause)
    memory.request(27, struct.pack("<2I", 0x80007, cause))
    cpu.load("cpu-emulator", "flash")
    config = (64, 50, 1000000, 0, 1, 0, 0, 0, 5, 500, 10000, 3)
    try:
        cpu.run(0, 0, 0, 10000, 1, config)
        cpu.request(5); time.sleep(.03)
        if cpu.status()["samples"]: raise ValueError("Bus access before physical reset")
        memory.run(0, 0, 0, 10000, 9, config)
        sent = cpu.wait(timeout=15); received = memory.wait(timeout=15)
        registers, trace, signals = cpu.cpu_registers(), cpu.cpu_trace(), memory.boot_status()
        if trace["dropped"] or trace["count"] != 6:
            raise ValueError("Incomplete per-instruction register trace")
        fields = "ssp pc sr opcode instructions reads writes address fc d a usp instruction_pc".split()
        for i, (actual, gold) in enumerate(zip(trace["snapshots"], expected)):
            for field in fields:
                if actual[field] != gold[field]:
                    raise ValueError(f"Snapshot {i}, {field}: {actual[field]} != {gold[field]}")
        if registers["state"] != 6 or registers["instructions"] != 5 or registers["writes"]:
            raise ValueError(f"CPU did not pause safely at five instructions: {registers}")
        if signals["fc_errors"] or signals["writes"] or signals["halt_seen"] or received["fdebug"]:
            raise ValueError(f"Unexpected bus activity: {signals}")
        name = f"cause-{cause:02x}"
        record = save_capture(memory, 0, output / (name + ".vcd"))
        samples = verify_state_capture(record, (output / (name + ".bin")).read_bytes(), events)
        with (output / (name + ".csv")).open("w") as f:
            writer = csv.DictWriter(f, fieldnames=["sample", "relative_ps", "address", "data", "read"])
            writer.writeheader(); writer.writerows(samples)
        # Readback also proves the uploaded ROM was not changed by execution.
        if memory.read_data(4, 0, len(rom)) != rom: raise ValueError("ROM changed during execution")
        result = dict(cause=cause, cpu=sent, memory=received, registers=registers, trace=trace,
                      expected_snapshots=expected, expected_bus=events, signals=signals, capture=record)
        (output / (name + "-report.json")).write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(dict(cause=cause, instructions=registers["instructions"], pc=hex(registers["pc"]),
                              sr=hex(registers["sr"]), d7=hex(registers["d"][7]), bus_reads=len(samples), passed=True)), flush=True)
        return result
    finally:
        cpu.request(7); memory.request(7)


def run_abc1600(cpu,memory,rom,instructions,output):
    expected,events,model_status,tables=expected_abc1600_boot(rom,instructions)
    cpu.load("cpu-emulator","flash");memory.load("abc1600-memory","flash")
    upload=memory.memory_load(rom)
    if len(events)>4096:raise ValueError("Increase capture capacity for this execution budget")
    config=(4096,50,1000000,0,1,0,0,0,instructions,500,10000,0)
    rejected=0
    invalid=[(0,config,7),(9,config,1)]
    for field,value in ((2,150000000),(7,1024),(11,3)):
        bad=list(config);bad[field]=value;invalid.append((1,bad,1))
    for flags,bad,status in invalid:
        try:memory.request(4,struct.pack("<17I",0,0,0,10000,flags,*bad))
        except DeviceError as error:
            if error.status!=status:raise
            rejected+=1
        else:raise ValueError("ABC1600 accepted an invalid RUN")
    try:
        cpu.run(0,0,0,10000,5,config);cpu.request(5);time.sleep(.03)
        if cpu.status()["samples"]:raise ValueError("Bus access before physical reset")
        memory.run(0,0,0,10000,1,config)
        sent=cpu.wait(timeout=15);received=memory.wait(timeout=15)
        registers,trace,signals=cpu.cpu_registers(),cpu.cpu_trace(),memory.boot_status()
        observed_model=memory.abc1600_status()
        if trace["dropped"] or trace["count"]!=instructions+1:raise ValueError("Incomplete instruction snapshots")
        fields="ssp pc sr opcode instructions reads writes address fc d a usp instruction_pc".split()
        for i,(actual,gold) in enumerate(zip(trace["snapshots"],expected)):
            for field in fields:
                if actual[field]!=gold[field]:raise ValueError(f"Snapshot {i}, {field}: {actual[field]} != {gold[field]}")
        if registers["state"]!=6 or registers["instructions"]!=instructions:raise ValueError("Incorrect instruction-budget pause")
        if observed_model!=model_status:raise ValueError(f"Hardware MAC status differs: {observed_model} != {model_status}")
        if (memory.read_data(6,0,1024),memory.read_data(7,0,2048))!=tables:raise ValueError("Hardware MAC tables differ")
        if signals["fc_errors"] or signals["halt_seen"] or received["fdebug"]:raise ValueError("Unexpected bus or capture error")
        name=f"abc1600-{instructions}"
        record=save_capture(memory,0,output/(name+".vcd"))
        samples=verify_state_capture(record,(output/(name+".bin")).read_bytes(),events)
        if sent["samples"]!=len(events) or signals["cycles"]!=len(events):raise ValueError("Bus transfer counts differ")
        with (output/(name+".csv")).open("w") as f:
            w=csv.DictWriter(f,fieldnames=["sample","relative_ps","address","data","read"]);w.writeheader();w.writerows(samples)
        if memory.read_data(4,0,len(rom))!=rom:raise ValueError("ROM changed")
        result=dict(machine="abc1600",instructions=instructions,rejected_invalid_runs=rejected,rom_sha256=hashlib.sha256(rom).hexdigest(),upload=upload,
                    cpu=sent,memory=received,registers=registers,trace=trace,expected_snapshots=expected,
                    expected_bus=events,signals=signals,capture=record,mac=observed_model)
        (output/"report.json").write_text(json.dumps(result,indent=2)+"\n")
        (output/"segments.bin").write_bytes(tables[0]);(output/"pages.bin").write_bytes(tables[1])
        print(json.dumps(dict(machine="abc1600",instructions=instructions,pc=hex(registers["pc"]),sr=hex(registers["sr"]),
                              bus_reads=registers["reads"],bus_writes=registers["writes"],mac=observed_model,passed=True),indent=2))
        return result
    finally:cpu.request(7);memory.request(7)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu", required=True); parser.add_argument("--memory", required=True)
    parser.add_argument("--allow-drive", action="store_true", required=True)
    parser.add_argument("--allow-writes",action="store_true",help="Permit the ABC1600 ROM's MAC programming writes")
    parser.add_argument("--machine",choices=("abc1600","generic"),default="abc1600")
    parser.add_argument("--instructions",type=int,choices=range(1,128),metavar="1..127",default=105)
    parser.add_argument("--rom", type=Path, default=ROOT / "roms/abc1600/ABC1600ROM.bin")
    parser.add_argument("--output", type=Path, default=ROOT / "build/abc1600-105")
    args = parser.parse_args(); rom = args.rom.read_bytes()
    if args.machine=="abc1600" and not args.allow_writes:parser.error("ABC1600 execution requires --allow-writes")
    if len(rom) != 16384 or zlib.crc32(rom) != 0x9372f6f2:
        raise ValueError("Expected ABC1600 boot 6490356-04, 16 KiB, CRC32 9372F6F2")
    args.output.mkdir(parents=True, exist_ok=True)
    with Device(args.cpu) as cpu, Device(args.memory) as memory:
        if cpu.info["serial"] == memory.info["serial"]: raise ValueError("Select two distinct boards")
        if any(d.info["firmware"] != "dispatcher-0.7" for d in (cpu, memory)):
            raise ValueError("Both boards need dispatcher-0.7")
        if args.machine=="abc1600":
            run_abc1600(cpu,memory,rom,args.instructions,args.output);return
        memory.load("bus-memory", "flash"); upload = memory.memory_load(rom)
        # Taken branch first; finish paused on the normal reset path.
        results = [run_case(cpu, memory, rom, cause, args.output) for cause in (6, 2)]
        (args.output / "report.json").write_text(json.dumps(dict(rom_sha256=hashlib.sha256(rom).hexdigest(),
                                                                upload=upload, cases=results), indent=2) + "\n")


if __name__ == "__main__": main()
