# Two-bank PIO generator and analyzer

This standalone Core2350B bench fixture generates and captures **GPIO0–31**,
then **GPIO32–44**, in separate runs. Each capture contains **1024 consecutive
samples at nominal 150 MS/s**, using PIO clock divider 1 on both boards.
The generator toggles one successive bit per cycle, wrapping after 32 or 13
pins. No extra clock or trigger wire is needed: GPIO0 or GPIO32 provides the
LOW-to-HIGH start trigger within the selected bank.

The boards now contain the [USB dispatcher](dispatcher.md). Reload the following
images to reproduce this earlier SWD-controlled milestone:

| Role | Board serial | SWD instance | Firmware |
| --- | --- | --- | --- |
| Generator | `F3217B63D8F6A7A5` | 1 | `build/multidrop/1/pio_trace.uf2` |
| Receiver | `AC740FAC748891BF` | 2 | `build/multidrop/2/pio_trace.uf2` |

The receiver saves the actual samples as `LOW32.VCD` and `HIGH13.VCD` in its
16 MiB flash. It exports a **read-only USB mass-storage drive named `ICECAP`**
while idle and disconnects USB during acquisition and flash writing. Captures
are not served during sampling. ROM BOOTSEL exposes its own UF2 programming
disk and cannot expose application files; use `ICECAP` to retrieve VCDs after
capture or after rebooting into the application.

## Repeat the capture

Keep the matching GPIO0–44 wires and shared ground connected. Power both boards
through USB and connect the shared SWD probe. Close other debugger sessions.

```sh
make pio-trace-capture
```

The macOS wrapper unmounts `ICECAP` before each run, prepares the source, arms
the receiver, starts generation through SWD, and leaves both boards' GPIO0–44
as inputs afterward. It waits for flash saving and USB reconnection, reads each
VCD, and checks every value and timestamp against the receiver's 4096-byte SRAM
dump, plus payload lengths and CRC32. A receiver FIFO stall/error or incomplete
DMA transfer rejects the run. Pattern mismatches are reported separately, so
real signal observations are preserved rather than replaced by expected data.

Files on the receiver:

```text
/Volumes/ICECAP/LOW32.VCD
/Volumes/ICECAP/HIGH13.VCD
```

Each command creates `build/debug/pio-trace-*/` containing both VCD copies,
`bank0.bin`, `bank1.bin`, the two OpenOCD logs and `report.json`. The automated
mounted-drive retrieval currently supports macOS. Firmware builds use the
portable Docker toolchain; Linux host retrieval has not been implemented.

To rebuild and program:

```sh
make pio-trace-build
# Request BOOTSEL on each target CDC port; names can change after reconnecting.
python3 tools/pico.py usb-boot --port /dev/cu.usbmodem24401
python3 tools/pico.py usb-boot --port /dev/cu.usbmodem24301
# Wait for both targets to enumerate in BOOTSEL before loading.
picotool info -a
picotool load -v build/multidrop/1/pio_trace.uf2 --ser F3217B63D8F6A7A5
picotool reboot --ser F3217B63D8F6A7A5
picotool load -v build/multidrop/2/pio_trace.uf2 --ser AC740FAC748891BF
picotool reboot --ser AC740FAC748891BF
```

