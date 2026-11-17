# ABC1600: next 100 instructions, 2026-11-17

Dispatcher 0.7 executed **105 instructions from reset**, adding the next 100
to the previously verified first five. It used the new ABC1600 memory app,
not a flat-RAM substitute for its registers. Both 3.3 V Core2350B boards were
USB-programmed and flash-verified; see [flash-1.txt](flash-1.txt) and
[flash-2.txt](flash-2.txt). No schematic, PCB or valuable target was involved.

| Role | Serial | CDC port | Loaded app |
| --- | --- | --- | --- |
| CPU | `F3217B63D8F6A7A5` | `/dev/cu.usbmodem24401` | 6, CPU emulator |
| Memory/state analyzer | `AC740FAC748891BF` | `/dev/cu.usbmodem24301` | 7, ABC1600 memory |

The uploaded ROM remains the unchanged 16 KiB `6490356-04` image, CRC32
`9372f6f2`, stored at `roms/abc1600/ABC1600ROM.bin`. Upload and final USB
readback matched. The generic memory application remains independently
available as app 4 (`generic-memory`, compatibility name `bus-memory`).

## Physical run

| Check | Result |
| --- | --- |
| Executed instruction count | 105, including loop iterations |
| Completed byte reads | 300 |
| Completed byte writes | 54 |
| Captured state records | 354, all ordered address/data/direction/DS/ACK checks passed |
| CPU snapshots | 106, after reset and each instruction; zero dropped |
| Snapshot comparison | All D/A registers, PC, SR, SSP/USP, opcode, instruction PC, read/write counts and last access/FC match host execution |
| MAC comparison | All 1024 segment bytes and 1024 page words match the MAME reference |
| MAC writes | 13 writes to segment entry `$0F`, 13 page-high writes, 13 page-low writes, one task-control write; remaining bus writes address unused MAC byte positions |
| Final MAC controls | Task 0, BOOTE 0, MAGIC 1, cause 0; two cause/watchdog-service reads |
| Bus/model/capture errors | Zero BERR, unsupported-I/O, FC errors, HALT assertions and receiver FDEBUG |
| Malformed RUN settings | Five rejected before execution: missing drive, generic boot flag, fast timing, nonzero base and nonzero seed |

The segment dump contains one changed entry: `$0F = $0F`. Page entries
`$F3..$FF` contain `$40F3..$40FF`; all other entries retain their cold-start
values. The repeated segment writes are not thirteen distinct segments.

The CPU is left **paused**, dispatcher job DONE, at PC `$0000007E`, SR `$2700`.
Final relevant registers: D0 `$F2`, D1 `$40F2`, D2 `$F2`, D7 `$02`,
A0 `$000F9004`, A7/SSP `$00040000`. The last executed opcode is `3400`,
`MOVE.W D0,D2`. The next instruction is the already-supported `LSR.W #4,D2`.
The ROM is still in its initial segment/page setup loop; 105 executed
instructions does not mean 105 distinct static opcodes.

The state capture uses DS release, stride 12, nominal PIO timestamp clock
150 MHz, capacity 4096 and idle completion. It retains the entire sequence
from record zero, with no trigger-history discard. Its raw payload has 4248
bytes and a verified CRC. AS/DS input synchronizers are independent; the
verifier accepts the previous AS level at a DS-release sample while requiring
the correct sampled DS, ACK, direction, address and data. Upper-bank FC and
RESET/HALT remain software observations rather than synchronous VCD signals.

- [Complete result, snapshots and expected bus sequence](report.json)
- [Instruction-by-instruction CSV](instructions.csv)
- [Physical bus VCD](abc1600-105.vcd), [raw records](abc1600-105.bin),
  [capture metadata/CRC](abc1600-105.json), [decoded byte CSV](abc1600-105.csv)
- [Segment table](segments.bin), [page table, little-endian uint16](pages.bin)
- [Manual CLI capture](cli-abc1600.vcd), [raw](cli-abc1600.bin),
  [metadata](cli-abc1600.json); its 354 transfers and final registers were
  compared with the same verified host run. The CLI reserved-seed configuration
  also has a host regression test.
- [Final CPU query](final-registers.json), [final MAC query](final-mac.json),
  [available application headers](application-list.json)

## Independent validation

