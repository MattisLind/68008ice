#!/usr/bin/env python3
"""Verify CPU reset/vector/STOP over the physical two-board PIO bus."""
import argparse
import json
from pathlib import Path
import struct
import time
from ice import Device, DeviceError, save_capture


def verify_boot_trace(raw, memory, profile):
    """Compare every physical read with ROM, including the first vector byte."""
    if len(raw) % 12:
        raise ValueError("Truncated state records")
    values = [struct.unpack_from("<I", raw, at)[0] for at in range(0, len(raw), 12)]
    addresses = [v & 0xfffff for v in values]
    expected = [*range(8), *range(0x100, 0x106 if profile == "nop-stop" else 0x104)]
    if addresses != expected:
        raise ValueError(f"Unexpected bus addresses: {addresses}, expected {expected}")
    for value, address in zip(values, addresses):
        if not value & (1 << 30) or ((value >> 20) & 255) != memory[address]:
            raise ValueError(f"Wrong direction/data at {address:#x}")
        # Sampled DS is inactive and ACK is held LOW. AS has its own pad
        # synchronizer and can retain its old level at this selected DS edge.
        if not value & (1 << 29) or value & (1 << 31):
            raise ValueError(f"Wrong completed-cycle strobes at {address:#x}")
    return addresses


def run_case(cpu, memory, output, profile):
    config = (64, 50, 1000000, 0, 1, 0, 0, 0, 1024, 500, 10000,
              ("stop", "nop-stop", "reset-fault").index(profile))
    cpu.load("cpu-emulator", "flash")
    memory.load("bus-memory", "flash")
    try:
        cpu.run(0, 0, 0, 10000, 1, config)
        cpu.request(5)  # CPU waits for a physical RESET/HALT assertion and release.
        time.sleep(.03)
        if cpu.status()["samples"]:
            raise ValueError("CPU accessed memory before RESET")
        memory.run(0, 0, 0, 10000, 9, config)
        sent = cpu.wait(timeout=15)
        received = memory.wait(timeout=15)
        registers, signals = cpu.cpu_status(), memory.boot_status()
        capture = save_capture(memory, 0, output / f"{profile}.vcd")
        rom = memory.read_data(3, 0, 1024)
        (output / f"{profile}-memory.bin").write_bytes(rom)
        if not (signals["reset_asserted"] and signals["reset_released"] and
                signals["reset_high_us"] >= 1000 and not signals["writes"] and not signals["fc_errors"]):
            raise ValueError(f"Bad reset / direction / FC observation: {signals}")
        if profile == "reset-fault":
            if (registers["state"] != 4 or not registers["halt_asserted"] or not signals["halt_seen"] or
                    registers["reads"] or registers["instructions"] or signals["cycles"] != 1):
                raise ValueError(f"Reset bus fault did not assert physical HALT: {registers}, {signals}")
        else:
            expected_reads = 14 if profile == "nop-stop" else 12
            if (registers["state"] != 3 or registers["ssp"] != 0x400 or registers["sr"] != 0x2700 or
                    registers["pc"] != (0x106 if profile == "nop-stop" else 0x104) or
                    registers["instructions"] != (2 if profile == "nop-stop" else 1) or
                    registers["reads"] != expected_reads or signals["reads"] != expected_reads or
                    registers["halt_asserted"] or signals["halt_seen"]):
                raise ValueError(f"Bad STOP result: {registers}, {signals}")
            verify_boot_trace((output / f"{profile}.bin").read_bytes(), rom, profile)
        result = dict(profile=profile, cpu=sent, memory=received, registers=registers, signals=signals, capture=capture)
        print(json.dumps(result), flush=True)
        return result
    finally:
        cpu.request(7)
        memory.request(7)


def rejects(device, payload, expected):
    try:
        device.request(4, payload)
    except DeviceError as exc:
        if exc.status == expected:
            return
        raise
    raise ValueError("Invalid RUN accepted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu", required=True)
    parser.add_argument("--memory", required=True)
    parser.add_argument("--allow-drive", action="store_true", required=True)
    parser.add_argument("--halt-test", action="store_true", help="Also inject a reset-vector BERR and verify physical HALT")
    parser.add_argument("--output", type=Path, default=Path("build/cpu-check"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with Device(args.cpu) as cpu, Device(args.memory) as memory:
        if cpu.info["serial"] == memory.info["serial"]:
            raise ValueError("Select two distinct boards")
        if any(d.info["firmware"] not in ("dispatcher-0.5", "dispatcher-0.6") for d in (cpu, memory)):
            raise ValueError("Both boards need dispatcher-0.5 or later")
        results = [run_case(cpu, memory, args.output, p) for p in
                   (("stop", "nop-stop", "reset-fault") if args.halt_test else ("stop", "nop-stop"))]
        # No RESET: bounded timeout without a single memory access.
        cpu.load("cpu-emulator", "flash")
        config = (1, 10, 1000000, 0, 0, 0, 0, 0, 1024, 0, 10000, 0)
        cpu.run(0, 0, 0, 100, 1, config); cpu.request(5)
        status = cpu.wait(states=(5,), timeout=3)
        if status["error"] != 2 or status["samples"]:
            raise ValueError(f"Missing RESET did not time out safely: {status}")
        cpu.run(0, 0, 0, 10000, 1, config); cpu.request(5)
        aborted = cpu.stop(discard=True)
        if aborted["error"] != 7 or aborted["samples"]:
            raise ValueError(f"Abort failed: {aborted}")
        # Validation precedes any output enable.
        rejects(cpu, struct.pack("<17I", 0, 0, 0, 1000, 0, *config), 7)
        rejects(cpu, struct.pack("<17I", 0, 0, 0, 1000, 9, *config), 1)
        results.append(dict(profile="no-reset-and-abort", timeout=status, abort=aborted))
        (args.output / "report.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