Alternatively copy each UF2 to its correctly identified ROM disk, following
the [multidrop identity precautions](bringup.md#two-boards-on-one-swd-probe-2026-11-15).
`picotool` selects by serial and also works when a ROM disk has not mounted.
The tested host tool is Raspberry Pi picotool 2.3.1, installed with
`brew install picotool`. Firmware loading updates its own flash sectors and
leaves the capture slots intact; a whole-chip erase removes captures.

Interactive inspection uses one `make multidrop-server`, then:

```sh
OPENOCD_EXTERNAL=1 make multidrop-debug INSTANCE=1 FIRMWARE=pio_trace
OPENOCD_EXTERNAL=1 make multidrop-debug INSTANCE=2 FIRMWARE=pio_trace
```

Inspect `board_id`, `trace_control` and receiver `trace_samples`. Resume both
cores and close these sessions before automated capture. GPIO39's LED is part
of the upper-bank pattern, not a software heartbeat.

## Capture implementation

PIO0 SM0 executes one `OUT PINS,32` instruction per source cycle, using
32-bit autopull and an eight-word joined TX FIFO. DMA supplies 2048 states;
the extra states keep generation active beyond the receiver's 1024 samples.
The last state is released after completion. The terminal source TX stall
after this finite burst is expected and recorded separately.

Receiver PIO0 SM0 first waits for LOW then HIGH on the bank's first GPIO,
then executes one `IN PINS,32` per cycle with autopush and an eight-word joined
RX FIFO. The upper bank's input count is 13; unused word bits are masked off.
PIO GPIOBASE is 0 for GPIO0–31 and 16 for GPIO32–44. The SDK relocates WAIT GPIO
and JMP operands when loading programs; the upper-bank trigger and timer use
those relocation rules explicitly.

Receiver SM1 starts synchronously with SM0, observes the same trigger and
counts the capture interval. Its DMA writes zero to PIO CTRL just after the
1024th sample, stopping both state machines without CPU polling or FIFO
overflow. Data DMA transfers exactly 1024 words. The CPU sleeps during the
burst with only completion and timeout IRQs enabled; USB is disconnected and
the host avoids SWD SRAM reads during acquisition. Earlier CPU polling caused
DMA contention and sample gaps; the final results below use the sleeping path.

Both banks retain the input synchronizers. The two boards have independent
12 MHz crystals and PLLs, so the trigger aligns the start but does not share
their sample clocks. Nominal sample spacing is **6.6667 ns**, with VCD times
expressed in integer picoseconds using `floor(i × 10^12 / 150000000)`.
The 1024-clock acquisition window is approximately **6.827 µs**. Absolute clock
frequency and phase were not measured with an external instrument. These two
files cannot be combined into a simultaneous 45-bit observation.

GPIO0–44 idle as inputs with weak pull-downs. Only the source's selected bank
is driven; the receiver always samples inputs. Source drive strength is 4 mA,
or 8 mA on the LED-loaded GPIO39, with fast slew. The source preparation lease
is 2 seconds; generation has a 10 ms timeout, reception a 2 second timeout.
Completion and abort release all tested pins. GPIO45–47 are not initialized
or selected as outputs; no PSRAM or CS discovery is used. This tests native
3.3 V development-board wiring only, not the MC68008 adapter's voltage
protection, passive behavior or external bus timing.

The last **512 KiB** of receiver flash is reserved as two 256 KiB slots at
offsets `0x00f80000` and `0x00fc0000`. Each has a versioned header, a final
commit word and payload CRC32. The VCD formatting buffer is bounded at 192 KiB,
enough even if every bit changes in every sample. Unknown nonblank contents
are refused rather than erased. A new capture replaces only its own bank;
an interrupted replacement may lose that bank, while incomplete records are
excluded from the retrieval disk. The other bank remains independent.
Flash operations run after capture with IRQs masked and core 1 parked in ROM.
The FAT12 disk is generated from validated flash records and rejects writes.

The debugger mailbox is 16 little-endian uint32 words, magic `0x50494f31`,
version 1: `magic`, `version`, `request_seq`, `completed_seq`, `command`, `bank`,
`state`, `error`, `sys_hz`, `samples`, `fdebug`, `dma_remaining`, `vcd_bytes`,
`vcd_crc`, `sample_crc`, `captures`. Commands are 1 prepare/arm, 2 source start,
3 abort/release, 4 reboot. States are 0 idle, 1 prepared/armed, 2 saving, 3 done,
4 error. Settings precede the request sequence; wait for matching completion.
Errors are 1 setup/command, 2 receive timeout, 3 storage. Host tools resolve
mailbox and sample addresses from the matching ELF files.

The USB descriptor adaptation retains TinyUSB's complete MIT notice in
`firmware/trace_usb.c`; other new fixture code uses the repository's Apache-2.0
license. The receiver's `cafe:4003` USB VID/PID is for this development fixture.

Primary references are the [RP2350 datasheet](https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf),
the [SDK 2.3.1 PIO loader](https://github.com/raspberrypi/pico-sdk/blob/2.3.1/src/rp2_common/hardware_pio/pio.c),
and the [Core2350B schematic](https://files.waveshare.com/wiki/Core2350B0/Core2350B.pdf).

## Bench evidence, 2026-11-17

Both images built with SDK 2.3.1 and `-Wall -Wextra -Werror`. The shared probe
used 1 MHz SWD. Toolchain versions are the
[recorded bring-up versions](bringup.md#verification-evidence-2026-11-15), plus
host picotool 2.3.1. Each image was USB-loaded and read-back verified.

| Result | GPIO0–31 | GPIO32–44 |
| --- | --- | --- |
| Samples | 1024 | 1024 |
| Configured PIO/sample clock | 150 MHz | 150 MHz |
| One-bit transitions | 1023 / 1023 | 1023 / 1023 |
| Repeated / multi-bit transitions | 0 / 0 | 0 / 0 |
| Pattern mismatches | 0 | 0 |
| Receiver FDEBUG / DMA words remaining | 0 / 0 | 0 / 0 |
| VCD bytes | 15503 | 14886 |
| VCD CRC32 | `1b4f69cc` | `22955a4b` |
| Raw sample CRC32 | `4e8002d9` | `46055b25` |
| Identical after SWD reset | yes | yes |

The OS mounted and read both files through the receiver's FAT12 MSC drive.
Every exported value and timestamp matched the raw SRAM capture. Both files
were reread and compared byte-for-byte after `reset run` through SWD. Power-cycle
persistence was not separately tested. Eighteen host tests passed, including
trace corruption, wrong-bank/timebase, FIFO stall/incomplete-transfer rejection
and the existing connectivity decoder cases.

Evidence is retained as [the result snapshot](validation/pio-trace-2026-11-17.json)
and [VCD files plus raw samples](validation/pio-trace-2026-11-17/). Full local
artifacts are in `build/debug/pio-trace-ozyeurxi/`, including `reset.log` and
`persistence.json`; build output is `build/pio-trace-build.log`.

Loaded ELF SHA-256:

- Generator: `8f7d3d1f046b511cdaecdcfc80853227956b894e9fc88836b11934dcad6e051f`
- Receiver: `13e6134ac9a5acb74ba6dee55d64cdc78dbee4cea2a09a416522004d41d7b6a5`