The CPU core passed **81238** single-instruction comparisons with the pinned
Musashi reference, in separate 1 MiB host RAM images, checking D0–D7, A0–A7,
PC, SR and every RAM byte. New families are ADDQ/SUBQ, ANDI including CCR/SR,
SUBA, DBcc and LSR/LSL. The previous opcode/addressing-mode matrix is retained.
[Instruction results](instruction-matrix.json) and
[tested core source hashes](core-sources.json) identify the implementation.

The MAC model passed **17133** access comparisons against 17 methods extracted
unchanged from the local MAME `abc1600_mmu.cpp`. Tests cover boot-ROM mirrors,
all task/segment selectors, all 1024 page entries, page-high readback bits,
randomized user/supervisor fetch/data accesses, translated RAM and protection
faults. A discovered user-program MAC read detail was corrected and given a
native regression test. The test shell supplies RAM/open-bus behavior and an
explicit error for unimplemented physical peripherals; it does not run a full
MAME machine or compare peripheral timing.

MAME revision: `2ab83c729233ca620533d692a8aa1729693ae87f`.
The port retains the source's BSD-3-Clause/Curt Coder notices and
[license text](../../../LICENSES/BSD-3-Clause-MAME.txt).
See [mapping comparison results](mame-model-check.json) and
[MAME method list/source hashes](mame-sources.json).

For the whole ROM run, the portable firmware CPU+MAC pair was compared after
**every instruction** with independent Musashi CPU execution plus those MAME
methods. This host result supplied the expected physical bus sequence and
hardware snapshots. No ROM patch, injected instruction or stack-dump routine
was needed.

All **66 repository tests** passed, including native tests for new instruction
flags/illegal modes, MAC register/protection behavior and separation from
generic RAM. Existing hardware regressions also passed: both generic
five-instruction branch paths; CPU reset/STOP/NOP/HALT, abort and missing-reset
timeout; all **11 bus fixture cases**, including 65536-record capture,
RAM verification and unmapped-cycle timeout.

Reports: [host tests](host-tests.txt), [generic app](generic-regression.json),
[CPU fixture](cpu-regression.json), [bus fixture](bus-regression.json).

## Reproduce and artifacts

Firmware uses the existing `68008ice-pico:2.3.1` toolchain: Pico SDK 2.3.1,
GCC 13.2.1, CMake 3.28.3, Ninja 1.11.1 and `-Wall -Wextra -Werror`.
USB programming uses picotool 2.3.1. Host tests use Python 3.14.8 and Apple
clang 21.0.0. Firmware/module hashes and sizes are in
[artifacts.json](artifacts.json).

```sh
make dispatcher-build
python3 -m unittest discover -s tools/tests -v
python3 tools/cpu_reference.py --prepare
python3 tools/abc1600_model.py
python3 tools/abc1600_check.py --cpu /dev/cu.usbmodem24401 \
  --memory /dev/cu.usbmodem24301 --allow-drive --machine generic \
  --output build/abc1600-105-regression/generic
python3 tools/cpu_check.py --cpu /dev/cu.usbmodem24401 \
  --memory /dev/cu.usbmodem24301 --allow-drive --halt-test \
  --output build/abc1600-105-regression/cpu
python3 tools/bus_check.py --generator /dev/cu.usbmodem24401 \
  --receiver /dev/cu.usbmodem24301 --full --output build/abc1600-105-regression/bus
python3 tools/abc1600_check.py --cpu /dev/cu.usbmodem24401 \
  --memory /dev/cu.usbmodem24301 --allow-drive --allow-writes
```

Generated images remain in `build/multidrop/{1,2}/`, including
`app_abc1600_memory.{elf,bin,app}` and dispatcher `.elf/.bin/.uf2`.
Build/verification logs: `build/abc1600-105-build.log`,
`build/abc1600-105-reference.log`, `build/abc1600-model-check.log`,
`build/abc1600-105-host-tests.log`, `build/abc1600-105-check.log` and
`build/abc1600-105-{generic,cpu-regression,bus-regression}.log`.

The verified scope is early MAC initialization. Physical I/O devices, DMA,
interrupts, watchdog expiry/reset timing, warm resets, original bus wait-state
timing, full CPU exceptions/opcodes and replacement performance remain future
work. Only the standalone two-board fixture has been validated. See the
[current workflow and model limits](../../abc1600.md).
