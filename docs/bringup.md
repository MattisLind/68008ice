# Core2350B build and debug bring-up

Validated on 2026-11-15 with the attached Waveshare Core2350B and Raspberry Pi
Debug Probe. This is standalone development-board firmware. **Do not load blink
on the ICE adapter: GPIO39 is target RESET_N there.**

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

References: [Raspberry Pi Debug Probe workflow](https://www.raspberrypi.com/documentation/microcontrollers/debug-probe.html),
[official SDK 2.3.1](https://github.com/raspberrypi/pico-sdk/tree/2.3.1), and
[official tool binaries](https://github.com/raspberrypi/pico-sdk-tools/releases/tag/v2.3.1-0).
