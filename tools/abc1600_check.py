#!/usr/bin/env python3
"""Upload the ABC1600 ROM and verify its first five instructions over PIO."""
import argparse
import csv
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import time
import zlib
from ice import Device, decode_cpu_registers, save_capture
from cpu_reference import CPU, LIBRARY, ROOT, require_current_library


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu", required=True); parser.add_argument("--memory", required=True)
    parser.add_argument("--allow-drive", action="store_true", required=True)
    parser.add_argument("--rom", type=Path, default=ROOT / "roms/abc1600/ABC1600ROM.bin")
    parser.add_argument("--output", type=Path, default=ROOT / "build/abc1600")
    args = parser.parse_args(); rom = args.rom.read_bytes()
    if len(rom) != 16384 or zlib.crc32(rom) != 0x9372f6f2:
        raise ValueError("Expected ABC1600 boot 6490356-04, 16 KiB, CRC32 9372F6F2")
    args.output.mkdir(parents=True, exist_ok=True)
    with Device(args.cpu) as cpu, Device(args.memory) as memory:
        if cpu.info["serial"] == memory.info["serial"]: raise ValueError("Select two distinct boards")
        if any(d.info["firmware"] != "dispatcher-0.6" for d in (cpu, memory)):
            raise ValueError("Both boards need dispatcher-0.6")
        memory.load("bus-memory", "flash"); upload = memory.memory_load(rom)
        # Taken branch first; finish paused on the normal reset path.
        results = [run_case(cpu, memory, rom, cause, args.output) for cause in (6, 2)]
        (args.output / "report.json").write_text(json.dumps(dict(rom_sha256=hashlib.sha256(rom).hexdigest(),
                                                                upload=upload, cases=results), indent=2) + "\n")


if __name__ == "__main__": main()
