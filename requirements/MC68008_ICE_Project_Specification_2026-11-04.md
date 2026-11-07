# MC68008 In-Circuit Emulator and Bus Analyzer

Updated **2026-11-07** with power, USB-C and startup-safety decisions.

## 1. Overall goal

Build an open-source FPGA-based tool for diagnosing and repairing computers using the **48-pin MC68008**. It should work as a transparent bus analyzer with a real CPU installed, or replace the CPU with an emulated core. Instruction-cycle accuracy is secondary to correct instruction execution and externally valid bus transactions.

## 2. Architecture

A custom board fits between the motherboard's 48-pin CPU socket and an optional real MC68008 in a socket on the board. The FPGA has **separate, level-translated interfaces** for the physical CPU and motherboard. In pass-through mode it forwards signals combinationally, without clocking the forwarding path through sampling registers.

Initial operating modes:

- **Transparent analyzer:** Real MC68008 runs the machine; FPGA forwards and records bus activity with programmable triggers.
- **Active real-CPU debugger:** Real MC68008 remains the execution engine. The FPGA can intercept/inject bus responses, instructions, interrupts and exceptions; redirect debugger-generated accesses to virtual memory; capture registers via an injected handler and resume using `RTE` where architecturally safe.
- **ICE:** FX68K drives the motherboard; supports halt, step, inspection and controlled bus accesses.

Tandem comparison of the real and emulated CPUs is **future scope**, not part of the initial implementation.

An FPGA-controlled output-enable scheme ensures that only the active bus master drives the motherboard, including during DMA bus arbitration. Bidirectional data, RESET and HALT require special handling.

## 3. Hardware

### 3.1 FPGA and PCB

- **Baseline FPGA:** Lattice **ECP5-25F**, preferably **CABGA-256** for availability and ample I/O. **Upgrade to ECP5-45F only if the complete design does not fit** (logic or embedded RAM).
- Custom **four-layer KiCad PCB**, manufactured and assembled by **JLCPCB** if routing and assembly rules permit.
- ECP5-25F provides **1,008 Kbit (126 KiB) embedded block RAM** for the CPU, debugger and trace capture.
- Two independent 5 V CPU-bus interfaces, with the optional physical CPU mounted above the adapter and a 48-pin DIP plug below.
- Prefer legal BGA pins on the perimeter, then successive inner rings; bank voltages, clock access and fixed configuration/JTAG functions take precedence.

### 3.2 Level translators and bus ownership

- **5 V to 3.3 V inputs:** 5 V-tolerant, 3.3 V-powered **74LVC541A** buffers.
- **3.3 V to 5 V outputs:** 5 V-powered, TTL-input-compatible **74AHCT541** tristate buffers.
- Initial schematic allocation: **12 octal receivers + 9 octal drivers**; refine by signal coverage and independent output-enable grouping.
- Use separate FPGA input/output/OE signals rather than internal tristate nets. Data bus direction changes between reads and writes.
- **RESET and HALT:** separate sensing and open-drain-style low drivers on both sides. Independently intercept or override **DTACK, BERR, VPA and the interrupt-level inputs** on the physical CPU side; distinguish real CPU signals from motherboard signals.
- Respect **BR/BG DMA arbitration**, turning off motherboard-side address, data and relevant control drivers whenever the CPU relinquishes the bus.
- A **hardware interlock**, independent of firmware, permits drive only when target +5 V and all FPGA rails are valid, **DONE and INITN are high**, and the FPGA explicitly asserts its arm request. Default-disabled operation includes AHCT outputs and RESET/HALT low drivers during startup, failed configuration and reconfiguration. Receiver outputs remain disabled until FPGA supplies are valid, avoiding drive into a partially powered FPGA.
- Provide a dedicated target-clock input for timing-sensitive bus interception.

### 3.3 Programming, configuration and USB

