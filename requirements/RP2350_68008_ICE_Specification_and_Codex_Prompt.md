# RP2350-based MC68008 Emulator and Bus Analyzer

**Engineering specification and Codex implementation prompt**  
**Revision:** 2026-11-10 · **Status:** Proposed design; electrical, mechanical and timing details require validation

## 1. Goal and scope

Design a small, low-cost, 48-pin DIP-footprint diagnostic board for computers built around the **48-pin MC68008**. The board uses a **Raspberry Pi RP2350B or RP2354B** microcontroller, its PIO state machines and DMA, and native USB. It should provide two principal operating modes:

1. **Passive analyzer:** A real MC68008 is installed in a socket above the board. The CPU's pins connect directly to the corresponding motherboard pins; the RP2350 observes the bus with all bus-facing GPIO outputs disabled.
2. **CPU replacement:** Remove the real MC68008. The RP2350 drives the motherboard's 68008 socket and progressively supports manual bus transactions, diagnostic operations, and then software emulation of a complete MC68008.

Prioritize an affordable, manufacturable **four-layer PCB**, with six layers allowed if needed. Aim to keep the PCB within or close to the DIP-48 body footprint, permitting a small extension for USB if necessary. A bill of materials under **US$10 for the electronic components** is a design target, **not** a verified assembly quotation; connectors, PCB, assembly, freight and rework may dominate the cost.

**Out of scope for the first revision:** 68000/68010 support, high-fidelity transparent bus interception or instruction injection into a real CPU, and a separate FPGA/NEORV32/FT2232H architecture. These are not required for the compact RP2350 design.

## 2. Mechanical concept and initial KiCad layout

### 2.1 Aligned top and bottom DIP connections

- Use a **48-pin, 0.6-inch / 15.24 mm row-spacing DIP pattern**, with **2 × 24 positions at 2.54 mm pitch**.
- **Top:** female socket/contacts for an optional genuine MC68008, for passive analyzer mode. Prefer an **open-frame socket** or **two 1 × 24 socket strips** so the central area remains open.
- **Bottom:** male precision/turned contacts that insert into the target computer's existing 48-pin socket. The electrical contact positions must align with the upper contacts in X/Y, with **pin 1 corresponding to pin 1** (account for bottom-view mirroring).
- Investigate sourcing **genuine SMT socket strips**, but also prototype **THT socket strips with carefully bent solder tails** if suitable SMT types are unavailable. Bending machined brass contacts is a mechanical experiment, not an approved manufacturing process. Consider stamped-contact strips for better formability. Inspect for fractures, contact displacement and solder-joint weakness.
- Investigate **turned male pin strips** for the bottom connection. The previously considered **Preci-Dip 350 series** is through-hole, not automatically usable as a same-location SMT male connector. Confirm mating diameter, insertion depth, available standoff, solder termination and mechanical retention.
- Top and bottom surface-mount pads may coincide in projection because they are on opposite copper faces. Their **vias, routing, mask openings and mechanical loading** still need design attention. Do not assume the arrangement is manufacturable without checking actual connector drawings and an insertion/extraction test.
- The center should accommodate the **10 × 10 mm QFN-80** RP2350B/RP2354B, nearby decoupling and power components. The 15.24 mm DIP-row pitch is **between pin centers**, not a guaranteed 15.24 mm free component corridor. Check pad, socket-frame and solder-joint clearance precisely.
- The board must physically support installing/removing a real processor without cracking SMT joints or flexing the PCB excessively.

### 2.2 First mechanical deliverable

Before routing or final circuit complexity, create a **real KiCad PCB project** with:

- DIP-48 reference geometry, pin-1 orientation and a realistic PCB Edge.Cuts outline.
- A **top-side female 2 × 24 arrangement** and a **bottom-side male 2 × 24 arrangement**, exactly co-registered in position and correctly mapped electrically.
- The RP2350B/RP2354B 80-pin QFN footprint on the **top side, centrally located**, and provisional footprints for USB, crystal, power components, decoupling, SWD and input protection.
- A side-view clearance note/sketch in documentation, and mounting/height assumptions.
- Explicitly identifiable **provisional custom footprints** when a real supplier footprint is not yet selected; never represent a hand-modified THT connector as a manufacturer-approved SMT part.
- A placement screenshot/plot and a checkable measurement report (row pitch, contact pitch, MCU clearances, board dimensions).

