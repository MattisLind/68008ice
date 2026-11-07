# Hardware design rules

- Prefer legal signal pins on the perimeter of BGA packages. Use the outermost
  rows and columns first, then successive inner rings as needed. Treat bank
  voltage, clock access, boot behavior, and fixed-function pins as constraints;
  configuration and JTAG signals stay on their required pins.
- Keep related interfaces physically grouped when choosing between equally
  accessible pins. Review actual placement and escape routing before freezing
  assignments.
- Keep FPGA schematic nets, `kicad/fpga_pins.csv`, and `kicad/68008ice.lpf` in sync.
- Use power symbols for supply and ground connections. Keep USB power, target
  power, and filtered or regulated rails distinct unless an explicit circuit
  connects them.
- Preserve the independent CPU and target bus interfaces and default-disabled
  output drivers. Processor debug/reset must not reset bus-safety logic.
- Power all functional circuitry, including FT2232H, from the target motherboard.
  USB-C VBUS is used only for presence detection through MOSFET gates; never
  connect it to a board supply. USB ground remains shared.
- Driver enable must require independent power-good, FPGA DONE/INITN, and an
  explicit arm request. Keep receiver outputs disabled until FPGA rails are valid
  so side-bank pins are not driven with the core unpowered.
