#!/usr/bin/env python3
"""Capture one 68008 bus cycle with RAM and a 150 MS/s analyzer on one RP2350."""
import argparse
import json
from pathlib import Path
import struct
import time
from ice import Device, save_capture


def timing_svg(record, raw, report):
    """Standalone, dependency-free SVG of the actual samples near the edge."""
    values = struct.unpack(f"<{len(raw)//4}I", raw)
    trigger, hz = record["trigger"], record["hz"]
    begin, end = max(0, trigger-45), min(len(values)-1, trigger+135)
    x = lambda i: 110+((i-trigger)*1e9/hz+300)*.7
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 475">',
           '<rect width="1000" height="475" fill="white"/>',
           '<g font-family="monospace" font-size="13" fill="#203044">',
           f'<text x="22" y="28" font-size="20">{report["type"].capitalize()} cycle: {record["count"]} samples at {hz/1000000:g} MS/s</text>',
           f'<text x="22" y="52">{report["wait_states"]} wait state(s); nominal cycle {report["nominal_bus_cycle_ns"]} ns; FIFO errors 0</text>']
    for ns in range(-300, 901, 100):
        px=110+(ns+300)*.7
        svg += [f'<path d="M{px} 78V405" stroke="#e7ecf1"/>',
                f'<text x="{px}" y="424" text-anchor="middle">{ns}</text>']
    for row, (label, bit, color) in enumerate((("AS_N",28,"#127d74"),("DS_N",29,"#2265ad"),
                                              ("R/W",30,"#535c6d"),("DTACK_N",31,"#823db0"))):
        y=104+row*50
        level=(values[begin]>>bit)&1
        path=f'M{x(begin):.2f} {y-12 if level else y+12}'
        for i in range(begin+1,end+1):
            current=(values[i]>>bit)&1
            if current!=level:
                path+=f'H{x(i):.2f}V{y-12 if current else y+12}'
                level=current
        path+=f'H{x(end):.2f}'
        svg += [f'<text x="22" y="{y+4}">{label}</text>',
                f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2"/>']
    for label, shift, bits, y in (("A[19:0]",0,20,312),("D[7:0]",20,8,362)):
        svg.append(f'<text x="22" y="{y+4}">{label}</text>')
        at=begin
        while at<=end:
            value=(values[at]>>shift)&((1<<bits)-1)
            last=at+1
            while last<=end and (values[last]>>shift)&((1<<bits)-1)==value:last+=1
            left,right=x(at),x(min(last,end))
            svg.append(f'<rect x="{left:.2f}" y="{y-12}" width="{max(.2,right-left):.2f}" height="24" fill="#f5f8fc" stroke="#506c89"/>')
            if right-left>38:
                svg.append(f'<text x="{(left+right)/2:.2f}" y="{y+4}" text-anchor="middle">0x{value:0{bits//4}X}</text>')
            at=last
    svg += [f'<path d="M{x(trigger):.2f} 70V405" stroke="#ce4b29" stroke-dasharray="4 3"/>',
            f'<text x="{x(trigger)+6:.2f}" y="76" fill="#b33d20">DS falling / sample {trigger}</text>',
            '<text x="520" y="447" text-anchor="middle">Time relative to trigger (ns)</text>',
            f'<text x="22" y="468" font-size="11">Zoom of recorded values. Full trace: {record["count"]*1000000/hz:.3f} us. Clock nominal; no external frequency reference.</text></g></svg>']
    return "\n".join(svg)+"\n"


def edges(values, bit, level):
    return [i for i in range(1, len(values))
            if (values[i] >> bit) & 1 == level and (values[i-1] >> bit) & 1 != level]


def check_cycle(record, raw, *, write, base, seed):
    values = struct.unpack(f"<{len(raw)//4}I", raw)
    if (record["hz"] != 150000000 or record["stride"] != 4 or not record["flags"] & 16
            or len(values) != record["capacity"] or record["trigger"] != len(values)*record["pre_percent"]//100):
        raise ValueError("Incorrect timing capture metadata")
    transitions = {name: edges(values, bit, level) for name, bit, level in
                   (("as_assert", 28, 0), ("as_release", 28, 1), ("ds_assert", 29, 0),
                    ("ds_release", 29, 1), ("ack_assert", 31, 0), ("ack_release", 31, 1))}
    if any(len(v) != 1 for v in transitions.values()):
        raise ValueError(f"Expected one complete acknowledged cycle: {transitions}")
    t = {name: positions[0] for name, positions in transitions.items()}
    if t["ds_assert"] != record["trigger"]:
        raise ValueError("Trigger marker is not the sampled DS falling edge")
    if not (t["as_assert"] <= t["ds_assert"]+1 <= t["ack_assert"]+2
            and t["ack_assert"] < t["ds_release"] <= t["ack_release"]+1):
        raise ValueError(f"Incorrect strobe/ack ordering: {t}")
    for value in values[t["ds_assert"]:t["ds_release"]]:
        if value & 0xfffff != base or bool(value & (1 << 30)) == write:
            raise ValueError("Address/direction changed during DS")
    expected = seed if write else 0
    for value in values[t["ack_assert"]+2:t["ds_release"]]:
        if (value >> 20) & 255 != expected:
            raise ValueError("Incorrect acknowledged data")
    ns = lambda samples: samples*1e9/record["hz"]
    as_ns, ds_ns = ns(t["as_release"]-t["as_assert"]), ns(t["ds_release"]-t["ds_assert"])
    # The latch IN precedes strobe release by one 128 MHz PIO tick.
    nominal_as = 41/128000000*1e9
    nominal_ds = (25 if write else 41)/128000000*1e9
    waits = max(0, round((as_ns-nominal_as)/125))
    if abs(as_ns-nominal_as-125*waits) > 20 or abs(ds_ns-nominal_ds-125*waits) > 20:
        raise ValueError(f"Bus phase timing differs from eight-state sequencing: AS={as_ns}, DS={ds_ns}")
    return dict(type="write" if write else "read", samples=len(values), hz=record["hz"],
                trigger_index=record["trigger"], edges=t, as_low_ns=as_ns, ds_low_ns=ds_ns,
                dtack_after_ds_ns=ns(t["ack_assert"]-t["ds_assert"]), wait_states=waits,
                nominal_bus_cycle_ns=500+125*waits,
                note="Cycle duration inferred from PIO phases; sampled widths have clock quantization.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--generator", required=True)
    p.add_argument("--receiver", required=True)
    p.add_argument("--allow-drive", action="store_true", required=True)
    p.add_argument("--allow-writes", action="store_true", help="Capture one write; default is one read")
    p.add_argument("--samples", type=int, default=4096)
    p.add_argument("--position", choices=("early", "middle", "late"), default="middle")
    p.add_argument("--base", type=lambda n: int(n, 0), default=0x400)
    p.add_argument("--delay-ms", type=int, default=0, help="Delay GO to exercise continuous pre-trigger wrapping")
    p.add_argument("--timeout-ms", type=int, default=5000, help="Receiver acquisition timeout, 10..30000 ms")
    p.add_argument("--output", type=Path, default=Path("build/single-cycle.vcd"))
    args = p.parse_args()
    if not 1 <= args.samples <= 4096 or not 0 <= args.delay_ms <= 10000:
        p.error("samples must be 1..4096 and delay 0..10000 ms")
    if not 10 <= args.timeout_ms <= 30000 or args.delay_ms >= args.timeout_ms:
        p.error("timeout must be 10..30000 ms and exceed delay")
    pre = {"early": 10, "middle": 50, "late": 90}[args.position]
    config = (args.samples, pre, 150000000, 0, 0, 0, 0, args.base, 1, 0, 10000, 0x5a)
    with Device(args.generator) as source, Device(args.receiver) as receiver:
        if source.info["serial"] == receiver.info["serial"]:
            raise ValueError("Select two different boards")
        source.load("bus-generator", "flash")
        receiver.load("bus-memory", "flash")
        try:
            source.run(0, 0, 0, 30000, 5 if args.allow_writes else 1, config)
            receiver.run(0, 29, 0, args.timeout_ms, 1, config)
            time.sleep(args.delay_ms/1000)
            source.request(5)
            generated = source.wait()
            captured = receiver.wait()
            if generated["samples"] != 1 or captured["fdebug"]:
                raise ValueError("Incomplete cycle or FIFO error")
            record = save_capture(receiver, 0, args.output)
            raw = args.output.with_suffix(".bin").read_bytes()
            result = check_cycle(record, raw, write=args.allow_writes, base=args.base, seed=0x5a)
            memory = receiver.read_data(3, 0, 1024)
            if memory != bytes([0x5a if args.allow_writes else 0])+bytes(1023):
                raise ValueError("Emulated memory content differs from the single transaction")
            args.output.with_suffix(".memory.bin").write_bytes(memory)
            result.update(generator=generated, receiver=captured, capture=record)
            args.output.with_suffix(".report.json").write_text(json.dumps(result, indent=2)+"\n")
            args.output.with_suffix(".svg").write_text(timing_svg(record,raw,result))
            print(json.dumps(result, indent=2))
        finally:
            source.request(7)
            receiver.request(7)


if __name__ == "__main__":
    main()