Do not fabricate until connector selection, mating dimensions, pad design and assembly clearances are verified.

## 3. Electronics architecture

### 3.1 Main components

| Function | Proposed implementation |
|---|---|
| MCU | **RP2350B** (QFN-80, 48 GPIO, external QSPI flash) or **RP2354B** (same package, integrated 2 MB flash) |
| CPU emulator | C/C++ on one Cortex-M33 core, using MCL68+ as a potential starting point |
| Bus signal sequencing | RP2350 PIO plus GPIO; DMA where useful |
| Analyzer capture | PIO/DMA bounded transaction records, with triggers and overflow reporting |
| Host communication | Built-in USB 1.1 device PHY/controller; simple binary protocol |
| Firmware storage | Dedicated QSPI flash for RP2350B, or in-package flash for RP2354B |
| External working memory | **8 MiB (64 Mbit) PSRAM**, APS6404L-3SQR-ZR / JLCPCB C3040877, sharing QSPI clock/data with separate GPIO47 CS1 |
| Debug/programming | Native USB ROM bootloader / BOOTSEL; Raspberry Pi Debug Probe with a 3-pin JST-SH side-entry SWD connector, SM03B-SRSS-TB(LF)(SN) / C160403 |
| Power | Target-derived 5 V to a properly designed 3.3 V supply; RP2350's internal core regulator with required external components |
| Timing reference | Reference 12 MHz crystal for MCU/USB; target CPU clock monitored separately |

Use Raspberry Pi's **official RP2350B Minimal KiCad** schematic and **Hardware Design with RP2350** guide as the baseline for regulator, inductor, oscillator, USB resistor, supply filtering and decoupling values. For RP2354B verify the package/pin-compatible reference and in-package flash requirements. **QSPI clock/data, USB and SWD use dedicated pads; PSRAM additionally needs GPIO47 as QMI CS1.** RP2354B's in-package flash already uses QSPI_SS; there is no separate board-level flash IC.

### 3.2 68008 connections and GPIO allocation

The **48-pin MC68008** has 48 physical pins: **45 signals plus VCC and two GND pins**. Its bus includes **A0–A19, D0–D7, CLK, FC0–FC2, AS, DS, R/W, DTACK, BR, BG, BERR, E, VPA, RESET, HALT, and the two encoded interrupt inputs IPL1 and IPL2/IPL0**. Consult the Motorola manual to establish the **authoritative physical pin map**, polarity, direction, three-state behavior and exception-cycle semantics. Do not rely on the list above for final pin numbering.

The RP2350B/RP2354B offers **48 user GPIOs**. The working allocation concept is:

- **GPIO0–GPIO39:** 40 five-volt-tolerant digital GPIOs for direct electrical connection where valid.
- **GPIO40–GPIO47:** eight ADC-capable digital GPIOs **not** five-volt tolerant. Assign the remaining **five 68008 input-only signals** here using external protection/level adaptation, leaving three possible spare GPIOs.
- Proposed slower inputs for the five protected positions include the **two IPL lines, BR, and other motherboard-to-CPU inputs**. **Prefer CLK, DTACK and BERR on directly connected/timing-favorable pins** where feasible. Final assignment must be optimized for PIO pin grouping, sample timing, and the actual Motorola signal directions. Do not allocate a CPU output to a non-5V-tolerant input-only protected position without checking it explicitly.
- The RP2350B's 5 V tolerant pins require correct supply/power conditions; **3.3 V outputs must also meet the target's TTL input threshold and loading requirements**. Verify each affected signal electrically.
- **RESET and HALT** use one FT GPIO each for bidirectional open-drain-style operation: keep input sensing enabled and output data LOW; assert by enabling the output and release by disabling it. Disable internal pulls and use the target pull-ups; verify sink-current/LOW-level margins. Track self-assertions separately from externally held LOW signals. Target RESET must remain separate from MCU RUN.
- CPU address/control pins must be released when the real processor is installed, and when DMA owns the motherboard bus. The exact Motorola 48-pin **two-wire BR/BG arbitration** behavior must be implemented and tested before enabling bus-master operations against a real CPU.

