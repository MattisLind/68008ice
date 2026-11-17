#!/usr/bin/env python3
"""Check continuous timing captures on the two-board bench fixture."""
import argparse
import json
from pathlib import Path
from ice import Device, save_capture


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--generator", required=True)
    p.add_argument("--receiver", required=True)
    p.add_argument("--output", type=Path, default=Path("build/continuous-check"))
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    with Device(args.generator) as source, Device(args.receiver) as receiver:
        if source.info["serial"] == receiver.info["serial"]:
            raise ValueError("Select different boards")
        for bank in (0, 1):
            for n, hz in ((17, 1000), (1, 1000000), (257, 1000000), (65536, 1000000)):
                for percent in (10, 50, 90):
                    source.load("generator", "flash")
                    receiver.load("analyzer", "flash")
                    source.run(bank, 32 if bank else 0, 1, 30000, 1)
                    config = (n, percent, hz, 0, 0, 0, 0, 0, 2048, 0, 10000, 0x5a)
                    try:
                        receiver.run(bank, 32 if bank else 0, 0, 10000, 0, config)
                        receiver.wait(timeout=30)
                        name = f"bank{bank}-{n}-{hz}-{percent}"
                        r = save_capture(receiver, bank, args.output / f"{name}.vcd")
                        assert r["count"] == n and r["trigger"] == n*percent//100 and r["hz"] == hz
                        assert not any((args.output / f"{name}.bin").read_bytes())
                        results.append(dict(name=name, capture=r))
                        print(name, "OK", flush=True)
                    finally:
                        source.request(7)
                        source.wait(states=(5, 4))
                        receiver.request(7)
        (args.output / "report.json").write_text(json.dumps(results, indent=2)+"\n")


if __name__ == "__main__":
    main()