- **FT2232H** on one USB connection: **Channel A = MPSSE/JTAG** programming; **Channel B = 8-bit asynchronous FT245 parallel FIFO** for binary debugger commands and bulk trace transfer (not UART).
- Use a **USB-C receptacle carrying USB 2.0**, with separate 5.1 kΩ CC1/CC2 pull-downs and both connector orientations supported.
- **All board circuitry, including the FT2232H, is powered exclusively from the target motherboard.** USB VBUS must not feed a supply rail. Sense VBUS through a **two-MOSFET presence detector** with no conductive VBUS-to-board-supply path; use its target-powered output for FTDI `PWRSAV#`. Configure the EEPROM for self-powered operation and suspend on USB absence. USB ground remains shared. This avoids the back-powering risk and interface-isolation circuitry associated with a separately USB-powered FTDI.
- Channel B uses **D0–D7, RXF#, TXE#, RD# and WR#** with FPGA-controlled handshaking (reserve **SIWU#** if practical). Include an FTDI configuration EEPROM.
- External **SPI NOR flash** stores the FPGA configuration and a directory of NEORV32 application images; JTAG FPGA loading remains available for development. Include FPGA-accessible SPI flash read/write circuitry and a recovery route.
- Expose a JTAG header for recovery and board bring-up.
- Include FPGA supplies, clocking, decoupling and safe power sequencing.

### 3.4 Bus trace capture

- Sample both bus interfaces at approximately **50 MHz**, independently of the combinational forwarding path.
- Use on-chip EBR as a **circular trace buffer** with configurable pre/post-trigger capture.
- Trigger on masked address, data, R/W, function code, bus error or DTACK timeout; optionally halt or enter the real-CPU debugger following a trigger.
- Support raw pin samples and a more compact **transaction/event trace**; no absolute timestamp is needed for uniformly sampled raw data.

### 3.5 Power supply

- Required FPGA rails: **1.1 V VCC**, **2.5 V VCCAUX**, and **3.3 V VCCIO** for the selected interfaces.
- Proposed supplies from target +5 V: **TPS62130A, 1.1 V / 3 A** core buck; **TPS62160, 3.3 V / 1 A** buck; **TLV75525, 2.5 V / 500 mA** LDO from 3.3 V. The 3.3 V budget includes the auxiliary LDO input current. Ratings are design capacity, not measured FPGA consumption.
- Establish 3.3 V for configuration-bank I/O and flash before enabling core/auxiliary supplies. Include independent voltage supervision, controlled ramps, bulk capacitance and local FPGA decoupling.
- Determine actual consumption using the implemented design and switching activity. Verify target-PSU, CPU-socket-contact and PCB current capacity, regulator thermals, sequencing and bus isolation under startup, brownout and USB-connected/target-off conditions before hardware release.

## 4. Software and FPGA logic

### 4.1 CPU implementation

- Start from **FX68K**, preserving its existing microcode and nanocode.
- Insert a **16-to-8-bit external bus adapter**: one logical 16-bit access becomes two MC68008 byte transactions, with DTACK to FX68K withheld until the operation completes.
- Validate prefetch, bus errors, interrupts, VPA, read-modify-write operations and DMA handoff. Exact internal instruction timing is not an initial requirement.

### 4.2 Debug control processor

- **Selected: NEORV32** RISC-V softcore, with memory-mapped control registers for the FX68K core, bus interface and trace engine.
- **Permanent bootloader** in FPGA-initialized block RAM; **one task-specific application at a time** runs from writable instruction RAM. Applications are normally loaded from SPI flash; direct FT245 loading remains available for development. Initial allocations: **8 KiB boot ROM, 16 KiB application IMEM, 4 KiB DMEM**, subject to compiled sizes.
- SPI flash holds the FPGA bitstream, a simple fixed application directory mapping **application ID → flash offset, image length and CRC32**, and the application images. No filesystem is required. The bootloader validates the selected image before execution.
- A **hardware FT245 command** writes the requested application ID into a mailbox register outside the NEORV32 reset domain, then triggers a **NEORV32-only reset**. On restart, the bootloader reads the ID, looks up the flash directory, loads the image into IMEM and starts it. Reserve an ID for direct FT245 application upload during development.
- Support full SPI flash image updates through FPGA-controlled logic, with safeguards for the FPGA configuration region and a JTAG recovery path if an update is interrupted.
- Keep the mailbox, FT245 protocol, bus ownership, buffer safety, trace contents and operating mode in FPGA hardware across NEORV32-only resets. Optional NEORV32 OCD/JTAG debugging is a development feature, not required for application switching.
- Synthesize **FX68K + NEORV32 + FT245 protocol engine + bus/trace logic** for ECP5-25F; move to ECP5-45F if needed.

