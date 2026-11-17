# RP2350 MC68008 Emulator and Bus Analyzer

A compact diagnostic adapter for computers using the **48-pin MC68008**. An
RP2350B or RP2354B microcontroller will use PIO, DMA and native USB to observe
the processor bus, generate diagnostic bus cycles and eventually emulate the
CPU in software.

The project now has a [draft pin map, candidate BOM and single-A3 KiCad schematic](kicad/README.md),
using RP2354B with in-package flash and **8 MiB QSPI PSRAM**, plus an
[unrouted four-layer placement starter](docs/mechanical.md). It uses provisional
outward-bent DIP contact lands and an accessible end tab. Firmware bring-up
now includes a [Docker Pico SDK build and verified SWD debugger workflow](docs/bringup.md)
for the standalone Waveshare Core2350B: GPIO39 blink, USB logging, flash read-back,
breakpoints, stepping and halt/resume. Two Core2350B boards have also been
verified with concurrent, independent debugger sessions through one probe on
a shared multidrop SWD connection. A GPIO0 link through the user's 470 ohm
resistor was verified with opposite LED states. The current
[GPIO0–44 connectivity test](docs/gpio-connectivity.md) scans both directions
with LOW and HIGH patterns through SWD. **All 45 paths pass in both directions**
after the user reflowed GPIO6's solder joints on 2026-11-16. The earlier expanded
scans detected that missing path; the earlier GPIO0–38 test found GPIO2's solder
fault before repair. No missing paths, cross-wiring or bridges are detected in
the latest scan. A [PIO bench analyzer and pattern generator](docs/pio-trace.md)
now capture GPIO0–31 and GPIO32–44 in separate 1024-sample runs at a nominal
150 MS/s. Both banks matched the one-bit-per-clock pattern with no receiver
FIFO stalls. The receiver stores `LOW32.VCD` and `HIGH13.VCD` in flash and
exports a read-only USB drive after acquisition; both files survived an SWD reset.
The current [core 0 dispatcher](docs/dispatcher.md) loads generator/analyzer
modules from flash or PSRAM into core 1 execution SRAM. A framed USB CDC
protocol and Python CLI start both applications without SWD. The analyzer
supports HIGH/LOW level triggers on any GPIO0–44 for either bank in its original
finite burst mode.
The dispatcher now exposes only USB CDC; the `ICECAP` mass-storage interface
has been removed. Captures remain in flash and download through CDC.
Dispatcher 0.3 adds an [8 MHz-timed 68008 bench bus generator, a 1 KiB memory
responder and state analyzer](docs/bus-fixture.md). Continuous timing and state
captures support 1..65536 records, address or GPIO triggers, early/middle/late
positions, partial stops and host VCD export. Continuous timing currently accepts
1 kHz..1 MHz; the original finite 150 MS/s path remains available. These are
3.3 V fixture applications with GPIO31 as DTACK, separate from the proposed
motherboard adapter. Dispatcher 0.4 adds a [combined memory/150 MS/s timing
mode](docs/single-cycle-timing.md) for a 4096-sample single-cycle trace with
an exact sampled-edge midpoint trigger. The 100 ms no-trigger capture/timeout
path and single read/write captures are bench verified on both boards, with
zero sampling stalls. The responder currently adds one or two wait states;
the nominal 500 ns no-wait cycle remains a sequencing target. Adapter bus
firmware remains unimplemented. Dispatcher 0.5 adds a
[CPU reset/STOP application](docs/cpu-emulator.md) using the shared PIO byte
bus engine and a boot image in the other board's memory/state analyzer. Both
boards passed reset-vector fetches and `STOP #$2700` (12 captured byte reads),
NOP/STOP (14 reads), and a separate reset-vector BERR-to-HALT test. This is a
reset/NOP/STOP milestone. Dispatcher 0.6 now runs the first five instructions
of the [supplied ABC1600 ROM](docs/abc1600.md), uploaded through the memory
tool into a separate 1 MiB target map. Both cause-register branch paths match
the captured bus bytes and per-instruction register snapshots. CLR,
MOVE/MOVEA, BTST, BRA/BSR/Bcc and JMP passed 37586 independent Musashi
comparisons in host RAM, including the legal MOVE addressing-mode cross-product.
Dispatcher 0.7 now separates generic uploaded-code memory from an ABC1600
memory application with boot-ROM mirrors, task/segment/page registers, MMU
translation and protection. The ROM executes **105 instructions** (the first
five plus the next 100), including 54 MAC writes; all 354 bus transfers, 106
CPU snapshots and MAC tables match the host/MAME reference. The expanded
CPU core passes 81238 independent instruction cases, and the MAC model passes
17133 comparisons against methods extracted from the local MAME checkout.
Complete ABC1600 peripherals, exception processing, interrupts, remaining
opcodes and CPU-speed validation remain future work. The
[RP2350 engineering specification](requirements/RP2350_68008_ICE_Specification_and_Codex_Prompt.md)
is the design baseline and contains the detailed requirements, acceptance
criteria and primary references.

