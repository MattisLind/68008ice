# 68008 bus fixture and circular capture

For a high-rate waveform of one bus cycle while this board also serves RAM,
see [combined memory and 150 MS/s timing capture](single-cycle-timing.md).
That 0.4 mode has a separate hardware trigger/stop path. Single read/write
captures are verified at 150 MS/s with 4096 samples and exact DS midpoint
placement; the current memory responder adds one or two wait states.

Dispatcher 0.3 adds three loadable applications: `bus-generator`, `bus-memory`
and `state-analyzer`. These run on the two wired **3.3 V Core2350B bench boards**.
The combined memory application serves a 1024-byte RAM and captures state on
the same RP2350. It is separate from the proposed motherboard adapter and its
mode interlock, protected inputs and arbitration circuits.

## Wiring and bus operation

Keep the existing matching GPIO wires and common ground between the boards.

| Fixture GPIO | Signal | Generator direction | Memory direction |
| --- | --- | --- | --- |
| 0–19 | A0–A19 | Output | Input |
| 20–27 | D0–D7 | Output on writes, input on reads | Input on writes, output on reads |
| 28 | /AS | Output | Input |
| 29 | /DS | Output | Input |
| 30 | R/W (1 = read) | Output | Input |
| 31 | /DTACK | Input | Output |

GPIO31 is deliberately repurposed from the adapter's CLK assignment. The
adapter's /DTACK is GPIO35; **this fixture pin map is not adapter firmware**.
The standard generator has no external CLK output, FC, BERR, VPA, RESET/HALT
or arbitration. Dispatcher 0.5's [CPU boot profile](cpu-emulator.md) adds FC
on GPIO32–34, RESET on GPIO35, HALT on GPIO38 and BERR on GPIO40 to the same
wired fixture. The diagnostic generator still models ordinary asynchronous
byte transfers.

The generator's PIO sequencer runs at nominal 128 MHz using the 150 MHz
system clock's fractional divider. Eight PIO clocks give one nominal
62.5 ns half-state of an 8 MHz MC68008 cycle. Read AS/DS assert in S2;
write AS/RW change in S2, data is enabled in S3 and DS asserts in S4.
The S4 termination test extends an unacknowledged transfer by whole nominal
125 ns clocks. Read data is latched before S7; strobes then release and data
outputs disable. Individual edges have system-clock quantization. Software
between transactions adds idle time: **8 MHz describes the bus phase timing,
not a sustained CPU emulation or transaction rate**.

The responder decodes only `[base, base+1024)`, with a configurable 1 KiB-aligned
20-bit base. It clears RAM on each RUN. It stores write data or enables read
data before asserting /DTACK. It holds read data through strobe release, then
releases data and /DTACK after a software recovery interval. CPU service can
insert wait states. Undecoded addresses receive no acknowledgement. A bus-cycle
timeout and USB abort release outputs; inactive bus pulls prevent a released
source from looking like another write. Both active roles require `--allow-drive`.

`--allow-writes` enables alternating sweeps of 1024 writes and 1024 verified
reads. The test byte is `(offset ^ (offset >> 8) ^ seed) & 255`. Without that
flag the generator performs read-only sweeps. It supports 1..65536 cycles,
a 10..100000 us per-cycle timeout and a bounded overall job timeout.

## Run the memory fixture

```sh
make dispatcher-build
# Install build/multidrop/{1,2}/dispatcher.uf2 on the corresponding boards.
python3 tools/ice.py --port /dev/cu.usbmodem24401 bus-generate \
  --allow-drive --allow-writes --prepare --cycles 2048
python3 tools/ice.py --port /dev/cu.usbmodem24301 memory \
  --allow-drive --samples 1024 --position middle \
  --address 0x300 --mask 0xfffff --strobe ds --edge assert --idle-ms 1000
python3 tools/ice.py --port /dev/cu.usbmodem24401 go
python3 tools/ice.py --port /dev/cu.usbmodem24301 fetch \
  --capture --output build/memory.vcd
python3 tools/ice.py --port /dev/cu.usbmodem24301 memory-dump \
  --output build/memory.bin
```

Wait for receiver STATUS `done` before fetching. The memory responder continues
serving the source after its capture window fills, until the configured idle
interval, STOP, or the overall timeout. `--idle-ms 0` disables idle completion.
An idle interval also applies before the first event; prepare the source before
arming memory, or disable idle completion when operating manually.

