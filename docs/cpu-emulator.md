# CPU reset and STOP fixture

Dispatcher 0.6 expands this initial milestone with uploaded ROM, additional
instruction families, a successful instruction-budget pause and full register
snapshots. See the current [ABC1600 workflow](abc1600.md). The sections below
record the original 0.5 reset/STOP milestone and its original limitations.

Dispatcher 0.5 adds loadable application **6, `cpu-emulator`**. It executes on
core 1 and fetches every byte through the same PIO bus-cycle engine used by
`bus-generator`. The second RP2350 runs `bus-memory` with a boot image and its
existing PIO/DMA state analyzer. This milestone implements external reset,
big-endian SSP/PC vector fetches, `NOP` and supervisor `STOP`; it is not yet a
full 68008 interpreter or a port of MCL68+.

## Instruction behavior and MCL68+ review

The 68008 has `STOP`, opcode `4E72`, followed by a status-register word.
`STOP #$2700` stops instruction execution without asserting the physical
`/HALT` output. The first test uses that instruction, as agreed with the user.
A separate fault test asserts `/BERR` during the first reset-vector read;
Motorola specifies that a bus error during reset-vector acquisition causes a
double bus fault and assertion of `/HALT`. See the Motorola
[M68000 user's manual](https://datasheets.chipdb.org/Motorola/68000/mc68000_userman.pdf),
sections 5.4.4, 5.5 and 6.3.1. Reset vectors are supervisor **program** accesses
(FC=6), unlike other exception vectors in supervisor data space.

The reviewed upstream source is Ted Fried's
[MCL68_Plus.ino](https://github.com/MicroCoreLabs/Projects/blob/master/MCL68%2B/code/MCL68_Plus.ino),
retrieved 2026-11-17, Git blob `c53c185381c44eb3cbb483216629101e56a42eea`,
939716 bytes, SHA-256
`ef353a301d813e87220f5b3b3db75889f3a2cba4fa4ddf9b9b78440f5147f7b6`.
Its header carries the MIT permission and warranty terms, copyright 2023 Ted
Fried; any later incorporation must retain those notices. No upstream code is
incorporated in this milestone, so the new original code retains Apache-2.0.

MCL68+ is a useful candidate for the subsequent instruction interpreter, but
its `BIU_Read`/write/prefetch paths include Teensy GPIO and board-specific
internal ROM/RAM mappings. Those shortcuts must be removed or adapted so every
target access goes through our byte bus. Its reset routine establishes SR
`$2700` and fetches SSP/PC; its STOP handler loops forever, which would prevent
our USB abort and bounded-job behavior. Its RESET instruction handler also
needs review against Motorola's peripheral-reset semantics. Importing the
whole sketch unchanged would not provide a correct 68008 bus implementation.

## Bench wiring

Use the existing same-number GPIO0–44 wires and common ground between the two
**3.3 V Core2350B boards**. No extra wires are needed on the validated fixture.
GPIO0–31 retain the [bus fixture](bus-fixture.md) assignments.

| GPIO | Signal | CPU board | Boot-memory board |
| --- | --- | --- | --- |
| 0–19 | A0–A19 | Output during execution | Input |
| 20–27 | D0–D7 | Input for this milestone | Output during acknowledged reads |
| 28 / 29 / 30 | /AS / /DS / R/W | PIO outputs | Inputs |
| 31 | /DTACK | Input | Output |
| 32–34 | FC0–FC2 | FC=6 during vector/program fetches | Inputs, checked for each decoded cycle |
| 35 | /RESET | Input | LOW output during reset, then input |
| 38 | /HALT | Input, LOW output on reset-vector fault | LOW during reset, then input/observer |
| 40 | /BERR | Input | LOW during the optional faulted vector read |

GPIO35 RESET is a **fixture assignment**, avoiding the board LED on GPIO39.
The proposed adapter instead uses GPIO39 RESET, GPIO38 HALT and GPIO35 DTACK;
its pin map is unchanged. This firmware is not for that adapter. GPIO32's
local permit in the separate 150 MS/s memory mode is incompatible with CPU
FC0; `--boot` therefore rejects `--timing150`.

RESET/HALT/BERR use fixed LOW SIO output latches and output-enable switching.
Input sensing remains enabled. The bench uses weak pull-ups on these three
lines at startup and after release; no HIGH output is driven on them. This is
the standalone fixture's bias policy, not an adapter pull-up circuit decision.
Boot memory asserts RESET and HALT together for at least 1 ms, then releases
both. CPU RUN/GO alone does not start vector reads: it must observe both LOW,
then both HIGH. Address, data, control and FC outputs stay disabled while
waiting for that initial reset sequence. All outputs release on completion,
abort, timeout or interpreter failure.

## Boot image and expected trace

The boot profile clears the 1 KiB RAM on RUN, then loads:

| Address | Bytes | Meaning |
| --- | --- | --- |
| `$00000..$00003` | `00 00 04 00` | SSP = `$00000400` |
| `$00004..$00007` | `00 00 01 00` | PC = `$00000100` |
| `$00100..$00103` | `4E 72 27 00` | `STOP #$2700` |

The expected bus trace has twelve byte reads: addresses 0..7 followed by
`$100..$103`. It ends with SSP `$400`, PC `$104`, SR `$2700`, one executed
instruction and `/HALT` HIGH. Profile `nop-stop` inserts `4E71` at `$100`,
moves STOP to `$102`, and ends at PC `$106` after fourteen reads.

Use DS **release** state capture to observe acknowledged read bytes. The
receiver preserves read data until after that edge. The existing raw/VCD
format records GPIO0–31 and 64-bit PIO timestamps; FC and RESET/HALT/BERR are
checked by the memory-side software and reported separately, not represented
as synchronized signals in this state VCD. `boot-status` counts attempted
decoded reads/writes, records FC endpoints/error count, records commanded
reset transitions, and latches a sampled HALT LOW after reset release.
Its microsecond times are software observations relative to reset start,
not PIO edge timestamps. Initial reset's HALT LOW does not count as a CPU halt.

## Run and inspect

```sh
make dispatcher-build
# Install each build/multidrop/{1,2}/dispatcher.uf2 on its matching board.
python3 tools/cpu_check.py \
  --cpu /dev/cu.usbmodem24401 --memory /dev/cu.usbmodem24301 --allow-drive
```

The helper verifies STOP and NOP/STOP, no bus access before reset, no-reset
timeout, abort, invalid drive flags, every captured address/direction/data
byte, final CPU registers, FC=6 and no HALT assertion. Results, RAM images,
CRC-checked raw records and VCD files go to `build/cpu-check/`.
For the separate physical HALT test, add `--halt-test`; it also injects a
reset-vector BERR. A halted test job drives HALT LOW for up to 1 ms before
completion releases every output. This bounded fixture pulse is not the
indefinite halted state of a complete replacement CPU.

Manual operation, preparing the CPU before the memory's reset pulse:

```sh
python3 tools/ice.py --port /dev/cu.usbmodem24401 emulate --allow-drive --prepare
# This command waits for completion; run the memory command in another terminal.
python3 tools/ice.py --port /dev/cu.usbmodem24401 go
python3 tools/ice.py --port /dev/cu.usbmodem24301 memory --allow-drive \
  --boot stop --samples 64 --edge release --idle-ms 500 --wait
python3 tools/ice.py --port /dev/cu.usbmodem24401 cpu-status
python3 tools/ice.py --port /dev/cu.usbmodem24301 boot-status
python3 tools/ice.py --port /dev/cu.usbmodem24301 fetch --capture --output build/boot.vcd
```

`emulate` starts automatically unless `--prepare` is selected. Its default
overall timeout is 10 s; `--cycle-timeout-us` bounds each transfer and
`--instructions` (1..65536) bounds execution. `stop` gracefully ends the job;
`stop --discard` aborts with error 7. A new RUN is required after STOP/job
completion. The automated helper ends with its abort check; both boards have
released outputs even though CPU job STATUS then reports the expected error 7.

## Implementation boundaries

The portable core is `firmware/dispatcher/cpu68008.c`; `cpu_fixture.c` handles
physical reset, FC and memory boot profiles; `bus_cycle.c` owns the shared PIO
sequencer. The SRAM-loaded `firmware/apps/cpu_emulator.c` entrypoint calls the
resident implementation through ABI 2, like the existing bus applications.
The build emits `app_cpu_emulator.{elf,bin,app}` and dispatcher images for
both SWD instances. The interpreter has no local target-memory path, and its
32-bit registers are preserved while each external address wraps to 20 bits.

Only reset, NOP, supervisor/non-tracing STOP and reset-vector BERR halt are
implemented. Unsupported opcodes, odd PCs, unsupported STOP status forms,
instruction-budget exhaustion, ordinary exceptions or external HALT during
execution terminate safely; they do not implement those CPU behaviors.
Interrupts, ordinary bus/address-error stacking, writes, RESET instruction,
BR/BG arbitration, VPA/E, clock input, prefetch and full instruction semantics
remain future work. Reset during an active byte transfer aborts/release the
cycle and waits for reset release before fetching fresh vectors. No claim is
made for real CPU prefetch traces, original instruction timing or CPU speed.
The reused PIO phase timing is nominal 8 MHz with software idle between bytes.

The [2026-11-17 evidence](validation/cpu-emulator-2026-11-17/README.md)
records actual bench results and reproducible checks. Full instruction
compatibility must later be tested independently of this bus bring-up.