## Operating modes

| Mode | Physical CPU | Intended behavior |
| --- | --- | --- |
| Passive analyzer | Installed in the upper socket | CPU pins connect directly to the motherboard; the MCU observes with all bus outputs disabled. Capture bounded traces with triggers, timestamps and overflow reporting. |
| CPU replacement | Removed | The MCU drives the motherboard bus. Begin with byte reads/writes and memory diagnostics, then add a software MC68008 interpreter and execution controls. |

Passive mode is the default. A hardware interlock must prevent accidental MCU
bus driving with a real processor installed. Full CPU emulation and original
CPU-speed performance remain development goals requiring validation.

## Hardware concept

- Aligned female contacts on top and male contacts underneath: 48-pin DIP,
  2.54 mm contact pitch and 15.24 mm row spacing, with verified pin-for-pin
  correspondence in the schematic. The PCB has co-registered outward-facing
  SMT lands for manually formed tails; physical connector fit is provisional.
- A central 10 × 10 mm QFN-80 RP2350B/RP2354B, targeting a board close to the DIP
  body footprint. Connector geometry, component clearance and insertion forces
  must be checked before committing to the arrangement.
- Four-layer PCB: top signals, GND plane, 3.3 V plane and bottom signals.
  The placement starter is 70.96 mm long, with a 21 mm-wide CPU section and a
  27 mm-wide tab for USB/SWD/buttons/mode bridge. The electronic-component
  BOM target is under US$10, excluding PCB, connectors, assembly and freight;
  this is an unverified target.
- Native USB-C for host communication, BOOTSEL recovery and dedicated SWD for
  MCU debugging. RP2354B is the draft choice to save external-flash space;
  RP2350B with external QSPI flash remains an alternative.
- Raspberry Pi Debug Probe for SWD uploads and debugging, through J4's keyed
  3-pin JST-SH connector (C160403), using the probe's supplied cable. The ICE
  takes no power through this connector. See the [programming guide](docs/programming.md).
- U5 **APS6404L-3SQR-ZR / C3040877** adds 8 MiB PSRAM on the shared QSPI
  clock/data lines, with GPIO47 as its separate chip select. USB presence moves
  to GPIO46; the unused BUS_ARM_REQUEST reservation is removed.
- Target-derived 5 V supplies a 3.3 V regulator and the MCU's core-regulator
  circuit. The USB-C starter uses VBUS only for MOSFET-isolated presence sensing.
  Protection of direct bus GPIOs during supply transitions remains unresolved.
- The [per-pin allocation](kicad/mc68008_pinmap.csv) uses 40 five-volt-tolerant
  GPIOs and five 2.2 kΩ/BAT54-protected inputs, keeping address/data/strobes/clock in one PIO
  window. Cross-PIO timing and electrical acceptance still require validation.

RESET/HALT behavior, bus arbitration, TTL compatibility and supply sequencing
are explicit design checks. Connector footprints and the proposed input clamps
are provisional until verified against original documentation and bench tests.

## Development order

1. **Mechanical feasibility:** create a placement-first KiCad project with
   aligned top/bottom contacts, board outline, central MCU and provisional
   support components. Produce placement plots, a dimensions report and
   connector/clearance findings before detailed routing.
2. **Circuit design and bring-up:** complete the schematic, reviewed pin map,
   power/protection and hardware mode interlock. Bring up safe GPIO defaults,
   USB, recovery and target-clock observation.
3. **Passive analyzer:** implement synchronized PIO/DMA capture, bounded buffers,
   triggers and USB trace export to text/CSV. Verify that pass-through operation
   leaves a known-good target unaffected.
4. **Active diagnostics:** with the real CPU removed, validate byte transactions,
   timeouts, bus errors and ordered word/long accesses using a bench fixture.
   Add memory examination and explicitly enabled RAM writes/tests.
5. **CPU emulation:** evaluate MCL68+ licensing and portability, isolate the
   interpreter from the hardware bus engine, and test 68008 addressing,
   exceptions and interrupts. Benchmark before making speed claims.

The first firmware target uses Pico C/C++ SDK 2.3.1. Run `make setup`,
`make program`, and `make debug-check` for standalone Core2350B bring-up;
`make debug` opens interactive GDB inside Docker. On macOS, native OpenOCD
bridges the USB probe to container GDB. The dispatcher provides loadable bench
bus/analyzer modules and a versioned USB command protocol. The motherboard
adapter and full instruction interpreter remain planned; the bench interpreter
executes 105 ABC1600 ROM instructions with bus/register/MAC validation.

