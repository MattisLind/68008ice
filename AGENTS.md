# Project instructions

## Design baseline and scope

- Read `requirements/RP2350_68008_ICE_Specification_and_Codex_Prompt.md` before
  hardware or firmware work. It defines the current RP2350B/RP2354B design.
- Build for the 48-pin MC68008: direct CPU-to-motherboard pass-through in passive
  mode, or CPU replacement with the real processor removed. The previous FPGA,
  NEORV32 and FT2232H architecture is superseded.
- Keep README.md aligned with actual repository progress. Distinguish proposed
  circuits, footprints and performance targets from verified results.

## Hardware workflow

- Start with a real KiCad placement project and report mechanical feasibility
  before detailed routing. Verify aligned top/bottom DIP contacts, pin-1
  orientation and bottom-side mirroring. Document dimensions, clearances,
  connector choices and provisional footprints.
- Use original Motorola and Raspberry Pi documentation for pin maps, electrical
  limits and reference circuits. Record sources and any corrections to the
  specification; never invent component dimensions or approved footprints.
- Prefer four PCB layers; justify six if needed. Treat the footprint and BOM
  budget as targets pending validation.
- Keep the entire schematic on one landscape A3 sheet; do not introduce child
  sheets. Use `tools/hardware_circuit.json` for circuit definitions and the
  generator's placement table for readable layout.
- Use local signal labels and real power symbols. Preserve saved GUI placement,
  wiring and field-layout edits during circuit changes; use `--bom-only` when
  refreshing purchasing outputs without replacing the edited schematic.
- Use five single BAT54 / C8590 clamps, one per protected input, with anodes at
  the MCU nodes after R14–R18 and cathodes at 3.3 V; leave SOT-23 pad 2 NC.
- Review GPIO allocation for signal direction, voltage tolerance and PIO
  grouping/timing. Keep any pin table, schematic and firmware assignments in sync.
- The current starter chooses RP2354B with in-package flash. Read
  `docs/hardware.md` for mapping decisions and unresolved safety circuits.
  `kicad/mc68008_pinmap.csv` drives `tools/build_hardware.py`; review GUI edits
  before regeneration and run `tools/check_hardware.py` on the exported netlist.
- Default to passive mode with bus-driving GPIOs high impedance after reset.
  Require a hardware mode interlock for active operation. Preserve RESET/HALT
  electrical behavior and BR/BG bus ownership.
- Verify target/USB power sequencing, unpowered pin exposure, input protection
  and back-powering. The current prototype uses shared target-only 5 V power,
  a TTL-compatible target, five 2.2 kΩ/BAT54 clamps and two parallel 1 kΩ rail
  loads. Treat common power as a design assumption to check on the bench;
  local 3.3 V ramp remains a bench check. The user explicitly accepts the BAT54
  forward-voltage margin risk at sub-mA currents. Preserve that decision and
  the nominal SPICE evidence in `simulations/bat54`; do not treat the accepted
  margin as requiring renewed approval or silently replace the clamps.
- Source purchased components as JLCPCB SMT parts, preferring Basic over
  Extended when electrically and mechanically suitable. Reuse an existing
  compatible value/MPN before adding an Extended type; retain values required
  for USB, clocks, filtering or other documented margins. J1/J2 DIP contacts
  are manually assembled and exempt. PCB-only pads/bridges need no C-number.
- Keep LCSC C-numbers, Basic/Extended class, source/date and selection reasons
  in `kicad/parts_catalog.json`, schematic fields and the BOM. Generate the
  JLCPCB upload BOM with manual/PCB-only positions excluded; verify catalog
  status and stock again at ordering time.
- Use one shared fast bypass capacitor for the co-registered J1/J2 supply contacts; retain regulator and MCU local decoupling.
- Keep RESET/HALT input sensing active with a fixed LOW output latch; assert/release through output enable, using the target pull-ups. Keep target RESET distinct from MCU RUN.
- Keep BOOTSEL and SWD recovery accessible. Do not proceed to fabrication with
  unresolved connector, clearance, electrical or power-safety issues.

## Software and validation

- Progress through bring-up, passive capture, active diagnostics and then CPU
  emulation. Keep implemented milestones buildable with portable tooling.
- Separate the PIO/bus hardware layer, analyzer and CPU interpreter. Review
  third-party licenses before incorporating code such as MCL68+.
- Use bounded buffers, report capture overflow and explicitly synchronize PIO
  sampling. Validate USB frames before execution; document framing, limits,
  integrity checking and recovery in a versioned protocol.
- Provide bus timeouts and safe abort/release behavior. Require explicit opt-in
  for diagnostic writes and account for memory-mapped I/O side effects.
- Validate active bus operations on a bench fixture before a valuable target.
  Test instruction compatibility separately from external bus timing; benchmark
  CPU emulation before promising replacement performance.
- For each implemented milestone, record generated file paths, tool versions,
  reproducible checks and results, placement plots where applicable, and
  unresolved risks. Run ERC/DRC and build/tests appropriate to the work.
