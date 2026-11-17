# ABC1600 ROM execution evidence, 2026-11-17

The unchanged user-supplied 16 KiB ROM was copied to
`roms/abc1600/ABC1600ROM.bin`, uploaded through the memory command channel,
CRC checked and read back byte for byte. Its CRC32 `9372f6f2` and SHA-1
`86f0681f7ef8dd190b49eda5e781881582e0c2a4` identify ABC1600 boot `6490356-04`.
The ROM was not built into either MCU's flash firmware.

Both Core2350B boards were programmed with dispatcher **0.6.0**, with
successful picotool flash verification recorded in [flash-1.txt](flash-1.txt)
and [flash-2.txt](flash-2.txt).

| Role | Serial | USB CDC | SWD instance |
| --- | --- | --- | --- |
| CPU | `F3217B63D8F6A7A5` | `/dev/cu.usbmodem24401` | 1 |
| Memory/state analyzer | `AC740FAC748891BF` | `/dev/cu.usbmodem24301` | 2 |

Both report core 0 dispatcher, core 1 worker and explicit 8 MiB PSRAM. Wiring
is the existing GPIO0–44 fixture and common ground. The uploaded target map
occupies PSRAM `0x11200000..0x112fffff`; module staging and capture storage
remain separate. Cause-register bytes below are deliberate fixture values,
not a complete ABC1600 hardware model.

## Normal reset-cause path: `$80007 = $02`

Physical RESET/HALT were asserted and released by the memory board. No bus
read occurred before reset. SSP and A7 became `$40000`, PC `$46`, SR `$2700`.

| PC | Instruction | PC after | SR after | D7 after | Completed reads |
| --- | --- | --- | --- | --- | --- |
| `$46` | `CLR.L D7` | `$48` | `$2704` | `$00` | 10 |
| `$48` | `MOVE.B $80007,D7` | `$4E` | `$2700` | `$02` | 17 |
| `$4E` | `BTST #2,D7` | `$52` | `$2704` | `$02` | 21 |
| `$52` | `BNE.S $40` (not taken) | `$54` | `$2704` | `$02` | 23 |
| `$54` | `CLR.L D6` | `$56` | `$2704` | `$02` | 25 |

The 25 reads include all eight reset-vector bytes, opcode/extension fetches
and one supervisor data read at `$80007`. Every captured address, data byte,
direction, sampled DS release and ACK matched the host execution. Six complete
register snapshots (after reset and after each instruction) matched D0–D7,
A0–A7, PC, SR, SSP/USP, opcode, instruction PC, read/write counts and last
access address/FC. Receiver FDEBUG was zero; writes and HALT assertions were
zero. ROM readback still matched after execution.

The CPU is left in state **6 paused**, dispatcher job DONE, at PC `$56` after
exactly five instructions, with outputs released. The ROM remains uploaded
on the memory board. The standalone memory CLI read back `$02` from `$80007`.
The next instruction is `ADDQ.L #1,D6`; it was not executed or implemented
in this milestone.

- [Instruction-by-instruction table](instructions-02.csv)
- [Full register and expected/actual execution report](cause-02-report.json)
- [Bus VCD](cause-02.vcd), [raw state records](cause-02.bin),
  [metadata/CRC](cause-02.json), [decoded byte trace](cause-02.csv)
- [Final register query](final-registers.json), [memory image metadata](final-memory-info.json),
  [cause-byte readback](cause-readback.bin)

## Taken branch: `$80007 = $06`

The same first four opcodes produced D7 `$06` and Z clear. BNE targeted `$40`;
the fifth instruction, `JMP $00010000`, left PC `$10000`, SR `$2700`, SSP
`$40000`. All 29 captured reads and six register snapshots matched the host
run, with no writes, HALT assertions or receiver FDEBUG. No instruction was
fetched/executed at `$10000` by this bounded job.