**Important:** 40 direct lines plus five protected lines is a **conceptual count, not a completed PIO-feasible pinout**. Make the pinout a reviewed design deliverable with one row per MC68008 pin, MCU pin/GPIO, direction in each mode, voltage, pull state and PIO function.

### 3.3 Protection for five non-5V-tolerant inputs

Prototype selection updated 2026-11-10 (see [hardware review](../docs/hardware.md)):

- Per input: a **2.2 kΩ series resistor** followed by a **single BAT54 Schottky clamp to the 3.3 V supply** (anode at the protected MCU node, cathode at 3.3 V). Use five **user-selected R+O BAT54X / C19627026 SOD-523** parts and plain two-pin Schottky symbols: pad 1 cathode, pad 2 anode, no NC terminal. D1–D5 protect BERR, BR, VPA, IPL1 and IPL20 respectively. The compact package replaces the earlier SOT-23 choice without changing the protection topology.
- Fit **two 1 kΩ resistors in parallel** from 3.3 V to GND, reusing the existing Basic 1 kΩ part. The 500 Ω load draws 6.6 mA nominal. A conservative five-input injection bound is 4.63 mA at 5.25 V target / 3.234 V rail with 1% series resistors and zero diode drop; the load sinks at least 6.40 mA under that envelope. The LDO need not sink the injected current. A single 1 kΩ load lacks adequate current margin.
- **Accepted risk, 2026-11-09:** retain BAT54 clamps at the intended sub-mA currents; the user accepts the forward-voltage margin and expects Vf ≤0.3 V. The nominal resistor-only bound is 1.7 V / 2.2 kΩ = 0.773 mA before diode drop. Manufacturer-model SPICE results are recorded in `simulations/bat54/`; they support typical behavior rather than a guaranteed JSCJ production corner. Preserve the accepted decision while retaining startup and input-edge timing checks.
- The RP2350 GPIO40–47 recommended/absolute input voltage limits must be met. Raspberry Pi does not specify a general allowable sustained injection current through those GPIO's internal ESD structures; **do not use their internal diodes as the primary clamp**.
- A TTL-compatible 5 V-tolerant buffer remains a fallback if the simple clamp cannot meet margins. Avoid ordinary resistor dividers unless the **TTL HIGH threshold** at their reduced output is verified.

### 3.4 Other electrical and functional safeguards

- Select **RP2350 A4 silicon or later** where possible because of the earlier high-impedance GPIO erratum; confirm actual supplied stepping rather than relying on catalog names.
- Ensure **all bus-driving GPIOs are inputs / high impedance immediately after reset**, before user code or PIO initializes.
- Add an unambiguous **hardware mode interlock** (jumper/switch or socket-detection mechanism) so a physical CPU cannot be driven by the emulator accidentally. Mode change must be deliberate; passive mode is the default.
- Use **target-only power**, shared with the TTL-compatible target logic. USB VBUS is used only for MOSFET-isolated presence sensing; SWD supplies no board power. This common-power prototype assumption is accepted without selecting additional bus isolation. Still check the local 3.3 V rise/fall against driven bus signals: sharing 5 V does not imply simultaneous 3.3 V availability. Independent powering and hot insertion are outside that assumption.
- Bus timing and correct logic levels must be verified with a logic analyzer and the Motorola bus timing diagrams; PIO is deterministic but does **not** by itself make arbitrary software CPU emulation cycle accurate.
- Layout: **4 layers first**, suggested top signals/components, solid GND plane, power/signal layer, bottom signals/components. Use **6 layers only if beneficial** for fanout/ground/reference integrity. Observe manufacturer's switch-mode regulator layout recommendations. Keep pass-through traces short and minimize input stubs.

### 3.5 Control reservations and shared decoupling (2026-11-09)

