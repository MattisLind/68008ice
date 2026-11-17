# Core2350B build and debug bring-up

Validated on 2026-11-15 with the attached Waveshare Core2350B and Raspberry Pi
Debug Probe. This is standalone development-board firmware. **Do not load blink
on the ICE adapter: GPIO39 is target RESET_N there.**

The latest loaded application is the [core 0 USB dispatcher](dispatcher.md),
with flash/PSRAM-loaded core 1 applications and the Python `tools/ice.py` CLI.
Both GPIO banks have been captured through USB commands, with selected HIGH/LOW
level triggering, timeout/abort and CDC/VCD transfer verified. The dispatcher
starts idle and exposes only CDC, with no mass-storage interface. Match the ELF to the
loaded application when debugging.

The earlier [two-bank PIO trace fixture](pio-trace.md) provided:
separate GPIO0–31 and GPIO32–44 captures, 1024 samples each at nominal 150 MS/s,
with flash-backed VCD files on the receiver's `ICECAP` drive. Both banks matched
the test pattern without receiver FIFO stalls and survived an SWD reset.
The earlier [GPIO0–44 connectivity fixture](gpio-connectivity.md) was tested
2026-11-16: all 45 pins passed LOW/HIGH patterns in both directions after
the user reflowed the GPIO6 solder joints. Earlier, all GPIO0–38
passed after GPIO2's solder repair. The blink and GPIO-link sections below retain the
earlier applications' commands and evidence; match the ELF to the loaded image.

