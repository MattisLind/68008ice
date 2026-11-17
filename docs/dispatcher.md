# Core 0 dispatcher and USB command interface

Both Core2350B boards now boot a resident dispatcher on **core 0**. It owns
USB CDC, frame validation, application loading and flash capture storage.
**Core 1** executes a loaded generator or analyzer module, using the shared
PIO/DMA hardware layer. No debugger is needed to start either application.
SWD instance IDs 1 and 2 and USB BOOTSEL recovery remain available.
Dispatcher **0.7.0 exposes CDC only**. The `ICECAP` mass-storage interface and
its `disk` command have been removed; captures still persist in flash and are
downloaded with `fetch`.

This is standalone 3.3 V development-board firmware. The new
[68008 bus fixture and circular capture apps](bus-fixture.md) add a generator,
1 KiB memory/state responder and passive state analyzer. Dispatcher 0.5 also
adds the [CPU reset/NOP/STOP application and boot profile](cpu-emulator.md).
Their bench pin map
differs from the proposed ICE adapter; do not load this image on that adapter.
The examples below describe the original finite 150 MS/s path. Use
`capture --burst150` to select that path explicitly in 0.3; ordinary `capture`
now uses continuous pre/post-trigger acquisition and `fetch --capture`.

| Board | Serial | Tested CDC port | SWD ID |
| --- | --- | --- | --- |
| 1 | `F3217B63D8F6A7A5` | `/dev/cu.usbmodem24401` | 1 |
| 2 | `AC740FAC748891BF` | `/dev/cu.usbmodem24301` | 2 |

Port names can change. The probe's `/dev/cu.usbmodem24202` UART is not a command
port. Both dispatcher images can run either application; the commands below
use board 1 as generator and board 2 as receiver. USB uses the development
VID/PID `cafe:4004`, product `ICE Dispatcher`, and the real board serial.

## Commands

The Python interface uses only the standard library on macOS/Linux. Windows
uses `pyserial` (`python -m pip install pyserial`); that backend has not been
bench tested. Firmware compilation remains in the pinned SDK Docker image.

```sh
python3 tools/ice.py ports
python3 tools/ice.py --port /dev/cu.usbmodem24301 info
python3 tools/ice.py --port /dev/cu.usbmodem24301 list
```

To load and run both applications and download both bank captures:

```sh
python3 tools/ice.py fixture \
  --generator /dev/cu.usbmodem24401 --receiver /dev/cu.usbmodem24301 \
  --source flash --output build/dispatcher-capture
```

This actively drives the generator's selected bank. Only the two fixture
boards should be connected. It runs GPIO0–31 and GPIO32–44 separately, with
1024 samples each at nominal 150 MS/s. Every downloaded VCD value/timestamp
is checked against raw SRAM samples, and frame/file/raw CRC32 values are
verified. FIFO errors and incomplete DMA reject the transfer. Pattern
differences remain in the raw samples and are reported in `report.json`.

For a selected LOW trigger, with both applications loaded through PSRAM:

```sh
python3 tools/ice.py fixture \
  --generator /dev/cu.usbmodem24401 --receiver /dev/cu.usbmodem24301 \
  --source psram --bank 1 --trigger-gpio 44 --level 0 \
  --output build/dispatcher-low
```

The fixture prepares the source HIGH for a LOW trigger, or LOW for a HIGH
trigger. This ensures the analyzer waits until generation starts. Its trigger
must be among the pins generated for that run. The analyzer itself supports
**any selected GPIO0–44 for either bank**, including a pin outside that bank.

To operate the boards independently, run these commands within the 30-second
preparation/trigger timeouts:

```sh
# Prepare the source, holding GPIO0..31 LOW until GO.
python3 tools/ice.py --port /dev/cu.usbmodem24401 generate \
  --bank 0 --source flash --allow-drive --prepare --timeout-ms 30000
# Arm the receiver for GPIO7 HIGH. This returns once armed.
python3 tools/ice.py --port /dev/cu.usbmodem24301 capture --burst150 \
  --bank 0 --trigger-gpio 7 --level 1 --timeout-ms 30000
python3 tools/ice.py --port /dev/cu.usbmodem24401 go
python3 tools/ice.py --port /dev/cu.usbmodem24301 status
python3 tools/ice.py --port /dev/cu.usbmodem24301 fetch --bank 0 --output trace.vcd
```

There is no requirement to use `fixture` or keep a host process connected.
For an immediate finite burst, arm the receiver with `capture`, then invoke
`generate --allow-drive` on the other port without `--prepare`. Each command
operates only its selected board. The 2048-state burst ends in about 13.7 µs,
so the receiver must be armed before that burst; this is not a continuous
pattern generator.

