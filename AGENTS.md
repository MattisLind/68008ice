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
- Review GPIO allocation for signal direction, voltage tolerance and PIO
  grouping/timing. Keep any pin table, schematic and firmware assignments in sync.
- Default to passive mode with bus-driving GPIOs high impedance after reset.
  Require a hardware mode interlock for active operation. Preserve RESET/HALT
  electrical behavior and BR/BG bus ownership.
- Verify target/USB power sequencing, unpowered pin exposure, input protection
  and back-powering. The proposed resistor/Schottky clamps require validation.
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
