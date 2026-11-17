#!/usr/bin/env python3
"""Decode a bidirectional GPIO0..44 LOW/HIGH scan captured through SWD."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

PIN_COUNT = 45
MASK = (1 << PIN_COUNT) - 1
LED_MASK = 1 << 39


def pins(mask):
    return [pin for pin in range(PIN_COUNT) if mask & (1 << pin)]


def decode(text):
    boards, baselines, scans, releases = {}, {}, {}, {}
    scan_format = None
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "FORMAT" and len(parts) == 3:
            scan_format = tuple(map(int, parts[1:]))
        elif parts[0] == "BOARD" and len(parts) == 3:
            boards[int(parts[1])] = parts[2]
        elif parts[0] == "BASELINE" and len(parts) == 4:
            baselines[int(parts[1])] = [int(part, 0) & MASK for part in parts[2:]]
        elif parts[0] == "SCAN" and len(parts) == 10:
            scans[tuple(map(int, parts[1:4]))] = [int(part, 0) & MASK for part in parts[4:]]
        elif parts[0] == "RELEASE" and len(parts) == 6:
            releases[tuple(map(int, parts[1:4]))] = [int(part, 0) & MASK for part in parts[4:]]
    expected = {(high, board, pin) for high in (0, 1) for board in (1, 2) for pin in range(PIN_COUNT)}
    if (scan_format != (2, PIN_COUNT) or "GPIO CONNECTIVITY SCAN COMPLETE" not in text or set(scans) != expected
            or set(releases) != expected or set(baselines) != {0, 1}
            or set(boards) != {1, 2} or boards[1] == boards[2]):
        raise RuntimeError("Incomplete scan or duplicate board identities; refusing to infer wiring")

    observations = {}
    for key, samples in scans.items():
        high, board, pin = key
        idle_source, idle_rx, source1, rx1, source2, rx2 = samples
        released_source, released_rx = releases[key]
        # The fitted GPIO39 LED can sink a weak pull-up. Its HIGH response
        # proves continuity; do not invent a LOW transition from that bias.
        source_valid = MASK if high else MASK & ~(~idle_source & LED_MASK)
        rx_valid = MASK if high else MASK & ~(~idle_rx & LED_MASK)
        def activated(idle, sample, valid):
            return pins((sample & ~idle if high else idle & ~sample) & valid)
        observations[key] = {
            "observed": activated(idle_rx, rx1, rx_valid),
            "local_active": activated(idle_source, source1, source_valid),
            "stable": not ((source1 ^ source2) & source_valid or (rx1 ^ rx2) & rx_valid),
            "released": not ((released_source ^ idle_source) & source_valid or (released_rx ^ idle_rx) & rx_valid),
            "drive_ok": all(bool(value & (1 << pin)) == bool(high) for value in (source1, source2)),
            "receiver_level": int(bool(rx1 & (1 << pin))),
        }

    rows = []
    for pin in range(PIN_COUNT):
        forward = observations[1, 1, pin]
        reverse = observations[1, 2, pin]
        issues = []
        for board in (1, 2):
            if pin != 39 and not baselines[1][board - 1] & (1 << pin):
                issues.append(f"board {board} GPIO{pin} LOW despite pull-up")
            if baselines[0][board - 1] & (1 << pin):
                issues.append(f"board {board} GPIO{pin} HIGH despite pull-down")
        for high in (0, 1):
            for board in (1, 2):
                item = observations[high, board, pin]
                label = "HIGH" if high else "LOW"
                if not item["stable"]:
                    issues.append(f"unstable while board {board} drives {label}")
                if not item["released"]:
                    issues.append(f"levels did not recover after board {board} released {label}")
                if not item["drive_ok"]:
                    issues.append(f"board {board} GPIO{pin} could not drive {label}")
                biased_low_led = not high and pin == 39 and not scans[high, board, pin][0] & LED_MASK
                expected_local = [] if biased_low_led else [pin]
                if item["local_active"] != expected_local:
                    issues.append(f"board {board} local {label} pins {item['local_active']}")
        for board in (1, 2):
            rx_idle_up = scans[0, board, pin][1]
            expected_low = [p for p in observations[1, board, pin]["observed"]
                            if p != 39 or rx_idle_up & LED_MASK]
            if observations[0, board, pin]["observed"] != expected_low:
                issues.append(f"board {board} LOW/HIGH destination maps disagree")

        observed = forward["observed"]
        if observed == [pin] and reverse["observed"] == [pin] and not issues:
            status = "PASS"
        elif issues:
            status = "ELECTRICAL_OR_UNSTABLE"
        elif not observed and not reverse["observed"]:
            status = "NO_CONNECTION_DETECTED"
        elif len(observed) > 1 or len(reverse["observed"]) > 1:
            status = "MULTIPLE_CONNECTIONS"
        elif len(observed) == 1 and observed != [pin]:
            target = observed[0]
            if observations[1, 2, target]["observed"] == [pin]:
                status = "WRONG_PIN"
            else:
                status = "DIRECTIONAL_OR_AMBIGUOUS"
        else:
            status = "DIRECTIONAL_OR_AMBIGUOUS"
        rows.append({"pin": pin, "status": status, "board1_to_board2": observed,
                     "board2_to_board1": reverse["observed"],
                     "low_board1_to_board2": observations[0, 1, pin]["observed"],
                     "low_board2_to_board1": observations[0, 2, pin]["observed"], "issues": issues})
    return {
        "boards": boards, "pin_count": PIN_COUNT, "format_version": 2,
        "passed": sum(row["status"] == "PASS" for row in rows),
        "rows": rows,
        "bias": {str(board): {
            "low_despite_pull_up": pins(~baselines[1][board - 1] & MASK),
            "high_despite_pull_down": pins(baselines[0][board - 1]),
        } for board in (1, 2)},
        "observations": {f"{high}:{board}:{pin}": item for (high, board, pin), item in observations.items()},
    }


def render(report):
    lines = [f"Board 1: {report['boards'][1]}", f"Board 2: {report['boards'][2]}",
             f"Same-number connectivity: {report['passed']}/{PIN_COUNT} passed (both directions, LOW/HIGH patterns)."]
    for row in report["rows"]:
        if row["status"] == "PASS":
            continue
        destinations = ", ".join(f"GPIO{p}" for p in row["board1_to_board2"]) or "none"
        reverse = ", ".join(f"GPIO{p}" for p in row["board2_to_board1"]) or "none"
        lines.append(f"GPIO{row['pin']}: {row['status']}; board 1 -> board 2: {destinations}; "
                     f"board 2 -> board 1: {reverse}")
        lines.extend("  " + issue for issue in row["issues"])
    if report["passed"] == PIN_COUNT:
        lines.append("All GPIO0..44 connect to the same-number pin in both directions.")
    else:
        lines.append("No detected path can mean an open wire, excessive resistance, or a connection "
                     "outside GPIO0..44; this is a digital test, not a resistance measurement.")
    return "\n".join(lines) + "\n"


def check(*, root, container, ocd_args, run, mac):
    debug = root / "build/debug"
    debug.mkdir(parents=True, exist_ok=True)
    artifacts = Path(tempfile.mkdtemp(prefix="gpio-connectivity-", dir=debug))
    definitions, hashes = [], {}
    for board in (1, 2):
        relative = f"build/multidrop/{board}/gpio_connectivity.elf"
        elf = root / relative
        if not elf.is_file():
            raise RuntimeError("Missing connectivity ELF; run make gpio-connectivity-build")
        hashes[str(board)] = hashlib.sha256(elf.read_bytes()).hexdigest()
        nm = subprocess.run(container(["arm-none-eabi-nm", "--defined-only", "/work/" + relative]),
                            cwd=root, check=True, capture_output=True, text=True)
        symbols = {parts[2]: int(parts[0], 16) for line in nm.stdout.splitlines()
                   if len(parts := line.split()) == 3}
        for name, symbol in (("MAILBOX", "connectivity"), ("IDADDR", "board_id")):
            definitions += ["-c", f"set {name}{board} 0x{symbols[symbol]:x}"]
    script = str(root / "tools/debug/gpio-connectivity.tcl") if mac else "/work/tools/debug/gpio-connectivity.tcl"
    args = ocd_args(multidrop=True)
    for board in (1, 2):
        args += ["-c", f"board{board}.cm0 configure -gdb-port disabled"]
    args += definitions + ["-c", f"set SCAN_PIN_COUNT {PIN_COUNT}", "-c", "init", "-f", script, "-c", "shutdown"]
    log = artifacts / "scan.log"
    run(args, log=log)
    report = decode(log.read_text())
    report["elf_sha256"] = hashes
    (artifacts / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    summary = render(report)
    (artifacts / "report.txt").write_text(summary)
    print(summary, flush=True)
    print(f"Scan artifacts: {artifacts}", flush=True)
    return report, artifacts
