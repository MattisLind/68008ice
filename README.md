# RP2350 MC68008 Emulator and Bus Analyzer

A compact diagnostic adapter for computers using the **48-pin MC68008**. An
RP2350B or RP2354B microcontroller will use PIO, DMA and native USB to observe
the processor bus, generate diagnostic bus cycles and eventually emulate the
CPU in software.

The project is restarting at the requirements stage. Hardware, firmware and
host tools for this approach have not yet been implemented. The
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
  MCU debugging. RP2350B requires external QSPI flash; RP2354B is the proposed
  integrated-flash alternative.
- Target-derived 5 V supplies a 3.3 V regulator and the MCU's core-regulator
  circuit. USB power behavior and protection against back-powering must be
  resolved for the new design.
- A provisional GPIO allocation uses 40 five-volt-tolerant GPIOs and five
  externally protected inputs. The physical pin map, PIO grouping, electrical
  limits and reset/power-off behavior still require review.

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

The first implementation milestone is **mechanical placement and feasibility**.
No PCB is ready for fabrication.

## Repository

- [requirements/RP2350_68008_ICE_Specification_and_Codex_Prompt.md](requirements/RP2350_68008_ICE_Specification_and_Codex_Prompt.md): current engineering specification and staged implementation prompt.
- [AGENTS.md](AGENTS.md): project-specific instructions for contributors and coding agents.
- [LICENSE](LICENSE): Apache License 2.0.