The [Waveshare schematic](https://files.waveshare.com/wiki/Core2350B0/Core2350B.pdf)
shows an active-high red LED on GPIO39 through 470 Ω, W25Q128 flash (16 MiB),
a 12 MHz crystal, and PSRAM CS on GPIO47. The custom SDK board header selects
RP2350B's 48 GPIOs; using Pico 2's RP2350A definition would be incorrect for GPIO39.
The supplied board has PSRAM, but blink does not initialize or test it. Capacity
and PSRAM QMI timing remain a later milestone; never discover CS by driving
GPIO0/8/19, which carry target address signals in the ICE design.

## Setup and daily use

The host needs Docker, Python 3 and Make. Start Docker Desktop first on macOS.
Connect the probe USB, connect its D/SWD port to board SWCLK/GND/SWDIO, and power
the Core2350B separately through its USB adapter. The debug connector supplies
no target power. The target's USB connection also carries blink's USB serial log.

```sh
make setup        # Build toolchain image; download/checksum host OpenOCD on macOS
make probe        # Identify probe and both Cortex-M33 cores, without flashing
make blink        # Configure and compile Debug ELF, UF2, BIN and HEX
make program      # Build, SWD flash, verify every loaded section, reset and run
make debug-check  # Program, then exercise the debugger and restore normal blink
make debug        # Program, then open container GDB stopped at main
```

Normal blinking is 500 ms per state, or one on/off cycle per second. USB output
reports `blink_count`, GPIO number, state and period. The three `volatile`
variables `blink_count`, `led_state` and `blink_period_ms` are visible through GDB.
The default build uses `-Og -g` for useful source debugging.

At the `make debug` GDB prompt:

```gdb
break blink_tick
continue
next
print blink_count
print led_state
set variable blink_period_ms = 100
delete breakpoints
continue
# Press Ctrl-C to halt; inspect variables/registers while stopped.
print blink_count
info registers pc sp xpsr
monitor reset run
detach
quit
```

`next` steps a source line; `stepi` steps one machine instruction. `continue`
resumes execution. Halting the core freezes this software-driven LED at its
current state. Reset restores the 500 ms period. Other future hardware such as
PIO/DMA may continue while the CPU is halted and needs its own safe-stop design.

`make monitor` lists candidate CDC ports if `PORT` is omitted. Choose the
**target** port, rather than the Debug Probe's UART bridge. On the tested Mac:

```sh
make monitor PORT=/dev/cu.usbmodem1101
# Bounded read, useful for automation:
python3 tools/pico.py monitor --port /dev/cu.usbmodem1101 --seconds 3
```

The target was `/dev/cu.usbmodem1101`; the probe UART was
`/dev/cu.usbmodem2402`. These names can change after reconnecting. No UART wiring
is needed for the target USB log, and no extra Python packages are required.

## Container and USB access

All firmware compilation, UF2 conversion and GDB run in `68008ice-pico:2.3.1`.
Sources and build output are mounted at `/work`. `make shell` opens the build
container; `make versions` prints its tools. The SDK source revision and vendor
binary SHA-256 checksums are pinned in [the Dockerfile](../docker/Dockerfile).
Ubuntu package versions are resolved at image-build time; the recorded versions
below describe the image tested here.

On **macOS**, OpenOCD runs natively from `build/tools/openocd` because Docker
Desktop's Linux VM does not receive ordinary macOS USB devices through
`--device`. Container GDB connects to `host.docker.internal:3333`. This bridge
has been tested with the attached probe. Only the GDB listener is enabled, bound
to host loopback. No USB/IP server or privileged container is needed.
[Docker USB/IP documentation](https://docs.docker.com/desktop/features/usbip/)
describes a separate USB-forwarding option; this project uses OpenOCD's GDB bridge.

On **native Linux**, the wrapper runs OpenOCD in the image too, binding
`/dev/bus/usb`, allowing USB character-device major 189, and using host networking
with loopback GDB. It does not use `--privileged`. This branch is provided but
has not been exercised against hardware; the actual hardware verification used
macOS/arm64. Linux image support covers arm64 and amd64; only arm64 was built here.
Windows/WSL2 USB forwarding is not configured or tested.

For a separate IDE or persistent server:

```sh
# Host terminal 1; keep it running:
make debug-server
# Host terminal 2; connect to that existing server:
OPENOCD_EXTERNAL=1 make debug
```

Without `OPENOCD_EXTERNAL=1`, the wrapper starts and stops its own OpenOCD server.
Only one OpenOCD instance may own the probe. Optional environment overrides are
`DEBUG_PROBE_SERIAL`, `OPENOCD` (macOS binary path, adjacent `scripts/` directory),
`DOCKER`, `PICO_IMAGE`, and `GDB_ENDPOINT`. Use `DEBUG_PROBE_SERIAL` if more than
one CMSIS-DAP probe is attached.

## BOOTSEL recovery

SWD programming needs no BOOTSEL button. As a fallback, hold BOOT and press/release
RESET to expose the RP2350 ROM disk, then:

```sh
make uf2
# For another mount point, including Linux:
make uf2 BOOT_VOLUME=/media/your-user/RP2350
```

The wrapper checks `INFO_UF2.TXT` for RP2350 identification before copying
`build/firmware/blink.uf2`. The copy/reboot path was not exercised in this session;
all actual programming used SWD. The application also enables Pico SDK USB stdio
and its standard recovery interface.

## Verification evidence, 2026-11-15

| Item | Observed result |
| --- | --- |
| Host | macOS 27.0.1, arm64; Docker Desktop 4.94.0 / Engine 29.8.2 |
| SDK | 2.3.1, `079c6f39023649b154152db30f1d781e884879bc` |
| Arm compiler | GCC 13.2.1, Ubuntu `15:13.2.rel1-2` |
| Build tools | CMake 3.28.3, Ninja 1.11.1 |
| Debugger | GDB 15.1; Raspberry Pi OpenOCD `0.12.0+dev-gacff23f` |
| picotool | 2.3.1, official `v2.3.1-0` tools release |
| USB probe | Raspberry Pi CMSIS-DAPv2, `2e8a:000c`, serial `E665D0C59B5A3A25` |
| Probe firmware | OpenOCD reports 1.0.1 and uses its older-firmware workaround; successful at 1000 kHz SWD |
| MCU | OpenOCD reports RP2350 rev 3 and both Cortex-M33 r1p0 cores; 8 breakpoints / 4 watchpoints each |
| Flash | SFDP ID `0x184020`, 16384 KiB, 4096 sectors |
| Programming | 30,276 loaded bytes; all six loadable sections matched during GDB read-back |
| Breakpoint / step | Stopped in `blink_tick`; instruction step moved PC `0x100001e0` → `0x100001e2` |
| Resume / halt | Counter advanced 0 → 4 while running; stayed 4 for 1.1 s while halted |
| Live modification | Set period to 100 ms; observed 13 toggles over the next 1.6 s; reset restored 500 ms |
| Interactive GDB | `make debug` stopped at `main`; `continue` ran; Ctrl-C halted at `blink_count=24`; variable/register reads worked |
| USB runtime log | Successive lines reported GPIO39 states 0/1 with `period_ms=500` |

The firmware/variables and USB log confirm program execution and GPIO writes;
this session did not optically measure the LED or scope its output waveform.
Neither the ICE adapter nor bus timing, passive capture, PSRAM operation or CPU
emulation has been validated by this blink milestone.

Artifacts: `build/firmware/blink.elf`, `.uf2`, `.bin`, `.hex`, `.dis`, `.elf.map`
and `compile_commands.json`. Repeatable checks are `make setup`, `make program`,
`make debug-check`, `make versions` and the bounded USB read above. Logs are in
`build/debug/probe.log`, `flash.log`, `check.log` and `openocd.log`; the latter is
overwritten on each managed server run. Everything under `build/` is disposable.
This table retains the results without committing downloaded tools or SDK code.

## Second Core2350B verification, 2026-11-15

Flashed the same existing `build/firmware/blink.elf` to the second board using
the same probe and Docker image. The build reported no work to do. The ELF
SHA-256 was `b574b9d46943620a34e69807a9e8108989b241161f0636ba3b7620fbe2cca35b`.

| Check | Observed result |
| --- | --- |
| Target identity | USB serial `AC740FAC748891BF`; reading SDK `retrieved_id.id` through GDB returned the same ID, confirming the second board |
| Probe / target | Probe `E665D0C59B5A3A25` at 1000 kHz; both Cortex-M33 cores detected; RP2350 rev 3, 16 MiB flash, SFDP ID `0x184020` |
| Flash read-back | All six loadable sections matched, 30,276 bytes total |
| Breakpoint / single-step | Hardware breakpoint reached `blink_tick`; PC advanced `0x100001e0` → `0x100001e2` |
| Resume / halt | Counter advanced 0 → 4 while running and remained 4 during a 1.1 s halt |
| Live variable update | Changed period to 100 ms; 13 toggles over 1.6 s; reset restored 500 ms |
| Interactive control | Stopped at `main`, continued, then halted with Ctrl-C at counter 22; register and variable inspection succeeded |
| Runtime / final state | Target USB `/dev/cu.usbmodem1101` reported alternating GPIO39 states at 500 ms; board left running normal blink |

Reproduction used `DEBUG_PROBE_SERIAL=E665D0C59B5A3A25 make debug-check`, then
`DEBUG_PROBE_SERIAL=E665D0C59B5A3A25 python3 tools/pico.py debug` for interactive
control and board identification. The board ID was read at the GDB prompt with:

```gdb
python print(bytes(gdb.parse_and_eval('retrieved_id.id')[i] for i in range(8)).hex().upper())
```

The bounded USB monitor command above confirmed execution after debugger detach.
Current logs are in `build/debug/`; this section retains the second-board results.
The earlier PSRAM, optical LED and ICE/bus-validation limits still apply.

## Two boards on one SWD probe, 2026-11-15

**Verified:** both standalone Core2350B boards share SWCLK, SWDIO and GND with
one Raspberry Pi Debug Probe. Each board remains USB powered. Two concurrent
GDB sessions independently controlled the boards through one OpenOCD process
at **1000 kHz SWD**, using the same SDK, Docker image and OpenOCD versions above.
This test covers the development boards, not the proposed ICE bus fixture.

| Board | USB/chip serial | SWD instance | DLPIDR | GDB port | Observed target CDC |
| --- | --- | --- | --- | --- | --- |
| 1 | `F3217B63D8F6A7A5` | 1 | `0x10000001` | 3333 | `/dev/cu.usbmodem24401` |
| 2 | `AC740FAC748891BF` | 2 | `0x20000001` | 3334 | `/dev/cu.usbmodem245201` |

The probe serial is `E665D0C59B5A3A25`; `/dev/cu.usbmodem24302` was its unused
UART bridge. CDC names can change after reconnecting.

The ROM's `RP2350` mass-storage disks accept **UF2 firmware**, not persistent text
configuration files. `ICE_SWD_INSTANCE_ID` is therefore compiled into each
blink image. At application startup the firmware writes the password-protected
`POWMAN.DBGCONFIG.DP_INSTID` register before USB initialization. Nothing is burned
into OTP. The address is restored by firmware each time that application boots.
The normal single-board build retains ID zero by default.
[Official SDK register definition](https://github.com/raspberrypi/pico-sdk/blob/2.3.1/src/rp2350/hardware_regs/include/hardware/regs/powman.h#L1925)

```sh
make multidrop-build
# Put each board into BOOTSEL and check its RP2350 INFO_UF2.TXT first.
# These were the mount names during this test; confirm them after reconnecting.
cp build/multidrop/1/blink.uf2 /Volumes/RP2350/blink-swd1.uf2
cp build/multidrop/2/blink.uf2 '/Volumes/RP2350 1/blink-swd2.uf2'
# Wait for both applications to boot and enumerate as USB CDC devices.
make multidrop-probe
make multidrop-check
```

`multidrop-probe` examines both cores on each chip. `multidrop-check` opens two
live GDB clients and verifies unique physical board IDs, the actual DP_INSTID
register, hardware breakpoints and instruction stepping in `blink_tick`, and
live writes of `blink_period_ms`. In the recorded run, each board advanced
**17 ticks over 1.6 seconds at a 100 ms period while its partner's counter stayed
unchanged under halt**. Both sessions remained connected throughout. Core 1
was examined and grouped with core 0 for halt/resume; it remains parked in ROM
and did not execute a separate test application. Cleanup restored both boards
to the normal 500 ms period and resumed them. Subsequent USB logs from both
boards confirmed their identities and normal alternating GPIO39 states.

Artifacts are `build/multidrop/{1,2}/blink.{elf,uf2,bin,hex}` and associated map
and disassembly files. The loaded ELF SHA-256 values were:

- Board 1: `6bcebb15ec622826f9858e639c4dadad1db2dcdeb8c0898228a1591b1b9a493a`
- Board 2: `1ee4d092f1a7053521a24879fc7e2d8eec72378f4cb2ed315d4ff3975a9ad57c`

Probe evidence is in `build/debug/multidrop-probe.log`. The passing concurrent
test produced `build/debug/multidrop-check-iyp2pjt1/board{1,2}.log` and `.json`;
later runs create new directories. The shared server log is
`build/debug/multidrop-openocd.log`. Test servers terminate after each check,
leaving both boards running.

For interactive debugging, keep **one shared server** running in a terminal:

```sh
make multidrop-server
```

Open each client in its own terminal:

```sh
OPENOCD_EXTERNAL=1 make multidrop-debug INSTANCE=1
OPENOCD_EXTERNAL=1 make multidrop-debug INSTANCE=2
```

Each client uses its matching ELF and attaches without reset. Use `continue`,
Ctrl-C, `break blink_tick`, `stepi`, and variable inspection normally. When
finished, use `monitor resume`, `detach`, then `quit` to leave that board running.
The server exposes only loopback GDB ports 3333/3334, with no Tcl/Telnet listeners.
Two Cortex-M33 cores are grouped **within each chip**, never across the chips.

Limitations: the current configuration is for attach/debug, with no flash
driver or reset/rescue hooks. Do not use the ordinary ID-zero `make program`,
`make debug` or `make debug-check` while these two nonzero-ID images share SWD.
Both chips use ID zero in ROM before the applications assign distinct IDs;
avoid debug traffic until both applications have started. Power-cycle/reset
recovery, connect-under-reset and debugger-initiated reprogramming were not
validated here. If an application cannot assign its ID, use its own USB BOOTSEL
recovery path and disconnect the partner's SWD when necessary to avoid duplicate
IDs. The probe's existing firmware 1.0.1 worked using OpenOCD's compatibility
workaround; it was not updated. PIO/DMA stopping and ICE output release remain
separate work; these tests run only the standalone software blink.

## GPIO0 link and opposite LEDs, 2026-11-15

**Application tested in this section:** `gpio_link`, a separate standalone bench demo
from the original `blink` application. The user connected GPIO0 on both boards
through **470 ohms**; the shared SWD connection provides common ground.

| Role | USB/chip serial | SWD instance | GPIO0 | GPIO39 LED |
| --- | --- | --- | --- | --- |
| Source | `F3217B63D8F6A7A5` | 1 | Output, toggles with its LED | Toggles every nominal 500 ms |
| Receiver | `AC740FAC748891BF` | 2 | Input, internal pulls disabled | Inverse of sampled GPIO0 |

Only the source enables GPIO0 output. The receiver samples the input once at
startup, then updates its LED from interrupts on both rising and falling
edges. USB logging runs outside the interrupt. The LEDs have opposite states
on each settled half-cycle (nominal one-second full cycle); IRQ response and
the source's two GPIO writes introduce a small unmeasured transition skew.
This is not a cycle-accurate phase or latency measurement. GPIO39 is active
HIGH on these bench boards. **Do not load these images on the ICE adapter:**
GPIO0 is a target address and GPIO39 is target RESET there.

Both roles build with the existing SDK 2.3.1/Docker/OpenOCD toolchain above:

```sh
make gpio-link-build
```

This builds `build/multidrop/1/gpio_link.{elf,uf2,bin,hex}` and the matching
`build/multidrop/2/` outputs, plus maps/disassembly, while retaining the original
`blink` targets. Load each image into its matching physical board. The USB
reset path was exercised without pressing BOOTSEL or rewiring SWD:

```sh
# Source: observed CDC port during this session.
python3 tools/pico.py usb-boot --port /dev/cu.usbmodem24401
# Wait for /Volumes/RP2350, check INFO_UF2.TXT and the USB chip identity.
cp build/multidrop/1/gpio_link.uf2 /Volumes/RP2350/gpio-link-source.uf2
# Wait for the source to reboot and its ROM disk to disappear.

# Receiver: observed CDC port during this session.
python3 tools/pico.py usb-boot --port /dev/cu.usbmodem245201
# Wait for the receiver's RP2350 disk and check its identity.
cp build/multidrop/2/gpio_link.uf2 /Volumes/RP2350/gpio-link-receiver.uf2

# After both applications have started:
make gpio-link-check
```

CDC ports and volume names can change. The SDK's USB stdio reset is requested
by changing baud rate to 1200; macOS may report device-disconnect ENXIO/EIO
during the successful request. The wrapper tolerates that disconnect, but the
operator must still check that the expected ROM disk appears. No OTP is changed.

**Measured result:** the shared 1 MHz SWD probe examined all four cores. The
final GPIO check obtained **15 stable samples** covering both LOW and HIGH,
with matching actual GPIO0 input levels at both ends of the resistor. Source
GPIO0 output enable was 1, receiver output enable 0. Both LED output enables
were 1, and GPIO39 input levels and output latches agreed with:

| GPIO0 at both boards | Source LED | Receiver LED |
| --- | --- | --- |
| 0 | 0 | 1 |
| 1 | 1 | 0 |

The check reads SIO registers while both programs run; it brackets each receiver
sample with source reads and discards a crossing edge. Five crossing samples
were discarded. An earlier check that halted the chips separately intermittently
observed a stale receiver LED around an edge. It was replaced with the running
check to avoid interfering with interrupt servicing; the exact halt-time cause
was not established. No firmware change was needed for the passing running
check. This check does not measure edge latency or independently verify optical
LED output, analog voltage margins, or the 470 ohm value.

Subsequent runtime logs showed alternating `gpio0=1 led=1` / `gpio0=0 led=0`
on the source and `gpio0=1 led=0` / `gpio0=0 led=1` on the receiver. The board
identities matched the table. Both boards were left running this demo.
The reproducible hardware check is [gpio-link-check.tcl](../tools/debug/gpio-link-check.tcl),
with output in `build/debug/gpio-link-check.log`. Loaded ELF SHA-256 values:

- Source: `2b2b4c06ca2b0c2ab99c237f7e98dcde1a6579a77554aee4733f6111c86947f1`
- Receiver: `a86025ec7661831152726fb1e48609bcb09e78ade1d2d6595719b73524c4329e`

For interactive debugging use the matching ELF, keeping one server running:

```sh
make multidrop-server
# Separate client terminals:
OPENOCD_EXTERNAL=1 make multidrop-debug INSTANCE=1 FIRMWARE=gpio_link
OPENOCD_EXTERNAL=1 make multidrop-debug INSTANCE=2 FIRMWARE=gpio_link
```

Halting the source freezes GPIO0; a running receiver holds the inverse of that
level. Halting the receiver prevents it servicing GPIO edges until resumed.
Use `make gpio-link-check` with the current images. `make multidrop-check`
belongs to the original independent-blink firmware and must not be run against
this application's different ELF and behavior.

References: [Raspberry Pi Debug Probe workflow](https://www.raspberrypi.com/documentation/microcontrollers/debug-probe.html),
[official SDK 2.3.1](https://github.com/raspberrypi/pico-sdk/tree/2.3.1), and
[official tool binaries](https://github.com/raspberrypi/pico-sdk-tools/releases/tag/v2.3.1-0).
