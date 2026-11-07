# Initial hardware schematic

Open [`68008ice.kicad_pro`](68008ice.kicad_pro) in KiCad, then open the schematic
editor. [`68008ice.kicad_sch`](68008ice.kicad_sch) is the root sheet. A
[PDF preview](68008ice.pdf) is included for review without KiCad.

This is an editable starting point based on the
[2026-11-04 requirements](../requirements/MC68008_ICE_Project_Specification_2026-11-04.md).
It is incomplete and has intentional ERC findings; it is not ready for PCB
layout or fabrication. Loading, PDF export, netlist export, and ERC were checked
with KiCad 10.0.5. No PCB layout is included.

## Sheets

| Sheet | Contents |
| --- | --- |
| `68008ice.kicad_sch` | Project overview, sheet index, and signal conventions. |
| `cpu_sockets.kicad_sch` | J1 motherboard plug and J2 optional physical CPU socket, retaining the MC68008P DIP-48 pin numbers. |
| `cpu_translation.kicad_sch` | Six 74LVC541A receivers sensing all 45 CPU signals, plus three 74AHCT541 drivers for data, responses, and CPU clock. |
| `target_translation.kicad_sch` | Six 74LVC541A receivers sensing all 45 motherboard signals, plus six 74AHCT541 drivers for address/control, strobes, data, and auxiliary outputs. |
| `bus_safety.kicad_sch` | Common output-disable circuit and four separately gated open-drain RESET/HALT low drivers. |
| `usb_flash.kicad_sch` | FT2232HL signal allocation, configuration EEPROM, provisional 4 MiB SPI flash, USB connector, and JTAG recovery header. FTDI clocking and power support remain incomplete. |
| `fpga_core.kicad_sch` | U1 ECP5-25F CABGA-256, split by bank, JTAG, and power; all receiver, driver, bus-control, and FT245 signals have assigned balls. |
| `power_supply.kicad_sch` | Target-powered 3.3 V and 1.1 V bucks, 2.5 V LDO, sequencing, independent rail supervision, and baseline FPGA decoupling. |