For the configured two-board bench setup, `make multidrop-probe` enumerates both
chips and `make multidrop-check` tests two concurrent GDB sessions, independent
halt/resume, breakpoints, stepping and variable writes. The
[multidrop instructions](docs/bringup.md#two-boards-on-one-swd-probe-2026-11-15)
describe firmware IDs, USB recovery and interactive debugging.
The current boards run the [USB dispatcher](docs/dispatcher.md).
`make dispatcher-build` builds both images and separate loadable modules.
`python3 tools/ice.py fixture --generator /dev/cu.usbmodem24401 --receiver /dev/cu.usbmodem24301`
starts both applications and downloads verified VCD/raw captures. The Python
CLI also exposes load, upload, capture, generate, status, stop and fetch commands;
use `FIRMWARE=dispatcher` for interactive debugging.
The earlier [PIO trace fixture](docs/pio-trace.md) and its
`make pio-trace-capture` SWD workflow require their matching images to be reloaded.
The earlier [GPIO connectivity fixture](docs/gpio-connectivity.md) remains available:
`make gpio-connectivity-build` builds both images; `make gpio-connectivity-check`
reports opens, wrong pins and other observed faults. Use
`FIRMWARE=gpio_connectivity` for interactive debugging of these images. All
test pins are inputs between checks; the earlier GPIO0/LED demo remains a
separate `gpio_link` target.

The [JLCPCB upload BOM](kicad/BOM_JLCPCB.csv) uses dated C-number selections,
preferring Basic SMT parts and sharing values. The DIP contacts are fitted manually.
The prototype assumes shared target-only power and a TTL-compatible bus; its
BAT54 forward-voltage margin is accepted, with [nominal SPICE evidence](simulations/bat54/README.md).
Local supply transitions and input timing still need validation.

The next hardware milestone is **physical connector fit and placement review**,
then routing, alongside resolving independent output inhibition. The mode
jumper currently provides firmware permission only. No PCB is ready for fabrication.

## Repository

- [requirements/RP2350_68008_ICE_Specification_and_Codex_Prompt.md](requirements/RP2350_68008_ICE_Specification_and_Codex_Prompt.md): current engineering specification and staged implementation prompt.
- [docs/hardware.md](docs/hardware.md): pin-map rationale, PIO constraints, BOM decisions and open items.
- [docs/mechanical.md](docs/mechanical.md): provisional contact footprints, board dimensions, layer stack, placement plots and remaining fit/DRC checks.
- [docs/programming.md](docs/programming.md): SWD wiring, automated firmware uploads and debugging workflow.
- [docs/bringup.md](docs/bringup.md): Docker setup, Core2350B blink/debug commands and measured bring-up results.
- [docs/gpio-connectivity.md](docs/gpio-connectivity.md): GPIO0–44 wiring scan, debugger protocol and measured pin report.
- [docs/pio-trace.md](docs/pio-trace.md): two-bank PIO generator/analyzer, flash-backed USB VCD retrieval and measured results.
- [docs/dispatcher.md](docs/dispatcher.md): core 0 USB dispatcher, core 1 application loading, Python command interface and hardware acceptance results.
- [docs/protocol-v1.md](docs/protocol-v1.md): versioned CDC framing, CRC/replay rules, command table and status records.
- [firmware/](firmware/): standalone Core2350B fixtures, dispatcher, loadable applications and board configuration.
- [docker/Dockerfile](docker/Dockerfile): Pico SDK, Arm compiler, GDB, picotool and RP2350 OpenOCD.
- [kicad/README.md](kicad/README.md): editable schematic, PDF, pin tables, BOM and validation commands.
- [tools/](tools/): reproducible schematic generation and netlist/BOM checks.
- [AGENTS.md](AGENTS.md): project-specific instructions for contributors and coding agents.
- [LICENSE](LICENSE): Apache License 2.0.

## Version control

Keep the requirements, documentation, tools, circuit definitions, native KiCad
schematic/project/PCB, custom design rules, project libraries, library tables, pin
maps and component catalog in Git. The saved schematic includes manual layout
edits and must be preserved even though a generator also exists.

Keep the BOMs, selected schematic/placement PDFs, placement SVG and validation summary as review
deliverables. Keep the BAT54 model, simulation inputs and the documented result
snapshot under `simulations/bat54/`, including its provenance and log. These
selected outputs support review without requiring every reader to run the tools.

Everything under `build/`, including `build/hardware/`, is disposable working
output: netlists, ERC reports, preview images, backup snapshots and temporary
scripts. It is ignored. Reusable tools belong in `tools/`; results worth retaining
belong in a documented evidence directory or the validation summary. KiCad's
personal `.kicad_prl` file, locks, automatic backups and footprint-info cache are
also ignored, together with Python caches/local environments and OS metadata.

`kicad/parts_catalog.json` is a curated, dated selection record rather than a live
inventory cache. Version it alongside the matching schematic and BOM. Recheck
stock, prices and Basic/Extended status before ordering. Refresh the recorded
fields deliberately when they change, keeping part identity, footprint, source,
verification date and selection reasons consistent across purchasing outputs
and schematic fields. A checkout or build should not automatically replace
these reviewed selections with whatever the supplier currently lists.

The ABC1600 memory-controller port retains MAME's per-file BSD-3-Clause/Curt
Coder attribution; see [its license](LICENSES/BSD-3-Clause-MAME.txt).
