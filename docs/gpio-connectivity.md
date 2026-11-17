# GPIO0–44 connectivity fixture

The two standalone Waveshare Core2350B boards were tested with `gpio_connectivity`, controlled
through one Raspberry Pi Debug Probe on shared multidrop SWD. This is a bench
wiring test, **not ICE bus firmware**. GPIO0–44 carry CPU signals on the proposed
ICE, so these images must not be loaded onto that adapter.

## Observed result, 2026-11-16

| Board | USB/chip serial | SWD instance | CDC port during programming |
| --- | --- | --- | --- |
| 1 | `F3217B63D8F6A7A5` | 1 | `/dev/cu.usbmodem24401` |
| 2 | `AC740FAC748891BF` | 2 | `/dev/cu.usbmodem24301` |

### Latest GPIO0–44 scan

**All 45 same-number paths pass after the GPIO6 solder reflow.** The full
LOW/HIGH scan was repeated without reflashing after the user reflowed the
solder joints. GPIO6 now follows both driven levels in both directions, as do
all other pins, including GPIO39–44 and the repaired GPIO2. No missing, crossed,
bridged, unstable, or held-level paths were detected within GPIO0–44. The latest per-pin snapshot is
[gpio-connectivity-0-44-2026-11-16.csv](validation/gpio-connectivity-0-44-2026-11-16.csv).

Before reflow, two expanded scans passed 44 of 45 paths. GPIO6 on either board
read local 0 / remote 1 when driven LOW, and local 1 / remote 0 when driven HIGH;
no other receiver pin responded. The
[before-reflow snapshot](validation/gpio-connectivity-0-44-2026-11-16-before-gpio6-reflow.csv)
retains that fault. After reflow, GPIO6 reads local 0 / remote 0 for LOW and
local 1 / remote 1 for HIGH. Both samples agree in each direction and polarity.
All 45 undriven pins follow both bias settings, and all patterns recover after
release. This confirms restored digital connectivity; joint resistance was
not measured.

GPIO39's onboard LED is a known passive load. Its driver uses the SDK's 8 mA
drive-strength setting, while other pins retain 2 mA. Both HIGH and LOW responses
on GPIO39 passed on these boards. If the LED sinks an undriven weak pull-up in a
future run, the decoder uses the HIGH pattern for GPIO39 continuity and records
the bias observation instead of inventing an open wire. Its driven LOW pad
level is still checked. The LEDs are not heartbeat outputs during the test.

### Earlier GPIO0–38 scan

**All 39 same-number paths passed in both directions after the GPIO2 repair.**
GPIO0–38 connect to their matching GPIOs. No missing paths, crossed paths,
multiple connections, unstable samples, or held levels were detected on the
repeat scan. The full per-pin snapshot is
[gpio-connectivity-2026-11-16.csv](validation/gpio-connectivity-2026-11-16.csv).

The initial scan passed 38 of 39 paths. For GPIO2, each chip pulled its own pad
LOW successfully, but every receiving GPIO0–38 remained HIGH. This repeated in
both samples and both directions. The user identified and repaired a bad solder
joint; the full scan was then repeated without reflashing. GPIO2 now pulls the
matching remote pad LOW in both directions. The
[before-repair snapshot](validation/gpio-connectivity-2026-11-16-before-repair.csv)
retains that detected fault. All pins followed both undriven pull-up and
pull-down baselines, and levels recovered after every drive was released.