- `MODE_PERMIT` / GPIO45 is JP1's physical firmware-permission input, default passive; it does not detect CPU presence or electrically disable pads.
- PSRAM addition, 2026-11-10: GPIO47 is `PSRAM_CS_N` / QMI CS1. Retain `USB_PRESENT_N` on **GPIO46** for active-low VBUS presence and self-powered USB attach/detach behavior. It detects cable power, not host application activity. USB VBUS remains sense-only.
- Remove the unused `BUS_ARM_REQUEST` reservation. R5 is MODE_PERMIT's 10 kΩ pull-down; R4 is repurposed as a **1 kΩ PSRAM CS pull-up**, reusing the existing Basic resistor SKU. An independent output inhibit remains unresolved; it has no spare GPIO reservation.
- Use **one shared 100 nF capacitor (C23)** for the co-registered top/bottom MC68008 supply contacts, not one per connector. Retain the regulator input/output capacitors and the MCU's own local bypass capacitors.

### 3.6 Assembly sourcing, schematic format and value reuse (2026-11-09)

- Keep all circuit sections on **one landscape A3 schematic sheet**, using readable symbol and text sizes rather than a hierarchical sheet structure. Use local signal labels and real power symbols; global signal labels are unnecessary on this single sheet. Preserve saved schematic layout edits when updating the circuit.
- Select purchased parts from **JLCPCB SMT assembly**, using **Basic** parts first where suitable and Extended parts where the electrical/mechanical requirements require them.
- Before adding an Extended SKU, check existing values and parts for a compatible reuse. Share pull-up/pull-down and protection values where practical; preserve explicitly required USB, clock, filtering and timing values.
- Record **LCSC C-number**, Basic/Extended class, source URL, verification date and the reason for each Extended selection in the BOM and schematic. Recheck class and stock when ordering.
- J1/J2 top/bottom 48-pin contact assemblies are soldered manually and are exempt from JLCPCB sourcing. JP1 is a PCB solder bridge and is excluded from the grouped upload BOM. **J4 is a purchased SMT connector included in the BOM:** JST SM03B-SRSS-TB(LF)(SN) / C160403, matching the Raspberry Pi three-pin debug cable, 1=SWCLK, 2=GND, 3=SWDIO, mounting tabs to GND. It replaces the former debug pads and has no 3V3/power contact. Confirm plug access at the board end with a CPU fitted.

### 3.7 PSRAM addition (2026-11-10)

- Fit **U5 APS6404L-3SQR-ZR**, 8 MiB, 2.7–3.6 V, in the compact USON-8 3 × 2 mm package. JLCPCB **C3040877** is Extended SMT. Use the reviewed pin/footprint mapping in [hardware.md](../docs/hardware.md); leave the unassigned centre paddle electrically floating.
- Connect SCLK/SIO0–3 to the dedicated QSPI pads shared with the RP2354B's in-package flash. Keep CE# separate on GPIO47 / QFN58; GPIO0/8/19 are also CS1-capable but carry target address signals.
- Hold PSRAM deselected through reset with R4 1 kΩ to 3.3 V. Fit C24 4.7 µF and C25 100 nF at U5 VDD/GND, reusing existing Basic capacitor SKUs; verify at least 1 µF effective local capacitance. Add 25 mA to the initial 3.3 V planning allowance for memory, CS pull-up and I/O activity, pending measurement.
- Firmware must configure **CS pin 47 and size 8,388,608 bytes explicitly**, disable the pin's reset pull-down, wait for PSRAM power-up and perform its reset/QPI initialization. Do not scan candidate CS pins: this could drive the target address bus. Begin at no more than 84 MHz linear-burst clock and obey CE# pulse/recovery limits. Hardware connectivity is supplied; PSRAM firmware and memory tests remain future work.

## 4. Software and validation plan

Develop in **incremental, independently testable phases**. The board must be useful well before a full 68008 emulator exists.

### Phase 0 — Toolchain and board bring-up

- Set up KiCad and the Raspberry Pi Pico C/C++ SDK, CMake, PIO assembler, host build/test tooling and debug support, across common operating systems (do not assume macOS).
- USB device with version/capabilities, boot/recovery, build metadata and diagnostic logging.
- GPIO pin-map self-test; safe high-impedance default; PIO clock tests; loopback fixture if possible.
- Read target clock; verify correct target power; refuse active mode if safety conditions fail.

### Phase 1 — Passive real-CPU analyzer (first useful milestone)

