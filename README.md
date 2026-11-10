# RP2350 MC68008 Emulator and Bus Analyzer

A compact diagnostic adapter for computers using the **48-pin MC68008**. An
RP2350B or RP2354B microcontroller will use PIO, DMA and native USB to observe
the processor bus, generate diagnostic bus cycles and eventually emulate the
CPU in software.

The project now has a [draft pin map, candidate BOM and single-A3 KiCad schematic](kicad/README.md),
using RP2354B with in-package flash and **8 MiB QSPI PSRAM**. A PCB placement study, firmware and host
tools have not yet been implemented. The
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
  correspondence through the board.
- A central 10 × 10 mm QFN-80 RP2350B/RP2354B, targeting a board close to the DIP
  body footprint. Connector geometry, component clearance and insertion forces
  must be checked before committing to the arrangement.
- Four-layer PCB preferred; six layers if justified. The electronic-component
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

Firmware is planned around the Pico C/C++ SDK, separate bus/analyzer/interpreter
modules and a documented, versioned USB protocol. Host tooling and reproducible
builds should work across common operating systems.

The [JLCPCB upload BOM](kicad/BOM_JLCPCB.csv) uses dated C-number selections,
preferring Basic SMT parts and sharing values. The DIP contacts are fitted manually.
The prototype assumes shared target-only power and a TTL-compatible bus; its
BAT54 forward-voltage margin is accepted, with [nominal SPICE evidence](simulations/bat54/README.md).
Local supply transitions and input timing still need validation.

The next hardware milestone is **mechanical placement and feasibility**, alongside
resolving independent output inhibition. The mode
jumper currently provides firmware permission only. No PCB is ready for fabrication.

## Repository

- [requirements/RP2350_68008_ICE_Specification_and_Codex_Prompt.md](requirements/RP2350_68008_ICE_Specification_and_Codex_Prompt.md): current engineering specification and staged implementation prompt.
- [docs/hardware.md](docs/hardware.md): pin-map rationale, PIO constraints, BOM decisions and open items.
- [docs/programming.md](docs/programming.md): SWD wiring, automated firmware uploads and debugging workflow.
- [kicad/README.md](kicad/README.md): editable schematic, PDF, pin tables, BOM and validation commands.
- [tools/](tools/): reproducible schematic generation and netlist/BOM checks.
- [AGENTS.md](AGENTS.md): project-specific instructions for contributors and coding agents.
- [LICENSE](LICENSE): Apache License 2.0.

## Version control

Keep the requirements, documentation, tools, circuit definitions, native KiCad
schematic/project (and PCB when added), project libraries, library tables, pin
maps and component catalog in Git. The saved schematic includes manual layout
edits and must be preserved even though a generator also exists.

Keep the BOMs, selected schematic PDF and validation summary as review
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
