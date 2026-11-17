#!/usr/bin/env python3
"""Exercise the two Core2350B boards as an 8 MHz-timed 68008 bus fixture."""
import argparse
import json
from pathlib import Path
import struct
from ice import Device, DeviceError, save_capture


def rejects(device, op, payload, status):
    try:
        device.request(op, payload)
    except DeviceError as exc:
        assert exc.status == status
        return
    raise AssertionError("Invalid request accepted")


def run_case(source, receiver, output, name, *, samples=100, percent=50, address=600,
             mask=0xfffff, cycles=2048, strobe=0, edge=0, base=0, idle=500):
    source.load("bus-generator", "flash")
    receiver.load("bus-memory", "flash")
    config = (samples, percent, 1000000, strobe, edge, address+base, mask, base, cycles, idle, 10000, 0x5a)
    try:
        source.run(0, 0, 0, 30000, 5, config)
        receiver.run(0, 0, 0, 30000, 1, config)
        source.request(5)
        sent = source.wait(timeout=40)
        received = receiver.wait(timeout=40)
        assert sent["samples"] == cycles and received["fdebug"] == 0
        record = save_capture(receiver, 0, output / f"{name}.vcd")
        raw = (output / f"{name}.bin").read_bytes()
        memory = receiver.read_data(3, 0, 1024)
        expected = bytes((i ^ (i >> 8) ^ 0x5a) & 255 if i < min(cycles, 1024) else 0 for i in range(1024))
        assert memory == expected
        (output / f"{name}-memory.bin").write_bytes(memory)
        values = [struct.unpack_from("<I", raw, at)[0] for at in range(0, len(raw), 12)]
        assert all(base <= (v & 0xfffff) < base+1024 for v in values)
        if record["flags"] & 1:
            assert (values[record["trigger"]] & mask) == ((address+base) & mask)
            assert record["trigger"] == samples*percent//100
        # Data is established for writes on DS assertion and for both
        # directions on DS release. AS assertion is an address-only snapshot.
        if strobe == 0:
            for value in values:
                offset = (value & 0xfffff)-base
                if edge or not value & (1 << 30):
                    assert (value >> 20) & 255 == (offset ^ (offset >> 8) ^ 0x5a) & 255
        result = dict(name=name, generator=sent, receiver=received, capture=record)
        print(json.dumps(result), flush=True)
        return result
    finally:
        source.request(7)
        receiver.request(7)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generator", required=True)
    parser.add_argument("--receiver", required=True)
    parser.add_argument("--output", type=Path, default=Path("build/bus-check"))
    parser.add_argument("--full", action="store_true", help="Also exercise 65536 captured state records")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with Device(args.generator) as source, Device(args.receiver) as receiver:
        if source.info["serial"] == receiver.info["serial"]:
            raise ValueError("Select two different boards")
        results = []
        for percent, name in ((10, "early"), (50, "middle"), (90, "late")):
            r = run_case(source, receiver, args.output, name, percent=percent)
            assert r["capture"]["count"] == 100
            results.append(r)
        results.append(run_case(source, receiver, args.output, "as-assert", strobe=1, base=0x40000))
        read = run_case(source, receiver, args.output, "ds-release", samples=128, edge=1, address=0)
        read_raw = (args.output / "ds-release.bin").read_bytes()
        assert struct.unpack_from("<I", read_raw, read["capture"]["trigger"]*12)[0] & (1 << 30)
        results.append(read)
        partial = run_case(source, receiver, args.output, "partial-after-trigger", samples=128,
                           percent=10, address=16, cycles=32)
        assert partial["capture"]["count"] == 28
        results.append(partial)
        partial = run_case(source, receiver, args.output, "partial-before-trigger", samples=128,
                           address=100, cycles=16)
        assert partial["capture"]["count"] == 16 and not partial["capture"]["flags"] & 1
        results.append(partial)
        if args.full:
            r = run_case(source, receiver, args.output, "maximum", samples=65536,
                         percent=50, address=0, mask=0, cycles=65536)
            assert r["capture"]["count"] == 65536
            results.append(r)
        receiver.load("state-analyzer", "flash")
        config = (65536, 90, 1000000, 0, 0, 0, 0xfffff, 0, 2048, 0, 10000, 0x5a)
        receiver.run(0, 0, 0, 30000, 0, config)
        receiver.stop()
        empty = save_capture(receiver, 0, args.output / "manual-empty.vcd")
        assert empty["count"] == 0 and empty["flags"] & 2
        results.append(dict(name="manual-empty", capture=empty))
        # Validate before executing: no drive, illegal capacity/ratio, bad
        # bank and excessive continuous rate must not start a worker job.
        source.load("bus-generator", "flash")
        rejects(source, 4, struct.pack("<17I", 0, 0, 0, 1000, 0, *config), 7)
        receiver.load("state-analyzer", "flash")
        for index, value in ((0, 0), (0, 65537), (1, 11)):
            bad = list(config)
            bad[index] = value
            rejects(receiver, 4, struct.pack("<17I", 0, 0, 0, 1000, 0, *bad), 1)
        rejects(receiver, 4, struct.pack("<17I", 1, 0, 0, 1000, 0, *config), 1)
        receiver.load("analyzer", "flash")
        bad = list(config)
        bad[2] = 1000001
        rejects(receiver, 4, struct.pack("<17I", 0, 0, 0, 1000, 0, *bad), 1)
        results.append(dict(name="invalid-settings-rejected"))
        # A responder at a different base must leave DTACK inactive. The
        # master times out and releases; the observer preserves that attempt.
        source.load("bus-generator", "flash")
        receiver.load("bus-memory", "flash")
        config = (128, 10, 1000000, 0, 0, 0, 0, 0, 1, 100, 1000, 0x5a)
        source.run(0, 0, 0, 5000, 5, config)
        other = list(config)
        other[7] = 1024
        receiver.run(0, 0, 0, 5000, 1, other)
        source.request(5)
        failed = source.wait(states=(5,))
        assert failed["error"] == 2 and failed["samples"] == 0
        receiver.wait()
        timeout = save_capture(receiver, 0, args.output / "unmapped-timeout.vcd")
        assert timeout["count"] == 1
        results.append(dict(name="unmapped-timeout", generator=failed, capture=timeout))
        report = dict(devices=[source.info, receiver.info], cases=results)
        (args.output / "report.json").write_text(json.dumps(report, indent=2)+"\n")


if __name__ == "__main__":
    main()