- Real MC68008 installed on top, electrical CPU-to-motherboard pass-through; every MCU bus GPIO input only.
- Use PIO to detect bus cycle boundaries and sample address, data, function codes, R/W, AS/DS, DTACK, BERR, relevant arbitration and timing information.
- DMA to a bounded circular buffer; trigger on address/mask, read/write, function code, error/timeout or activity; pre/post-trigger capture where memory allows.
- Provide USB tools to start/stop, configure triggers, download and decode traces to human-readable text and CSV (later VCD if useful).
- Prove that analyzer installation does not interfere with a known-good motherboard. Report FIFO/capture overflow rather than silently losing records.
- Cross-PIO sampling **must be synchronized**: pin-window, trigger alignment and timebase issues need an explicit design and bench validation.

### Phase 2 — Active bus-cycle generator and memory diagnostics

- Remove the physical CPU; switch into **CPU-replacement** mode with a hardware interlock.
- Firmware/PIO drive valid 68008 bus cycles using the motherboard CLK, data/address phase, AS/DS, R/W, function codes, DTACK/VPA/E and any applicable exceptions. Begin with read and write of **single bytes**; then bounded word/long accesses assembled as ordered 8-bit transfers.
- USB commands: inspect/reset the bus controller, read/write a memory byte or range, scan a bounded address range, RAM walking-bit tests and ROM checksum/dump. Distinguish RAM from **memory-mapped I/O with side effects**; require explicit opt-in for writes.
- Implement bus timeout, abort and safe deassertion. Never assume DTACK always arrives; capture BERR and arbitrate BR/BG as needed.
- Validate against a **bench bus fixture** (ROM/RAM mock or FPGA/logic fixture) before connecting to a valuable vintage motherboard.
- Manual memory examination is a hardware/bus diagnostic facility, **not yet CPU instruction execution**.

### Phase 3 — MC68008 CPU interpreter