### 4.3 Bus interception and real-CPU debugging

- Add hardware selection between **forward**, **suppress** and **inject** for target bus transactions; implement a small FPGA-backed virtual instruction/stack-memory window.
- For non-destructive register capture, request a suitable exception, intercept its stack frame/vector fetch, inject a handler to save registers, and restore state with `RTE`. Account for USP/SSP and prefetch. Test recovery carefully before using it on faulty hardware.
- Support hardware HALT, interrupt/trace exceptions and `BERR` injection; note that an ordinary 68000/68008 bus-error exception **cannot generally resume an interrupted instruction**. `BERR` + `HALT` retry is a separate bus-cycle mechanism with restrictions.

### 4.4 FT245 protocol and command routing

- FT2232H Channel B provides an **unframed 8-bit byte stream**. Implement **framing, byte stuffing and command dispatch in FPGA RTL**, independently of NEORV32.
- Use `0xFF` as escape: `FF 00` = start frame, `FF 01` = end frame, `FF 02` = abort/resynchronize, `FF FF` = literal data byte `FF`. Escape frame contents, including integrity fields, in both directions.
- Each frame contains **message type, command ID, sequence number, payload length and CRC32**. Validate length, command and CRC **before executing any action**. Discard invalid/incomplete frames and resynchronize at the next start delimiter. Use **bounded payload frames** (initially up to 256 bytes) and chunk larger uploads.
- FPGA RTL handles the **FT245 handshake, RX/TX FIFOs, frame encoder/decoder, CRC and command dispatcher**. Simple commands (version, trigger and trace control, application-ID selection and NEORV32-only reset) are handled directly in hardware. Other validated commands reach NEORV32 through a **memory-mapped mailbox with interrupt**.
- Support **direct FPGA trace-buffer streaming** into the framed FT245 transmitter, bypassing NEORV32 data copies. Serialize outbound frames so responses, trace data and asynchronous events cannot interleave.
- Expose **independent NEORV32 application reset/reload and protocol-recovery controls**, preserving safe target-bus outputs; retain JTAG as an independent recovery path.

### 4.5 Firmware and host tools

- NEORV32 bootloader selects and validates application images from SPI flash using the persistent mailbox application ID; direct FT245 loading is supported for development. Applications implement higher-level debugging, real-CPU register extraction, virtual memory and diagnostics.
- Host application uses **libftdi/libusb** and the same framing protocol for commands, responses and events; provide trace decoding, disassembly, stepping and diagnostic bus access.

### 4.6 Development toolchain and verification

- **Yosys + nextpnr-ecp5 + Project Trellis**, **openFPGALoader**, **Verilator**, and Makefiles; develop on macOS/Linux.
- First validate the FX68K bus adapter in simulation, then test transparent forwarding and capture on hardware, followed by real-CPU interception and ICE operation.

## 5. Others

- Starting reference: [hoglet67/AtomBusMon](https://github.com/hoglet67/AtomBusMon).
- CPU core: [ijor/fx68k](https://github.com/ijor/fx68k).
- **First feasibility milestone:** synthesize FX68K + NEORV32 + FT245 protocol engine + proposed bus and trace infrastructure for ECP5-25F, then verify one 16-bit logical read as two correctly timed 8-bit physical transfers.
- **Future ideas (not initial scope):** tandem comparison of physical and emulated MC68008 execution, and a standalone reference fixture for testing a real processor.
- **Key risks:** BGA breakout and power layout; forwarding delay and data/DTACK relationship; reliable virtual bus interception and exception restoration; bus ownership/driver contention; FX68K behavior under extended memory waits.