For capture without responding, use `state-capture` with the same capture
options and no drive flag. Choose either AS or DS, and assertion (falling) or
release (rising). DS assertion captures valid write data; read data may not
yet be driven. Use DS release to observe completed read data. AS assertion
is an address/control snapshot, and write data is not yet valid there.
The state VCD represents sampled states, not transitions between samples.

## Continuous capture and trigger positions

Both state capture and the updated timing analyzer accept **1..65536 samples**.
Before triggering, a logical circular buffer continually replaces old records.
The comparator is enabled after collecting the selected history quota.

| Position | History before trigger | Trigger and following records |
| --- | --- | --- |
| early | floor(capacity × 10 / 100) | remainder |
| middle | floor(capacity × 50 / 100) | remainder |
| late | floor(capacity × 90 / 100) | remainder |

The trigger sample is the first post-trigger sample. Capacity 1 contains that
sample alone. On a match, excess older history is dropped immediately. Capture
then stops when its post-trigger quota is complete. For state capture, the
match is `(sampled_address & mask) == (address & mask)` on the selected edge;
mask zero matches any address. Triggering does not depend on USB polling.

```sh
python3 tools/ice.py --port /dev/cu.usbmodem24301 capture \
  --bank 0 --samples 65536 --position late --sample-hz 1000000 \
  --trigger-gpio 7 --level 1 --timeout-ms 30000
python3 tools/ice.py --port /dev/cu.usbmodem24301 stop
python3 tools/ice.py --port /dev/cu.usbmodem24301 fetch \
  --capture --output build/timing.vcd
```

The continuous timing path accepts nominal 1 kHz..1 MHz sample rates. Its
trigger GPIO must be inside the selected bank, so the comparator uses the
recorded sample. It reports the actual divider-derived nominal rate. The
original finite 1024-sample **150 MS/s** path remains available with
`capture --burst150`; the original `fixture` command still exercises that
path and any GPIO0..44 may trigger either bank. Fetch those older-format
VCD captures without `--capture`. Continuous 150 MS/s is not implemented.

`stop` gracefully freezes a continuous/state capture and saves only its
collected records, including an empty trace if no events arrived. It works
before or after trigger. Idle completion and the overall timeout also preserve
partial captures, with a completion reason in metadata. `stop --discard`
uses the original abort, error 7, and discards the new job. An existing
persistent capture is not replaced by an aborted or failed acquisition.

## Timing, storage and recovery

A PIO state machine observes the selected strobe with input synchronizers
enabled. It snapshots GPIO0..31 and two counters on each edge. Counter loops
account for idle LOW and HIGH periods and fixed record-emission overhead;
core 1 converts them to 64-bit system-clock timestamps. Strobe polling gives
up to three PIO clocks of edge-detection quantization plus synchronizer delay.
PIO FIFO stalls invalidate the capture; no timestamp is silently stretched.

DMA uses a supported **32 KiB** physical ring at `0x20040000`; core 1 drains it
into a distinct PSRAM logical ring at `0x11040000`. The DMA's monotonically
decreasing transfer count detects consumer overrun, including whole wraps.
Overflow or FIFO stalls fail the job instead of saving an apparently complete
trace. Core 0 serves USB while core 1 acquires and services memory. PSRAM CS is
always GPIO47, with an explicit 8 MiB size; no other CS pin is probed.

Two 1 MiB raw-capture flash slots start at `0x00d80000` and `0x00e80000` on the
16 MiB bench boards. They precede the existing two 256 KiB legacy VCD slots.
Unknown nonblank slot contents are refused. A CRC and final commit word reject
incomplete replacements; each bank is independent. Flash writes happen after
acquisition and output release, with the worker parked and PSRAM cache cleaned.
USB replies can pause during saving. Captures survive reset; live emulated RAM
is retained only until another memory RUN or reset, and downloads after completion.

`fetch --capture` verifies metadata, length, CRC and increasing state timestamps,
then writes `.vcd`, `.bin` and `.json` files. Timestamps in VCD are relative to
the first retained sample, in integer picoseconds. A `TRIGGER` signal marks the
actual trigger record. The raw state format is three little-endian uint32s:
GPIO0..31, timestamp low, timestamp high. Timing records are one uint32 each.
Host conversion avoids a firmware VCD buffer limit for large captures.