- Study [MicroCoreLabs MCL68+](https://github.com/MicroCoreLabs/Projects/tree/master/MCL68%2B/code) as a candidate **software 68000 interpreter**, porting from Teensy/i.MX RT to RP2350 as permitted by its license.
- Separate instruction execution from hardware: a software bus interface supports byte/word/long reads and writes and returns DTACK/BERR/address-error status. For the 48-pin 68008, words use **two byte cycles**, longwords **four byte cycles**, with big-endian ordering and correct fault handling.
- Implement MC68008-specific **20-bit physical address behavior**, interrupt encoding/acknowledge, stack/exception behavior, reset vectors, trace, function codes, read-modify-write operations, DMA ownership and timing-sensitive peripheral cases.
- Test CPU instructions against established 68000-family test suites (e.g. Tom Harte's processor tests), ROM boot sequences and differential traces. Verify compatibility separately from external bus timing.
- Expose registers (D0–D7, A0–A7, PC, SR), step/run, halt, breakpoints, execution trace and debugger commands over USB.
- **Performance is unproven:** dual Cortex-M33 cores at nominal 150 MHz are considerably slower than the 600 MHz Teensy 4.1 used by MCL68+. Benchmark bus transactions and real code before promising 8–10 MHz replacement performance. PIO accelerates bus sequencing, not instruction decoding.

### Phase 4 — Enhancements (optional)

- Higher-level trace disassembly, memory maps/symbols, scripted test sequences, USB trace streaming and advanced error triggers.
- Adaptive bus timing or acceleration only after full electrical compatibility is established.
- Consider broader CPU-family support only as a separate hardware variant, not a requirement for this 48-pin design.

### Firmware/host architecture

- Keep a **hardware abstraction layer** for PIO/target cycles, a **bus-analyzer engine**, and a **CPU interpreter** as separate modules.
- Define a documented, versioned **binary USB command protocol** with explicit framing, escaping, integrity checking and recovery. The previously discussed `0xFF` delimiter/escape scheme (`FF 00` start, `FF 01` end, `FF 02` abort, `FF FF` literal) is a suitable starting point; enforce maximum frame lengths, CRC and validated-before-execute semantics. Adapt to native USB bulk/CDC transport as appropriate.
- Maintain independent and safe low-level recovery: BOOTSEL/SWD access must remain available even if firmware crashes.
- Automated tests for encoder/decoder, bus read/write ordering, timeouts, PIO sample alignment, pin mapping and emulator instruction semantics.

## 5. Deliverables and acceptance criteria

1. **KiCad schematic and PCB:** native editable `.kicad_pro`, `.kicad_sch`, `.kicad_pcb` files, any custom symbol/footprint libraries and reproducible plot/DRC steps.
2. **Initial placement-first PCB:** aligned top/bottom 48-pin DIP contacts; small outline; central MCU; preliminary support-component placements; a placement PNG/SVG/PDF and dimension report. **Do this before routing.**
3. **Engineering decisions:** pin mapping spreadsheet/CSV, electrical risk register, connector selection and alternatives with data-sheet sources, top-bottom socket feasibility assessment, BOM with supplier/manufacturer part numbers, budget estimate and explicit unknowns.
4. **Software repository:** buildable Pico SDK project, PIO modules, USB host utility, unit tests, stage-by-stage bring-up and test instructions.
5. **Validation checkpoints:** board electrical safety, unpowered condition, passthrough integrity, analyzer capture, manual read/write, then full CPU interpreter.

**Critical acceptance checks:** valid top-to-bottom 1:1 DIP connectivity; no pin-number mirroring mistakes; all GPIO reset states safe; QFN/support components physically fit; no collision between SMT pads/vias/contacts; protected inputs within specifications; target unaffected in passive mode; and no active bus cycles with the real CPU installed unless a separately verified bus-arbitration mode explicitly authorizes them.

## 6. Copy-and-paste prompt for Codex

> **Role:** Act as a hardware/firmware engineer creating a compact RP2350B/RP2354B MC68008 ICE board. Work iteratively in this repository. Produce real KiCad files and buildable firmware; do not stop at descriptive sketches. Treat the engineering specification above as project requirements, but correct factual mistakes discovered in authoritative documentation and record those corrections.
>
> **Project objective:** Create a low-cost four-layer (six-layer if necessary) 48-pin DIP MC68008 emulator and passive analyzer. A real 68008 may plug into a socket on the top of the PCB while male pins on the bottom plug into the motherboard. The RP2350 observes the shared CPU bus as all-input passive analyzer, or replaces the CPU to perform external bus cycles and eventually executes 68008 instructions in software.
>
> **First task — mechanical placement, not routing:**
> 1. Initialize a KiCad project and a short `README.md`. Determine the precise Motorola 48-pin DIP socket geometry from primary references. Establish a realistic initial board outline near the DIP package dimensions.
> 2. Place 2 × 24 **female socket contacts on the PCB top** and 2 × 24 **male plug contacts on the PCB bottom**, 2.54 mm pitch, 15.24 mm between rows. Their X/Y contact locations must be identical and every like-numbered pin connected electrically. Explicitly validate mirroring of bottom footprints and pin-1 placement.
> 3. Evaluate two mechanical socket solutions: (a) genuine SMT open-frame sockets/1 × 24 strips and (b) carefully bent conventional THT socket strips as experimental SMT parts. For the bottom evaluate suitable SMT precision male contact strips versus turned-pin through-hole products. Use clearly marked mechanical placeholders until a purchasable, dimensionally verified solution is chosen. **Do not claim that a THT connector is inherently SMT-compatible.**
> 4. Place a 10 × 10 mm QFN-80 RP2350B/RP2354B footprint between the DIP rows, preferably top side. Place realistic provisional footprints for 12 MHz crystal, core-regulator inductor/capacitors, 3.3 V regulator, USB-C, BOOTSEL, SWD, ESD and five input-protection networks. Check top socket open-frame clearance, pad/via conflicts, assembly clearances and insertion forces.
> 5. Generate a placement image, top/bottom screenshots, dimensions table, net/pin correspondence report and a short manufacturability/clearance list. **Stop and report concrete feasibility findings for this first task before beginning detailed routing.**
>
> **Second task — complete schematic:**
> 6. Import and adapt the official Raspberry Pi RP2350B Minimal KiCad design (power, 1.1 V regulator, 12 MHz crystal, USB, decoupling, QSPI flash where needed, SWD). Compare RP2350B with RP2354B integrated 2 MB flash and choose the simpler well-supported implementation. Keep dedicated USB/QSPI/SWD pins separate from bus GPIO allocation.
> 7. Create an authoritative table of all **48 MC68008 pins** from Motorola documentation (45 signals, VCC and two GND). Allocate 40 signals to 5 V-tolerant GPIO0–39 and five input signals to protected GPIO40–47, only if correct after PIO/timing analysis; preserve three spare GPIOs where feasible. Check active-low polarity, bidirectionality, CPU output tri-states, RESET/HALT, E/VPA, DTACK/BERR, IPL encoding and BR/BG.
> 8. Evaluate the prototype five-input 2.2 kΩ + BAT54-to-3.3 V protection and two parallel 1 kΩ rail loads. Calculate worst-case clamp current, rail rise, voltage-margin, edge-delay and back-power conditions. If unsafe, select the least-complex verified replacement and document why. Add an active/passive mode hardware safety interlock and power-selection safeguards.
> 9. Run schematic ERC and PCB DRC as appropriate. Record any intentionally unresolved connector, assembly or input-clamp items. Do not proceed to fabrication without resolving them.
>
> **Third task — staged software, keeping every milestone buildable:**
> 10. Build Pico SDK C/C++ firmware with documented safe GPIO initialization, USB command endpoint, boot/recovery and a host CLI. Include code comments explaining bus timing, safety and PIO synchronization.
> 11. Implement a first **passive analyzer**: real CPU passes through; MCU never drives bus; PIO/DMA record complete bus transactions into a bounded trace buffer. Provide address/data/control decoding, timestamps or cycle deltas, triggers, overflow detection and USB trace export. Demonstrate with recorded/simulated test vectors before a real motherboard.
> 12. Implement **active bus diagnostics** only with the real CPU removed and a confirmed hardware interlock: generate single-byte 68008 memory reads/writes through PIO, observe DTACK/BERR, implement timeout/recovery; then ordered byte sequences for words and longwords. Add USB commands to examine/dump memory and perform opt-in RAM tests. Validate using a low-risk bus fixture.
> 13. Investigate MCL68+ as a software CPU-core starting point. Identify license and isolate instruction interpreter from Teensy-specific GPIO. Port and benchmark on RP2350 with mock bus first; then wire it to the PIO 8-bit bus engine. Add 68008-specific addressing, exceptions, interrupts, bus error behavior, tracing and execution controls. Use instruction regression tests and real boot traces. **Do not assume that a 150 MHz RP2350 will achieve the original CPU's speed.**
>
> **Working process and evidence:** For each milestone, show the exact generated file paths, tool/library versions, build/DRC/test commands, test results, screenshots and unresolved risks. Use authoritative primary documentation; never invent footprints or part dimensions. Prefer portable build scripts rather than macOS-only commands. Avoid excessive abstract architecture and concentrate first on the **small PCB with aligned top and bottom DIP contacts**, then a minimal working analyzer, then bus-cycle generation, then CPU emulation.

## 7. Primary references

- [Raspberry Pi RP2350 downloads, datasheet, hardware guide and RP2350B Minimal KiCad](https://pip.raspberrypi.com/categories/1214-rp2350)
- [Raspberry Pi RP2350 datasheet (PDF)](https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf)
- [Raspberry Pi RP2350 family / RP2354B integrated flash](https://www.raspberrypi.com/documentation/microcontrollers/microcontroller-chips.html)
- [Motorola M68000 family reference including 48-pin MC68008 bus and signals](https://www.bitsavers.org/components/motorola/68000/M68000_Family_Reference_1988.pdf)
- [Motorola M68000 family user's manual](https://datasheets.chipdb.org/Motorola/68000/mc68000_userman.pdf)
- [MicroCoreLabs MCL68+ emulator source](https://github.com/MicroCoreLabs/Projects/tree/master/MCL68%2B/code)
- [MCL68+ project background](https://microcorelabs.com/2023/10/26/mcl68-motorola-68000-emulator-2/)
- [MCL68+ updated development report (2026)](https://microcorelabs.com/2026/)

**Design policy:** All specific component values, pin mappings, connector footprints and claimed timing margins must be checked against current original documentation before manufacturing. This document describes the design direction, not a production-approved schematic.