For LOW triggering, add `--initial-high` to `generate` and choose `--level 0`
on `capture`. A level already present when armed triggers immediately; no
preceding opposite level or edge is required. `capture --wait` waits for
completion. `generate` without `--prepare` starts its finite 2048-state burst
immediately and waits for completion. `load analyzer --source flash` loads a
module without running it; `capture`/`generate` perform their own load.

```sh
python3 tools/ice.py --port /dev/cu.usbmodem24301 stop
python3 tools/ice.py --port /dev/cu.usbmodem24301 bootsel
```

For the legacy apps, `stop` wakes the worker, aborts DMA/PIO and releases outputs.
Continuous/state apps instead save a partial capture; `stop --discard` aborts.
An aborted job
retains error 7 in its status for inspection. `bootsel` requires an idle or
finished job; stop a running job first. The 1200-baud recovery path also remains.
On every reset the dispatcher starts with no application loaded and GPIO0–44
as inputs. GPIO35/38/40 have inactive pull-ups for the bench RESET/HALT/BERR
lines; other inputs have pull-downs until configured. Generation requires explicit `--allow-drive` and the protocol's
drive flag. GPIO45/46 are unused; GPIO47 is exclusively PSRAM CS1.

## Loading applications

The default policy is **flash → selected application in SRAM → core 1**.
There is no requirement to preload every application into PSRAM at boot.

| Memory | Purpose |
| --- | --- |
| Flash | Persistent boot code, resident dispatcher/HAL, built-in application catalogue, and saved captures |
| Internal SRAM | One selected application's execution image, worker stack, and timing-sensitive data |
| PSRAM | Optional uploaded image, continuous/state capture ring and legacy VCD formatter |

Keep standard applications in flash alongside the dispatcher. On LOAD, core 0
selects the image, validates ABI/length/CRC, copies its code into the execution
slot, and verifies the copy. RUN then starts it on core 1. The dispatcher stays
resident. The current implementation launches one application at a time per
board; it is not a preemptive scheduler and does not suspend several applications
in the execution slot. Finish or stop the current job before loading another.

PSRAM upload is useful for testing a new module without reflashing. Its image
is volatile and must be uploaded again after reset. The explicit `psram` path
below stages a built-in image through PSRAM to test that loading route; it adds
a copy and is unnecessary for normal flash-resident applications. Standard
modules currently share the dispatcher's firmware update; an independently
updatable flash application partition is not implemented.

```sh
make dispatcher-build
```