- [Instruction table](instructions-06.csv) and [full report](cause-06-report.json)
- [VCD](cause-06.vcd), [raw](cause-06.bin), [metadata](cause-06.json),
  [decoded byte trace](cause-06.csv)

## Independent instruction and regression checks

The portable firmware C core and independent Musashi reference ran in
separate 1 MiB host RAM images. **37586 cases passed**, comparing all D/A
registers, PC, SR and every RAM byte after one instruction. The matrix covers
the legal MOVE/MOVEA source/destination EA cross-product, CLR byte/word/long,
static/dynamic BTST, all branch conditions and CCR combinations, byte/word
displacements, JMP control EAs and brief-index register/size selectors.
The reference CPU is a 68000; this compares shared instruction semantics,
while the bench trace verifies our 68008 byte-bus adaptation.

Musashi commit: `313ebf1bd9f4d0d93341eb5ce21fd8a119e9dbdd`.
Archive SHA-256:
`8bed9e28e7e5377256d41aff80a99c9e917a24e7392d9219e1c45c40ad4000e5`.
Upstream MIT notices remain in its downloaded source under
`build/cpu-reference/`; no upstream code is linked into the MCU firmware.
The runner fingerprints the current C core/header and adapter and refuses a
stale host library. [Core source hashes](core-sources.json) and
[matrix results](instruction-matrix.json) identify the tested implementation.

All **56 repository tests passed**, including native C tests for bus errors,
illegal modes, alignment, function codes, CLR read-before-write, long
predecrement write order, A7 stride, BSR stack bytes, both ROM paths and ROM
upload bounds/CRC rejection. The existing STOP/NOP/HALT/abort/no-reset suite
and **11 full bus fixture cases** also passed after the changes, including
65536-record capture and unmapped-cycle timeout. Reports:
[host tests](host-tests.txt), [CPU regression](cpu-regression.json),
[bus regression](bus-regression.json).

## Tools, files and reproduction

Firmware uses the existing `68008ice-pico:2.3.1` Docker toolchain: Pico SDK
2.3.1, GCC 13.2.1, CMake 3.28.3, Ninja 1.11.1, Debug build with
`-Wall -Wextra -Werror`; capture processing retains `-O2`. USB programming
uses picotool 2.3.1. Host execution used Python 3.14.8 and Apple clang 21.0.0.

```sh
make dispatcher-build
python3 -m unittest discover -s tools/tests -v
python3 tools/cpu_reference.py --prepare
python3 tools/cpu_check.py --cpu /dev/cu.usbmodem24401 \
  --memory /dev/cu.usbmodem24301 --allow-drive --halt-test \
  --output build/abc1600-regression/cpu
python3 tools/bus_check.py --generator /dev/cu.usbmodem24401 \
  --receiver /dev/cu.usbmodem24301 --full --output build/abc1600-regression/bus
python3 tools/abc1600_check.py --cpu /dev/cu.usbmodem24401 \
  --memory /dev/cu.usbmodem24301 --allow-drive
```

Build log: `build/abc1600-build.log`. Host/reference logs:
`build/abc1600-host-tests.log`, `build/cpu-reference/final-check.log`.
Bench logs: `build/abc1600-check.log`, `build/abc1600-cpu-regression.log`,
`build/abc1600-bus-regression.log`. Generated dispatcher/module files remain
in `build/multidrop/{1,2}/`; hashes/sizes are in [artifacts.json](artifacts.json).
The combined upload and execution evidence is [report.json](report.json).

Limits: the state capture is DS-edge GPIO0–31, not an external-clock or
prefetch-accurate original-CPU trace. AS/DS synchronization may show the
previous AS level at a DS-release sample. Upper-bank FC and RESET/HALT are
software observations. Ordinary exceptions, interrupts, complete MMU/I/O,
ROM mirrors, remaining opcodes and CPU performance are future work. This
validates only the 3.3 V two-board fixture; no schematic or PCB was changed.