`68008ice.kicad_sym` and `sym-lib-table` provide the project symbols. Standard
symbols are also embedded in the schematics. The project library contains
passive socket/plug versions of KiCad's MC68008P symbol, a 74LVC541A using the
standard 541 pin arrangement, and an ECP5 symbol built from Lattice's official
pin table. Adapted KiCad library symbols retain the
[KiCad library licensing terms](https://www.kicad.org/libraries/license/).

## Signal and ownership conventions

- `CPU_*` and `TGT_*` are separate physical **5 V** bus nets. They are connected
  through receivers, FPGA logic, and drivers rather than direct copper links.
- `FPGA_CPU_*_IN` and `FPGA_TGT_*_IN` are receiver outputs at **3.3 V**.
  `FPGA_*_OUT` signals feed the AHCT driver inputs. Matching global signal names
  connect these wires to U1 on the FPGA sheet. Each buffer also has a note listing
  its FPGA balls in channel 0–7 order; `-` marks an unused channel.
- Supply and ground connections use actual KiCad power symbols. `+5V` is the
  motherboard rail, distinct from `USB_VBUS`. The filtered FTDI analog and FTDI
  1.8 V rails have separate project power symbols.
- `_N` denotes active low. `RW` is high for a read. `IPL02_N` represents the
  combined IPL2/IPL0 input of the 48-pin CPU; there is also `IPL1_N`.
- Receiver `/OE1` connects to `RECEIVER_OE_N`, pulled high until Q8 enables it
  after `POWER_GOOD`; `/OE2` stays grounded. This prevents receiver outputs from
  driving FPGA side-bank inputs while VCCIO is up but the core is still off.
  Each AHCT `/OE1` has a 10 kΩ pull-up to 3.3 V.
  `/OE2` connects to `BUS_DISABLE_5V`, pulled up to the target's 5 V rail.
  Q1 pulls that common disable net low only when `BUS_ARMED_3V3` is high.
  The FPGA GPIO `BUS_ENABLE_3V3` is a request, qualified in hardware by
  `POWER_GOOD`, `FPGA_DONE`, and `FPGA_INIT_N`. R10 is a 1 kΩ request pull-down
  to overcome configuration weak pull-ups. FPGA pins never connect directly to
  the 5 V OE net.
- `CPU_DATA_OE_N`, `CPU_RESPONSE_OE_N`, and `CPU_CLOCK_OE_N` control the
  physical-CPU drive groups. The FPGA can select each response signal's value
  independently within the response group.
- `TGT_MASTER_OE_N` controls address, function code, R/W, AS, and DS outputs.
  Release those outputs and `TGT_DATA_OE_N` during DMA. `TGT_AUX_OE_N` separately
  controls BG and E so arbitration and clock behavior can be handled correctly.
- RESET and HALT have separate sensing and NMOS low drivers on both sides.
  Four AND gates qualify low-drive requests with `BUS_ARMED_3V3`; gate and
  request pull-downs provide default-off behavior. CPU-side pull-ups are fitted;
  target-side pull-ups are expected on the motherboard and need confirmation.
- Series gate resistors and Schottky clamps to `POWER_GOOD` hold Q1–Q5 off
  during logic-supply ramp-up. The interlock must be validated on hardware,
  including shutdown and failed/repeated configuration. Include gate RC delay
  when budgeting RESET/HALT response time.

The current allocation uses **12 receivers and 9 drivers**, exceeding the
specification's preliminary eight-plus-eight estimate. This follows from sensing
all 45 signals on both sides, including motherboard address/control during DMA,
and splitting outputs by ownership. Counts and grouping remain provisional.

Transparent forwarding still requires FPGA RTL; no passive bypass exists. The
RTL must avoid RESET/HALT feedback latching by distinguishing external low
assertions from its own drive, and must sequence data and output enables safely.

## FPGA, host, and power decisions

[`fpga_pins.csv`](fpga_pins.csv) lists all **256 unique FPGA balls**, their bank
and alternate function, escape-ring depth, usage, and assigned net. Blank entries
are spare or reserved pins. [`68008ice.lpf`](68008ice.lpf) carries the matching
LVCMOS33 pin constraints for the proposed RTL port names. It is a constraint
fragment; FPGA synthesis and timing closure have not been performed. The symbol uses the
[Lattice ECP5U-25 pinout, revision 2.0](https://www.latticesemi.com/view_document?document_id=50485).
The BGA footprint remains unset pending package-drawing review.

The current bus boundary connects 152 FPGA signals: 90 sense inputs, 51 driver
data/control outputs, four RESET/HALT low requests, six group enables, and one
common bus enable. Another 13 FT245 signals are connected and one sampling-clock
input is reserved, for **166 general I/O assignments**. `FPGA_TGT_CLK_IN` uses
**A7 / PCLKT0_0**; `CLK_50M` uses **G1 / GR_PCLK7_1**. The oscillator circuit
still needs to be added.

For example, CPU address bit 0 follows J2 pin 46 → U2 pin 2 → U2 pin 18 →
`FPGA_CPU_A0_IN` → U1 ball T2. The output path for target address bit 0 is
U1 ball T6 → `FPGA_TGT_A0_OUT` → U17 pin 2 → U17 pin 18 → J1 pin 46.
These are electrically connected nets in the exported KiCad netlist.

### BGA escape rule

Prefer the outermost legal BGA rows and columns, then successive inner rings.
Voltage-bank compatibility, clock access, boot behavior, and fixed pin functions
take precedence. Keep related interfaces grouped when ring depth is equal.
This rule also appears in the repository's [`AGENTS.md`](../AGENTS.md).

`escape_ring` is the minimum distance from a ball to any package edge: ring 0
means row A/T or column 1/16. Supply, configuration, and fixed JTAG pins are
excluded from the following GPIO counts.

| Escape ring | Assigned GPIO signals |
| --- | ---: |
| 0 — outermost | 47 |
| 1 | 44 |
| 2 | 41 |
| 3 | 33 |
| 4 | 1 |

The selected set exhausts legal GPIO candidates in rings 0–3 before using ring 4.
Five bank-8 D3–D7 pins carry target address outputs after configuration; they are
unused by the selected single-bit master-SPI boot mode. D2 remains spare. Other
unused configuration controls are reserved. Actual placement, escape routing,
and timing must still be reviewed before freezing this allocation.

FT2232H channel A uses ADBUS0/1/2/3 for TCK/TDI/TDO/TMS. Channel B uses BDBUS0–7
for D0–7 and BCBUS0/1/2/3/4 for RXF#/TXE#/RD#/WR#/SIWU#. Configure channel B
for **asynchronous FT245 FIFO** operation in the EEPROM. The 93LC46B x16 EEPROM
and flash capacity remain provisional selections. The USB connector is a
USB-C USB 2.0 receptacle with the HRO TYPE-C-31-M-12 footprint. The flash is
shared by FPGA configuration and user logic; verify access through the ECP5
configuration resources before implementing updates.

For master-SPI boot, flash chip select is **N8 / CSSPIN**. R8 is the slave-SPI
CSN/SN pin and is reserved. The flash clock remains N9 / CCLK; user logic must
drive it through `USRMCLK`. Release unused configuration ports in user mode when
using the corresponding pins as GPIO. See Lattice's
[sysCONFIG guide](https://www.latticesemi.com/view_document?document_id=50462),
especially sections 4.7 and 6.1.2. Gateware must keep target drivers disabled
through configuration and reconfiguration.

J3 is a **custom 3.3 V JTAG header**, with the following pinout. Open R22–R24
(the three FTDI JTAG source links) before driving it with an external programmer;
the schematic labels identify the links if references change later.

| Pin | Signal | Pin | Signal |
| --- | --- | --- | --- |
| 1 | 3.3 V reference | 2 | TMS |
| 3 | GND | 4 | TCK |
| 5 | GND | 6 | TDO |
| 7 | GND | 8 | TDI |
| 9 | GND | 10 | Unconnected |

`+5V` originates at motherboard pin 13 and supplies the physical CPU, AHCT
drivers, and regulators. **Every functional supply, including the FT2232H, comes
from the target.** The proposed supply circuits are on the power sheet:

| Rail | Proposed regulator | Rated output capacity |
| --- | --- | ---: |
| +1V1 | TPS62130A buck from +5V | 3 A |
| +3V3 | TPS62160DGK buck from +5V | 1 A, including auxiliary LDO input |
| +2V5 | TLV75525PDBV LDO from +3V3 | 500 mA, subject to thermal limits |

The feedback ratios set the bucks to approximately 1.0992 V and 3.296 V.
The 3.3 V regulator's PG enables the core buck and auxiliary LDO, establishing
configuration I/O/flash power first. These are capacity choices; the actual
FPGA load still needs a power-calculator run using implemented logic and activity.
At full simultaneous buck ratings, a 90%-efficiency assumption would imply about
1.47 A from +5V, before direct CPU/buffer loads. The socket's single +5V contact,
target PCB and PSU must be checked against the actual measured budget.

The FPGA core and auxiliary rails follow the
[ECP5 supply guidance](https://media.latticesemi.com/-/media/LatticeSemi/Documents/ApplicationNotes/EH/FPGA-TN-02032-1-4-ECP5-ECP5G-sysIO-Usage-Guide.ashx?document_id=50464).
The [ECP5 datasheet](https://www.latticesemi.com/view_document?document_id=50461)
specifies 1.045–1.155 V for VCC and 2.375–2.625 V for VCCAUX, and the master-SPI
power-up constraint. Its side-bank hot-socketing limits motivate receiver gating.

TPS37043BJOFDDFRQ1 monitors the three FPGA rails using nominal ±4% windows
and a 10 ms release delay. Its outputs, core PG, and a TPS3808G50 +5V supervisor
form the open-drain `POWER_GOOD` net. The +5V supervisor has a nominal 4.65 V
falling threshold and a 20 ms release delay; tolerance and hysteresis can require
approximately 4.86 V at startup. Review these thresholds against the target PSU.
The monitor remains independent of FPGA firmware. Baseline bypassing includes
one 100 nF capacitor per FPGA supply ball and local bulk capacitance; final PDN
and thermal review still require a PCB layout.
[Regulator](https://www.ti.com/lit/ds/symlink/tps62130a.pdf),
[I/O buck](https://www.ti.com/lit/ds/symlink/tps62160.pdf),
[auxiliary LDO](https://www.ti.com/lit/ds/symlink/tlv755p.pdf),
[rail monitor](https://www.ti.com/lit/ds/symlink/tps3704.pdf), and
[+5V supervisor](https://www.ti.com/lit/ds/symlink/tps3808.pdf) datasheets.

### USB power and presence detection

USB-C supplies the USB 2.0 data connection, shared ground, and two independent
5.1 kΩ CC pull-downs. It supplies **no board power**. VBUS connects only through
100 kΩ to Q6's insulated gate, with a 1 MΩ gate bleed to ground. Q6 and Q7 form
two inversions, producing a target-powered `FTDI_PWRSAV_N` signal. At 5 V,
the sensing resistor path draws about 4.5 µA into ground; it does not feed +3V3
or any regulator. The FTDI interfaces therefore share the target supply domain
with the FPGA, avoiding a separately USB-powered I/O domain.

| Target power | USB VBUS | Result |
| --- | --- | --- |
| Off | Present or absent | FTDI and board remain unpowered; VBUS only biases Q6's gate. |
| On | Absent | Q6 off, Q7 on: `PWRSAV#` low, USB PHY suspended. |
| On | Present | Q6 on, Q7 off: `PWRSAV#` high, normal USB operation permitted. |

Program the FTDI EEPROM for self-powered operation and enable suspend on
BCBUS7 low. Channel B stays in asynchronous FIFO mode; channel A remains
available for MPSSE/JTAG. `FTDI_RESET_N` follows `POWER_GOOD` through a resistor.
The FTDI self-powered connection and `PWRSAV#` behavior are described in
[its datasheet, section 6.2](https://ftdichip.cn/Support/Documents/DataSheets/ICs/DS_FT2232H.pdf).
The USB ESD part is rail-less TPD2EUSB30, and connector shield is bonded to ground.

### NEORV32 application debugging

NEORV32's optional on-chip debugger supports halt, single-step, register and
memory access, and hardware break/watchpoints with OpenOCD/GDB. Enable `OCD_EN`
in the selected core version. The stock DTM exposes four JTAG signals; vendor
JTAG infrastructure can share the FPGA's existing configuration connection.
[NEORV32 debugger documentation](https://stnolting.github.io/neorv32/#_on_chip_debugger_ocd)

The intended board path is FT2232H channel A → ECP5 configuration TAP → `JTAGG`
→ a gateware debug bridge → NEORV32. **No extra debug IC, connector, or FPGA
GPIO is required for this approach.** It needs an implemented tunnel and matching
OpenOCD configuration; wiring the FPGA's JTAG pins alone does not expose the
CPU debugger. An external-DTM implementation may use `OCD_EXT_DTM` and the
processor's DMI ports. This integration is planned, not yet implemented or tested.
[ECP5 JTAGG reference implementation](https://github.com/tomverbeure/ecp5_jtag)

OpenOCD supports configurable BSCAN tunnels for non-Xilinx TAPs; the chosen
bridge must match that protocol or supply its own host support.
[OpenOCD RISC-V tunnel configuration](https://openocd.org/doc/html/Architecture-and-Core-Commands.html)

Alternatively, exposing NEORV32's stock JTAG port on four GPIOs permits a direct
connection to a JTAG adapter. The FTDI pin mapping is documented in the
[NEORV32 debugging tutorial](https://stnolting.github.io/neorv32/ug/#_using_the_on_chip_debugger).
Channel B remains the FT245 FIFO, so a direct approach would need routing or
selection for channel A. Debug resets must leave bus safety and ownership intact.

## Work before layout

1. Confirm FPGA fit and timing with the assigned I/O, review placement and
   escape routing, and add the approximately 50 MHz sampling oscillator.
2. Validate regulator sizing, target/socket current capacity, sequencing,
   monitor thresholds and the hardware interlock. Verify target-off/USB-on
   behavior and prove that startup/configuration cannot drive the bus.
3. Review the installed ECP5 bypassing, bulk capacitors, master-SPI straps and
   pull-ups against the actual layout. Check user access to the shared SPI flash.
4. Complete FTDI support: 12 MHz crystal and load capacitors, REF resistor,
   final VCCIO decoupling, and EEPROM programming. REF bias, analog filtering,
   regulator/core bypassing, reset and VBUS sensing are now drawn.
5. Validate the selected USB-C footprint, ESD placement, shield treatment,
   USB routing and target timing constraints.
6. Confirm CPU socket/plug dimensions and bottom-view orientation, BGA footprint,
   assembly availability, and four-layer breakout feasibility. Review translation
   delays, data/DTACK skew, clock duty cycle, and DMA handoff.
7. Resolve ERC after completing the missing circuitry. Spare FPGA pins,
   isolated support-circuit endpoints, undriven inputs, and undriven supply rails are
   currently expected. Checks have not been suppressed with no-connect markers
   or power flags on unfinished connections.

The provisional schematic was checked by exporting a netlist and reviewing the
socket mapping, domain isolation, translator supplies/enables, and host signal
mapping. Successful export establishes file readability; it does not establish
electrical completeness or timing closure.

The current ERC report has 32 findings: 28 spare/reserved FPGA pins, three
isolated clock endpoints, and one undriven oscillator input. The power, bus-safety,
CPU translation and target translation sheets have no ERC findings. Power flags
identify actual regulator outputs or external supply sources. Remaining clock
circuitry and spare pins stay visible for the next design iteration.

Useful component references:

- [Motorola M68000 user manual](https://www.nxp.com/docs/en/reference-manual/MC68000UM.pdf)
  — MC68008 variant and bus behavior.
- [74LVC541A datasheet](https://assets.nexperia.com/documents/data-sheet/74LVC541A.pdf)
  — 5 V-tolerant receiving at 3.3 V.
- [74AHCT541 datasheet](https://www.ti.com/lit/ds/symlink/sn74ahct541.pdf)
  — TTL-compatible inputs and output-enable behavior.
- [FT2232H datasheet](https://ftdichip.com/wp-content/uploads/2020/07/DS_FT2232H.pdf)
  — channel pin mapping and required support circuits.

To regenerate review outputs from the repository root:

```sh
kicad-cli sch export pdf --output kicad/68008ice.pdf kicad/68008ice.kicad_sch
kicad-cli sch export netlist --output /tmp/68008ice.net kicad/68008ice.kicad_sch
kicad-cli sch erc --output /tmp/68008ice-erc.rpt kicad/68008ice.kicad_sch
```