The scan checked all four Cortex-M33 cores, then used **1 MHz SWD** memory
access without halting the running applications. Tool versions remain the
[recorded SDK 2.3.1/Docker/OpenOCD toolchain](bringup.md#verification-evidence-2026-11-15).
Both current builds passed `-Wall -Wextra -Werror`. Twelve decoder tests passed,
covering correct wiring, an open GPIO44, a GPIO0/GPIO44 swap, a bridge, a held-LOW
line, unstable samples, incomplete/old-range rejection and GPIO39 LED cases
(loaded bias, real open, cross-wire, and LOW-response verification).

Raw scan and machine-readable results:

- `build/debug/gpio-connectivity-gs4xhyam/scan.log`
- `build/debug/gpio-connectivity-gs4xhyam/report.json`
- `build/debug/gpio-connectivity-gs4xhyam/report.txt`

The two pre-reflow expanded scans are `build/debug/gpio-connectivity-lsft30bq/`
and `build/debug/gpio-connectivity-hdxerbqx/`. The earlier
39-pin repaired scan is `build/debug/gpio-connectivity-7pn_s9u5/`, and its initial
GPIO2 fault capture remains in `build/debug/gpio-connectivity-8y62n0jx/`.

Loaded ELF SHA-256:

- Board 1: `7a3ca84759c4b19eca8334487ddf2c0bbbf62768b8b9eff2f11c0b7872edc74b`
- Board 2: `198e5a8ab9399daa599e6afa7c11fcea2c08ca0423628f3d7199b9119ddf235c`

## Build and repeat

```sh
make gpio-connectivity-build
# Load each matching build/multidrop/{1,2}/gpio_connectivity.uf2 through USB.
# See bringup.md for usb-boot, ROM disk identity checks, and sequential copies.
make gpio-connectivity-check
python3 -m unittest discover -s tools/tests -p 'test_gpio_connectivity.py'
```

The boards now run the [USB dispatcher](dispatcher.md). Reload the matching
connectivity images before using this check. While those images remain loaded,
repairs require only `make gpio-connectivity-check`, without reflashing. Each run creates a new
`build/debug/gpio-connectivity-*` directory. A completed scan returns normally
even when wiring faults are found; `report.json`'s `passed` and per-pin `status`
fields contain the verdict. Transport/protocol errors abort without inferring
missing wires from incomplete data.

Interactive access uses one `make multidrop-server`, then separate terminals:

```sh
OPENOCD_EXTERNAL=1 make multidrop-debug INSTANCE=1 FIRMWARE=gpio_connectivity
OPENOCD_EXTERNAL=1 make multidrop-debug INSTANCE=2 FIRMWARE=gpio_connectivity
```

Inspect `board_id` and `connectivity`. Resume both CPUs and close other debugger
sessions before starting the automated scan; it needs sole ownership of the
probe. Earlier `multidrop-check` and `gpio-link-check` commands belong to different
applications and must not be used against these images.

## Method and limits

The firmware initializes GPIO0–44 (45 pins) as inputs with weak pull-downs.
GPIO45–47, QSPI, USB and SWD are excluded from the scan. GPIO40–44 are tested
only between these native 3.3 V boards; this does not validate a 5 V interface.
There is no PSRAM initialization or CS-pin discovery. The
[manufacturer schematic](https://files.waveshare.com/wiki/Core2350B0/Core2350B.pdf)
is the bench-board pin reference.

The debugger first sets weak pull-downs on both boards, then weak pull-ups, to
identify held levels. It then enables a **single LOW output** on one board and
reads all 45 inputs on both boards twice, leaving other pins as inputs with
pull-ups. It repeats with HIGH outputs and pull-downs, in both directions:
**180 driven patterns, each sampled twice at both ends**. Each pattern is
released and recovery checked before the next pin. Latches change only while
output enable is off, so a swapped wire never meets opposing test outputs.
This identifies the actual observed destination(s), including same-board pins
that follow through a bridge, without opposing push-pull patterns on crossed
wires. The source output-enable mask and receiver all-input mask are checked
for every pattern.

Control uses a versioned 48-byte debugger mailbox, with its address resolved
from each matching ELF. Fields at byte offsets 0..32 are `magic`, `version`,
`request_seq`, `completed_seq`, `requested_pin`, `pull_up`, `applied_pin`,
`error`, and `heartbeat`, all `uint32_t`. Offsets 36, 40 and 44 add `pin_count`,
`drive_high`, and `applied_high`. Write pin/pull/level settings before changing
the request sequence; wait for completion and verify applied pin/error. Pin
`0xffffffff` releases all tested outputs. Error 1 rejects an invalid command;
error 2 indicates drive-lease expiration. Mailbox magic is `0x47434e31`, version 2;
the host checks both version and pin count before sending commands.

An active drive expires after **1000 ms**, and normal completion/error cleanup
releases both boards. The scan verified zero test output enables on exit. This
software lease requires the CPU to run: halting a chip can leave its last output
enabled. All test pins are currently inputs with weak pull-downs; LEDs remain off.

This checks digital LOW/HIGH propagation and passive recovery, not resistance,
analog voltage margins, edge timing, or wiring to GPIO45–47. Simulated fault
cases validate reporting; no physical miswire/bridge
was introduced deliberately. The user-reported GPIO2 solder repair restored its
observed digital connection; joint resistance was not measured.