Loadable apps now use **ABI 2** at `0x20030000`; regenerate uploaded `.app` files.
The build emits `app_bus_generator`, `app_bus_memory` and `app_state_analyzer`
as `.elf`, `.bin` and `.app` files in each `build/multidrop/{1,2}/` directory,
alongside the two original modules and the dispatcher `.elf`/`.uf2` images.
The original wire framing, protocol version, 16-word STATUS and legacy command
IDs remain unchanged. See [protocol-v1.md](protocol-v1.md) for the RUN extension.

## Reproducible validation

```sh
python3 -m unittest discover -s tools/tests -v
python3 tools/bus_check.py \
  --generator /dev/cu.usbmodem24401 --receiver /dev/cu.usbmodem24301 --full
```

The fixture suite checks RAM contents, read-back verification, all three
trigger positions, AS/DS sampling, address decoding above 64 KiB, idle partial
captures before and after trigger, manual empty stop, raw/VCD CRCs and a
65536-record trace. Generated reports and files go to `build/bus-check/`.
The final results and remaining limits follow.

## Bench evidence, 2026-11-17

Both final dispatcher images were built with Pico SDK 2.3.1, GCC 13.2.1,
CMake 3.28.3, Ninja 1.11.1 and `-Wall -Wextra -Werror`, then USB-loaded with
picotool 2.3.1 and flash read-back verified. Capture processing uses `-O2`.
Board 1 has `bus-generator` loaded and board 2 `bus-memory`, both idle with
outputs released. Their serials and ports are in [dispatcher.md](dispatcher.md).

| Verification | Result |
| --- | --- |
| Host tests | 33 passed, including the actual firmware C ring policy |
| Bus fixture | 11 cases passed; full 1024-byte write/read verification, AS assertion, DS assertion/release, address triggers at 10/50/90, idle partial/empty stop, invalid requests and unmapped-address DTACK timeout |
| Maximum state trace | 65536 records, trigger index 32768, 786432 raw bytes, no FIFO error; raw CRC `ecea67d5` |
| Continuous timing | 24 cases passed: banks 0 and 1 × all three positions; 17 samples at 1 kS/s, and sizes 1, 257 and 65536 at 1 MS/s |
| Original dispatcher checks | 11 passed, including framing/replay, timeout/abort, cross-bank trigger and uploaded ABI 2 modules |
| Original finite 150 MS/s | Both banks: 1024 samples, zero receiver FIFO errors, VCD/raw CRC agreement |
| Persistence | A 262144-byte continuous capture, its metadata and generated VCD were identical before and after SWD reset of both boards |

The full state trace spans about 0.382 seconds at the nominal timestamp clock;
this illustrates the firmware's added wait/idle time rather than an 8 MHz
transaction rate. No external oscilloscope or frequency reference was used.
Bus phase timing and the absolute timestamp clock therefore remain nominal.
State throughput against a faster external producer remains unbenchmarked;
FIFO/consumer overrun detection is implemented. An attempted continuous
5 MS/s run overran and was rejected; the public limit is 1 MS/s. The original
150 MS/s upper-bank capture still shows wire/clock-skew pattern differences;
these observations are retained in its report, with no receiver FIFO errors.

Evidence is retained in [bus-fixture-2026-11-17](validation/bus-fixture-2026-11-17/),
including build versions/hashes, all reports, representative VCDs and the full
maximum-state raw trace. The exact raw CRCs are in the individual metadata.
Local outputs are `build/bus-check/`, `build/continuous-check/`,
`build/bus-legacy-check/`, `build/bus-dispatcher-check.json`,
`build/bus-host-tests.log` and `build/bus-dispatcher-build.log`.

Installed ELF SHA-256:

- Board 1: `aa17ff7e49ff7189a100b639fe83544dd2d0908ef8b38f41d896f8a32c0cb6ab`
- Board 2: `4911e5550410777248ec19f155208806d2b199ba4b45dfe842f642921d7ff58c`

Primary references: Motorola's [M68000 User's Manual, section 4 and figure 4-2](https://datasheets.chipdb.org/Motorola/68000/mc68000_userman.pdf)
and Raspberry Pi's [RP2350 datasheet, PIO and DMA](https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf).
Implementation uses the pinned Pico SDK 2.3.1, including its
[DMA register definitions](https://github.com/raspberrypi/pico-sdk/blob/2.3.1/src/rp2350/hardware_regs/include/hardware/regs/dma.h).
