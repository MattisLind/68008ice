#!/usr/bin/env python3
"""Run two independent full-clock PIO bench captures and retrieve receiver VCDs."""
from __future__ import annotations
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import time
import zlib


def parse_vcd(text):
    ids = {}
    timestamps, values = [], []
    current = 0
    for line in text.splitlines():
        fields = line.split()
        if line.startswith("$var "):
            if len(fields) != 6 or fields[1:3] != ["wire", "1"]:
                raise RuntimeError("Unexpected VCD variable")
            ids[fields[3]] = int(fields[4].removeprefix("GPIO"))
        elif line.startswith("#"):
            if timestamps: values.append(current)
            timestamps.append(int(line[1:]))
        elif line and line[0] in "01" and line[1:] in ids:
            bit = 1 << ids[line[1:]]
            current = current | bit if line[0] == "1" else current & ~bit
    if timestamps: values.append(current)
    if len(timestamps) != 1024 or len(set(ids.values())) != len(ids):
        raise RuntimeError("VCD must have exactly 1024 timestamps and unique GPIO declarations")
    if not all(b > a for a, b in zip(timestamps, timestamps[1:])):
        raise RuntimeError("VCD timestamps are not strictly increasing")
    return ids, timestamps, values


def check_vcd(data, raw, bank, mailbox):
    if bank not in (0, 1):
        raise RuntimeError("Unknown capture bank")
    if len(mailbox) != 16 or mailbox[7] or mailbox[9] != 1024 or mailbox[11]:
        raise RuntimeError("Incomplete or failed receiver transfer")
    if mailbox[10]:
        raise RuntimeError(f"Receiver PIO FIFO error/stall: 0x{mailbox[10]:08x}")
    ids, times, values = parse_vcd(data.decode("ascii"))
    base, count = (32, 13) if bank else (0, 32)
    if set(ids.values()) != set(range(base, base + count)):
        raise RuntimeError("VCD pin set does not match the requested bank")
    raw_values = struct.unpack("<1024I", raw)
    if values != [value << base for value in raw_values]:
        raise RuntimeError("VCD values differ from the receiver's raw SRAM samples")
    hz = mailbox[8]
    if not hz:
        raise RuntimeError("Receiver reported a zero sample clock")
    if times != [i * 10**12 // hz for i in range(1024)]:
        raise RuntimeError("VCD timebase differs from the device PIO clock")
    if len(data) != mailbox[12] or zlib.crc32(data) != mailbox[13] or zlib.crc32(raw) != mailbox[14]:
        raise RuntimeError("VCD/raw length or CRC differs from the receiver")
    deltas = [(a ^ b).bit_count() for a, b in zip(raw_values, raw_values[1:])]
    # Match against the intended one-bit-per-clock Johnson pattern, allowing a
    # constant trigger/input-sync offset. Real inter-board skew can cause deviations.
    expected = []
    state = 0
    for i in range(2048):
        state ^= 1 << (i % count)
        expected.append(state)
    best = min(range(64), key=lambda offset: sum(value != expected[i + offset]
                                                for i, value in enumerate(raw_values)))
    mismatches = sum(value != expected[i + best] for i, value in enumerate(raw_values))
    return {"bank": bank, "gpio_base": base, "pins": count, "samples": 1024,
            "pio_hz": hz, "sample_period_ps": 10**12 / hz,
            "rx_fdebug": mailbox[10], "raw_crc32": mailbox[14], "vcd_crc32": mailbox[13],
            "vcd_bytes": len(data), "one_bit_transitions": deltas.count(1),
            "repeated_samples": deltas.count(0), "multi_bit_transitions": sum(n > 1 for n in deltas),
            "best_pattern_offset": best, "pattern_mismatches": mismatches}


def capture(*, root, container, ocd_args, run, mac):
    if not mac:
        raise RuntimeError("This bench retrieval path currently expects macOS /Volumes/ICECAP")
    artifacts = Path(tempfile.mkdtemp(prefix="pio-trace-", dir=root / "build/debug"))
    definitions = []
    for board in (1, 2):
        relative = f"build/multidrop/{board}/pio_trace.elf"
        if not (root / relative).is_file():
            raise RuntimeError("Missing PIO ELF; run make pio-trace-build")
        nm = subprocess.run(container(["arm-none-eabi-nm", "--defined-only", "/work/" + relative]),
                            cwd=root, capture_output=True, text=True, check=True)
        symbols = {p[2]: int(p[0], 16) for line in nm.stdout.splitlines() if len(p := line.split()) == 3}
        definitions += ["-c", f"set CONTROL{board} 0x{symbols['trace_control']:x}"]
        if board == 2: definitions += ["-c", f"set SAMPLES2 0x{symbols['trace_samples']:x}"]
    results = []
    volume = Path("/Volumes/ICECAP")
    for bank, name in ((0, "LOW32.VCD"), (1, "HIGH13.VCD")):
        if volume.is_dir():
            run(["diskutil", "unmount", str(volume)])
        args = ocd_args(multidrop=True)
        for board in (1, 2): args += ["-c", f"board{board}.cm0 configure -gdb-port disabled"]
        args += definitions + ["-c", f"set BANK {bank}", "-c", f"set ARTIFACTS {artifacts}",
                "-c", "init", "-f", str(root / "tools/debug/pio-trace.tcl"), "-c", "shutdown"]
        log = artifacts / f"bank{bank}.log"
        run(args, log=log)
        text = log.read_text()
        match = re.search(rf"^RECEIVER {bank} (.+)$", text, re.M)
        if not match or f"PIO TRACE BANK {bank} COMPLETE" not in text:
            raise RuntimeError("Missing completed capture metadata")
        mailbox = [int(word, 0) for word in match[1].split()]
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            path = volume / name
            if path.is_file(): break
            time.sleep(0.2)
        else: raise RuntimeError(f"Capture saved, but {path} did not mount; see {artifacts}")
        data = path.read_bytes()
        (artifacts / name).write_bytes(data)
        result = check_vcd(data, (artifacts / f"bank{bank}.bin").read_bytes(), bank, mailbox)
        results.append(result)
        print(json.dumps(result, indent=2), flush=True)
    (artifacts / "report.json").write_text(json.dumps(results, indent=2) + "\n")
    print(f"VCD files are on {volume}; verified copies and report: {artifacts}", flush=True)
    return results, artifacts