Outputs are `build/multidrop/{1,2}/dispatcher.{elf,uf2}` and separately linked
`app_generator.{elf,bin,app}` / `app_analyzer.{elf,bin,app}`. Install each
matching dispatcher UF2 through BOOTSEL/picotool as in
[the PIO programming instructions](pio-trace.md#repeat-the-capture), selecting
`dispatcher.uf2` instead of `pio_trace.uf2`.

Modules are freestanding Cortex-M33 binaries linked at `0x20030000` with a
versioned HAL function table. The generator module constructs the staggered
pattern; the analyzer module arms and runs acquisition. The PIO/DMA HAL is
resident, shared by both modules. Modules return to the resident core-1 worker
after completion and have no independent SDK runtime or global BSS.

`--source flash` copies the built-in image from flash to execution SRAM.
`--source psram` stages that image in PSRAM, then validates and loads it into
execution SRAM. For an image supplied independently over USB:

```sh
python3 tools/ice.py --port /dev/cu.usbmodem24401 upload build/multidrop/1/app_generator.app
python3 tools/ice.py --port /dev/cu.usbmodem24301 upload build/multidrop/2/app_analyzer.app
python3 tools/ice.py fixture \
  --generator /dev/cu.usbmodem24401 --receiver /dev/cu.usbmodem24301 \
  --source uploaded --output build/dispatcher-uploaded
```

Each board has one volatile PSRAM image slot. `uploaded` selects that slot;
`psram` replaces it with a built-in image. Reset loses the uploaded module.
Flash-resident modules are currently built into the dispatcher; USB does not
rewrite the firmware or install persistent third-party modules. Native modules
are trusted code using the same privileges as the dispatcher, not sandboxed
applications.

The 28-byte image header is seven little-endian uint32 values: magic
`0x41505031`, ABI 2, app ID (1 generator / 2 analyzer / 3 bus generator /
4 generic memory and state / 5 passive state / 6 CPU emulator / 7 ABC1600 memory), load address `0x20030000`, Thumb entry
offset 1, code length (2..16384), and code CRC32. Rebuild ABI 1 uploads.
The host and device validate the header, exact length and CRC before loading;
the SRAM copy is checked again. Uploads are bounded and strictly sequential;
commit rejects incomplete or corrupt code. Loading/running is rejected while
another job is active.

PSRAM setup uses **GPIO47 and 8,388,608 bytes explicitly**. No CS GPIO scanning
occurs. The CS pull-down is disabled, CS is pulled HIGH, and setup waits 1 ms
before SDK QPI initialization. Configuration is 75 MHz at the 150 MHz system
clock, with an 8 µs maximum select interval, 50 ns minimum deselect and 1024-byte
page breaks. The SDK registers its CS1 setup callback for later flash operations.
Initialization runs before core 1 and USB start. Uncached startup checks cover
the first 4 KiB, distinct addresses in all eight MiB to catch size aliasing,
and the far-end word. This is not an exhaustive full-memory stress test.
If checks fail, PSRAM loading and capture RUN are unavailable. Flash loading
and the original finite generator remain usable.

## Sampling and storage

The [earlier PIO fixture](pio-trace.md) supplies the one-instruction-per-sample
PIO/DMA engine. Generator PIO0 SM0 emits one changed bit per 150 MHz cycle;
DMA supplies 2048 states. Receiver PIO0 SM0 captures 1024 words, with the
upper bank's 13 input bits masked. SM1 and its DMA stop the sampler just after
the last sample, avoiding a CPU stop and trailing FIFO overflow.

Receiver **PIO1 SM0** waits for the selected GPIO level, then pushes value 3.
A one-shot DMA writes that value to PIO0 CTRL, enabling both sampler state
machines simultaneously. PIO1 chooses its own GPIO window, so its trigger
can be outside PIO0's capture window. Input synchronizers remain enabled.
The trigger precedes sample zero by the synchronizer, PIO and DMA-start
latency; this is not pre-trigger capture or zero-latency sampling. For the
tested same-bank generator pattern, GPIO0 HIGH started at pattern offset 7,
and GPIO7 HIGH at offset 14. No GPIO output is needed for triggering.

The dispatcher and DMA use separate physical SRAM banks:

| Address range | Owner |
| --- | --- |
| `0x20000000..0x2002ffff` | Core 0 data, USB and metadata |
| `0x20030000..0x20033fff` | Loaded ABI 2 module |
| `0x20050000..0x20051fff` | 2048-word generator DMA pattern; isolated from dispatcher SRAM traffic |
| `0x2003f000..0x2003ffff` | Core 1 stack reservation |
| `0x20040000..0x20047fff` | 32 KiB continuous acquisition DMA ring |
| `0x20080000..0x20080fff` | Legacy 1024-word full-rate capture; dedicated bank 8 |
| `0x20081000..0x20081fff` | Core 0 stack reservation; bank 9 |
| `0x11040000..0x110fffff` | PSRAM logical capture ring, up to 65536 × 12 bytes |
| `0x11200000..0x1122ffff` | Legacy VCD formatter in PSRAM |

Core 1 sleeps during DMA. Core 0 can continue servicing CDC while the analyzer
waits and samples, without competing for the acquisition DMA's SRAM banks. DMA completion, timeout and
the inter-core abort IRQ wake core 1. The source preparation timeout and receiver
trigger timeout are bounded to 10..30000 ms; source transfer has a 10 ms bound.
PIO0/PIO1 and three DMA channels are owned by the worker's HAL.

The two boards still have independent crystals and unequal wire/pad delays.
Some captures have repeated samples followed by two-bit changes, with zero
receiver FIFO errors. This is consistent with the user-observed clock-phase
and wire-length skew. Full-rate sampling preserves those observations; it
does not reconstruct an ideal pattern. No shared sampling clock or external
clock-frequency measurement has been added. Nominal spacing remains 6.667 ns.

After acquisition, core 0 formats VCD and uses SDK inter-core lockout while
writing flash. Core 1 parks in SRAM during flash erase/program; CDC responses
can pause during this bounded save. Each bank replaces its own existing
256 KiB slot in the last 512 KiB of flash, using the earlier bounded formatter,
commit marker, ownership guard and CRC. FIFO errors, timeout and abort do not
save an incomplete capture. VCD comments retain trigger GPIO/level; header
reserved words 0/1 contain GPIO+1 and level (GPIO+1 zero means unspecified).
Each successful capture remains in flash after reset. An interrupted write
may lose that bank's newest capture; it does not provide a two-copy journal.

Download stored captures directly through CDC:

```sh
python3 tools/ice.py --port /dev/cu.usbmodem24301 fetch --bank 0 --output LOW32.VCD
python3 tools/ice.py --port /dev/cu.usbmodem24301 fetch --bank 1 --output HIGH13.VCD
```

There is no application mass-storage interface, FAT filesystem or disk mode
in dispatcher 0.2.0. Command ID 10 is retired and returns unknown-command.
`trace_disk.c` remains only in the earlier standalone `pio_trace` milestone;
it is excluded from the dispatcher build. ROM BOOTSEL retains its programming
disk for firmware recovery.

## Initial dispatcher 0.1 validation, 2026-11-17

Both installed images built with SDK 2.3.1, `-Wall -Wextra -Werror`, and were
picotool-loaded/read-back verified. Host tests exercise the actual C parser
through Python/ctypes, including all escaped byte values, fragmentation,
overflow/resynchronization, malformed lengths/versions/status, corruption and
module headers. **24 host tests passed** including the earlier trace/connectivity tests.

```sh
python3 -m unittest discover -s tools/tests
python3 tools/dispatcher_check.py \
  --generator /dev/cu.usbmodem24401 --receiver /dev/cu.usbmodem24301
```

Ten hardware acceptance checks passed: runtime core numbers and PSRAM checks,
drive permission and GPIO bounds, CRC rejection, duplicate GO replay after
completion, CDC responsiveness while armed, timeout, abort, an already-active
LOW level, GPIO44 triggering lower-bank capture, corrupt executable rejection,
and valid module upload/load (some are grouped in the ten report entries).
The final measured abort response was about **0.55 ms**. Captures were validated
through CDC against raw SRAM, then through the OS-mounted MSC drive. Both files
were downloaded again after an SWD reset and compared byte-for-byte. Startup
reported core 0 dispatcher / core 1 worker, app 0, disk off, PSRAM 8 MiB.
Power-cycle persistence was not separately tested.

| Final run | Trigger | FIFO errors | One-bit / repeated / multi-bit transitions |
| --- | --- | --- | --- |
| Flash, lower bank | GPIO0 HIGH | 0 | 1023 / 0 / 0 |
| Flash, upper bank | GPIO32 HIGH | 0 | 909 / 57 / 57 |
| PSRAM, upper bank | GPIO44 LOW | 0 | 1023 / 0 / 0 |
| USB-uploaded PSRAM, lower bank | GPIO7 HIGH | 0 | 1023 / 0 / 0 |

Earlier runs also captured both banks cleanly from flash and observed skew in
PSRAM-loaded runs; source memory selection does not synchronize the crystals.
All final runs transferred exactly 1024 samples at configured 150 MHz.
The skewed upper-bank file is retained as observed, with 144 pattern mismatches.

Retained evidence: [dispatcher-2026-11-17](validation/dispatcher-2026-11-17/).
Full local outputs are `build/dispatcher-final-flash/`,
`build/dispatcher-final-low/`, `build/dispatcher-final-uploaded/`,
`build/dispatcher-check.json`, `build/dispatcher-reset.log` and
`build/dispatcher-build.log`. SDK/compiler/probe versions remain the
[recorded bring-up toolchain](bringup.md#verification-evidence-2026-11-15);
native picotool is 2.3.1. SWD reset used the existing 1 MHz shared probe.

Initial 0.1 ELF SHA-256 (superseded by the 0.2 images below):

- Board 1: `a6e0764c29b1283da84e678e045949839c142aba6074122b2f0c1cacc4aa6515`
- Board 2: `97c6894d884f38b07f762ad2fe06aa344243998f280f6cb610852ca2f8d2d992`

## CDC-only dispatcher 0.2 validation, 2026-11-17

Both updated images built with `-Wall -Wextra -Werror` and were USB-loaded and
read-back verified. All 24 host tests passed. Eleven hardware acceptance report
entries passed, including rejection of the retired disk command. macOS
enumerated exactly two interfaces per board, using AppleUSBACMControl and
AppleUSBACMData, with no storage interface. HELLO reports `dispatcher-0.2`.

Independent operation was exercised as three separate host processes: arm the
receiver for GPIO7 HIGH, start the generator without preparing the other board,
then fetch the resulting VCD through CDC. Both banks were also repeated through
the fixture: 1024 samples each at nominal 150 MS/s, zero FIFO errors and complete
raw/VCD CRC agreement. The observed clock/wire skew remained in the captures.

Evidence: [dispatcher-cdc-2026-11-17](validation/dispatcher-cdc-2026-11-17/).
Local outputs: `build/dispatcher-cdc-check.json`, `build/dispatcher-cdc-usb.json`,
`build/dispatcher-independent.vcd`, `build/dispatcher-cdc-capture/` and
`build/dispatcher-build.log`.

Dispatcher 0.2 ELF SHA-256 (superseded by 0.3):

- Board 1: `90b9ad2257811748d999c6fe92311a9e81ef2c2b5f423e5727be5f28fc622f67`
- Board 2: `88491f7a7231fb93cce26fcbfffefc759d337b4d2992aed6ab0839a0d4aea2ad`

Primary references: [RP2350 datasheet](https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf),
[SDK 2.3.1 PSRAM implementation](https://github.com/raspberrypi/pico-sdk/blob/2.3.1/src/rp2_common/hardware_psram/psram.c),
and [SDK 2.3.1 multicore implementation](https://github.com/raspberrypi/pico-sdk/blob/2.3.1/src/rp2_common/pico_multicore/multicore.c).
The SDK's BSD-3-Clause code is linked normally; the existing TinyUSB descriptor
adaptation retains its full MIT notice. New dispatcher/host code uses Apache-2.0.

The wire format and complete command table are in [protocol-v1.md](protocol-v1.md).

## Bus/circular-capture dispatcher 0.3, 2026-11-17

The 0.3 images introduced three additional loadable bus/state apps,
configurable circular capture, 10/50/90-percent history, address triggers,
graceful partial stop and host VCD conversion. Continuous timing supports
1 kHz..1 MHz; the original finite 150 MS/s mode remains available. Module ABI
is 2; uploaded ABI 1 files need rebuilding. The original 11 dispatcher hardware
checks passed again, alongside 11 bus fixture cases, 24 continuous timing cases
and 33 host tests. A saved capture survived SWD reset byte for byte.
See [bus-fixture.md](bus-fixture.md) for wiring, commands, final installed ELF
hashes, retained evidence and measured limits.

## Combined memory/timing dispatcher 0.4

`memory --timing150` prepares a simultaneous memory responder and 150 MS/s
timing sampler with a 1..4096-sample hardware-triggered window. The client
starts acquisition after the arm reply; USB pauses during full-rate sampling.
The generator's no-wait sequence was corrected to eight half-states. Builds,
39 host tests and all 11 dispatcher hardware checks pass. Both installed
boards captured single reads/writes with 4096 samples, DS at index 2048 and
FDEBUG zero. Early/late placement, a 2.5-second pre-trigger wait and a 100 ms
no-trigger timeout also pass. The responder adds one or two wait states;
see [single-cycle-timing.md](single-cycle-timing.md) for retained waveforms,
wiring (including the local GPIO32 permit), limits and commands.

## CPU reset/STOP dispatcher 0.5

The new CPU module and memory boot profiles use the shared PIO bus engine.
The portable reset/NOP/STOP core is separate from GPIO/PIO and can be tested
on the host. Built-in LIST now has six images; image ABI 2 is unchanged.
Commands 19/20 report stopped CPU registers and memory-side reset/HALT/FC
observations. Existing apps and captures retain their formats. Both boards
were USB-programmed with verification; STOP, NOP/STOP, reset-vector BERR halt,
no-reset timeout and abort passed. The full existing bus regression and
150 MS/s read/write phase checks also passed after extracting the shared
bus engine. See [CPU workflow](cpu-emulator.md) and
[dated evidence](validation/cpu-emulator-2026-11-17/README.md).

## ABC1600 dispatcher 0.6

The [ABC1600 workflow](abc1600.md) uploads a CRC-checked ROM into a separate
1 MiB PSRAM target map and executes five instructions through the PIO bus.
Instruction-budget completion now pauses successfully. New commands upload
and read back ROM/RAM, expose all CPU registers and retrieve a bounded trace
of reset and instruction snapshots. Both reset-cause branch paths are bench
verified against bus samples and host/Musashi state. CPU memory writes need
additional opt-in. The old STOP/HALT and full bus fixture regressions passed.
See [dated evidence](validation/abc1600-2026-11-17/README.md).

## Separate memory applications, dispatcher 0.7

App 4 is the generic memory backend (`generic-memory`, with `bus-memory` kept
as a compatibility name); app 7 is the new `abc1600-memory` backend. Both
share the state analyzer and physical responder. The ABC1600 backend implements
boot ROM mirrors, task/segment/page registers, translated RAM, cause state and
protection faults from the local MAME MAC model. Command 28 and READ kinds
5/6/7 expose MAC diagnostics, physical RAM and its mapping tables. CPU snapshot
capacity is now 128. The 105-instruction ROM run, generic five-instruction run,
and prior fixture regressions are documented in the
[ABC1600 guide](abc1600.md).
