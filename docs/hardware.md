# Pin mapping and candidate BOM review

Revision 0.3, 2026-11-09. This is a schematic starter with reviewed physical pin
numbering and a **proposed** GPIO allocation. It is not an electrically validated
board. All circuit sections are kept on one landscape A3 schematic. The current iteration establishes mapping, parts and schematic connections;
mechanical placement remains required before routing.

## MCU choice

Use **RP2354B**, QFN-80, with 2 MB in-package flash, and require A4 or later silicon.
It removes the external flash and its routing from the cramped DIP adapter.
Raspberry Pi's hardware guide permits adapting the RP2350B Minimal design by
omitting its external flash while retaining BOOTSEL. This starter follows that
approach; external QSPI data/clock pads are left unconnected, and QSPI_SS retains
the boot switch. RP2350B with external flash is an alternative requiring a
separate schematic variant. [Raspberry Pi hardware guide](https://pip-assets.raspberrypi.com/categories/1214-rp2350/documents/RP-008280-DS-2-hardware-design-with-rp2350.pdf)

## Physical pin map

[mc68008_pinmap.csv](../kicad/mc68008_pinmap.csv) contains one row per DIP pin:
signal, GPIO, QFN pad, direction in each mode, interface, reset/pull policy and PIO
role. [rp2354b_gpio.csv](../kicad/rp2354b_gpio.csv) lists all 48 GPIO assignments.
The CSV is the generator's source for bus connections, rather than an unrelated
spreadsheet maintained separately.

The physical MC68008 pin numbers were transcribed from **MC68000UM Figure 11-5,
printed page 11-6 (PDF page 175)** and checked against the installed KiCad MC68008P
symbol. In particular: pin 13 is VCC; pins 15/35 are GND; CLK is 34; DTACK is 31;
RESET/HALT are 37/36. The combined IPL2/IPL0 input is pin 42. The 48-pin device
has **no BGACK**, and its interrupt encoding provides levels **0, 2, 5 and 7**.
[Motorola manual, sections 3 and 11](https://www.nxp.com/docs/en/reference-manual/MC68000UM.pdf)

J1 is the upper CPU socket assembly; J2 is the lower target plug assembly. Both
use the same physical DIP numbering. Every J1 pin connects to the like-numbered
J2 pin, including supplies. The MCU observes taps on these shared nets; there is
no intervening MCU path in the CPU pass-through.

| GPIO | Assignment | Electrical path |
| --- | --- | --- |
| 0–19 | A0–A19 | Direct FT GPIO; target-powered TTL assumption |
| 20–27 | D0–D7 | Direct FT GPIO, bidirectional in replacement mode |
| 28–31 | AS_N, DS_N, RW, CLK | Direct; shared strobe/clock observation |
| 32–34 | FC0–FC2 | Direct |
| 35–37 | DTACK_N, BG_N, E | Direct |
| 38–39 | HALT_N, RESET_N | Direct; drive low or release only |
| 40–44 | BERR_N, BR_N, VPA_N, IPL1_N, IPL20_N | 2.2 kΩ series + BAT54 upper clamp |
| 45 | MODE_PERMIT | JP1 physical permission input; open = passive; 10 kΩ pull-down |
| 46 | BUS_ARM_REQUEST | Unused hardware-enable reservation; currently only R5 to GND |
| 47 | USB_PRESENT_N | Active-low MOSFET-isolated VBUS detector, retained for USB attachment |

Suffix `_N` denotes active low; `RW` is high for read, low for write. `IPL20_N`
denotes one physical combined IPL2/IPL0 signal, not an extra interrupt pin.

There are **45 target signals**, using 40 direct and five resistor/clamp connections.
The remaining three GPIOs are allocated to mode, arm and USB presence; there are
no uncommitted GPIOs in this draft. USB, flash and SWD use their dedicated pads.
Package-pad numbers and FT/non-FT classification follow the QFN-80 tables in the
[RP2350 datasheet, sections 14.8–14.9](https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf).

## PIO feasibility

Each PIO instance sees 32 GPIOs: GPIOBASE 0 exposes GPIO0–31; GPIOBASE 16 exposes
GPIO16–47. The setting applies to the entire PIO instance. State machines cannot
independently select both windows within one block. [Pico SDK PIO API](https://github.com/raspberrypi/pico-sdk/blob/master/src/rp2_common/hardware_pio/include/hardware/pio.h)

- PIO0, base 0: all 20 address bits, eight data bits, AS/DS/RW and CLK fit in one
  window. Address and data each form contiguous output groups. AS/DS/RW form a
  three-pin SET group; CLK stays an input.
- PIO1, base 16: function codes, acknowledgements, error/arbitration and interrupt
  inputs are accessible, along with the same AS/DS/RW/CLK pins and all data bits.
- PIO2 remains available, but adds no GPIO. An active bus engine may need to
  communicate completion across blocks; a PIO IRQ flag alone is not a shared
  inter-block handshake.

This establishes pin-window feasibility, not an assembled PIO program or proven
cycle timing. A concrete implementation must synchronize transaction snapshots
and pair records across blocks, account for input synchronizers and clamp-node RC delay,
and test timeout/abort, data direction changes and BR/BG ownership. No capture
rate or 8–10 MHz CPU replacement performance is claimed.

Only four slow, input-only signals remain after keeping CLK, DTACK and BERR
direct: BR, VPA and the two IPL lines. Therefore the original five-protected-input
concept cannot keep all three timing inputs direct without changing another
connection. This draft protects **BERR** with a series resistor and clamp as the fifth input,
preserving direct bidirectional RESET/HALT connections. Include the resulting
RC edge delay and sampling latency in the error-recognition budget.

## BAT54 input clamps and rail load

The target is assumed to use TTL-compatible signals and one common 5 V supply.
Following the design choice agreed on 2026-11-09, **U3/C3 are removed**. R14–R18
are five identical **2.2 kΩ** input resistors. **D1–D5 are five single BAT54
Schottky diodes**, one per input, so each clamp can sit beside its MCU pad during
routing. Anodes connect to the MCU side of the resistor; cathodes connect to
3.3 V. The SOT-23 pinout is **1 = anode, 2 = NC, 3 = cathode**. Leave pad 2
unconnected; BAT54A/C/S are different diode configurations.
[Selected JSCJ BAT54, C8590](https://jlcpcb.com/partdetail/BAT54/C8590)

| Input | Series resistor | Single clamp |
| --- | --- | --- |
| BERR_N | R14 | D1 |
| BR_N | R15 | D2 |
| VPA_N | R16 | D3 |
| IPL1_N | R17 | D4 |
| IPL20_N | R18 | D5 |

R19 and R20 are **two 1 kΩ resistors in parallel**, giving 500 Ω nominal from
3.3 V to GND. They reuse the Basic 1 kΩ part already used for BOOTSEL and crystal
damping. This load absorbs incoming clamp current; the LDO is not expected to
sink it. A single 1 kΩ part is too close to, or below, the possible five-input
injection current.

| Steady-state calculation | Result |
| --- | --- |
| Target maximum for 5 V ±5% | 5.25 V |
| Conservative 3.3 V rail minimum, using a ±2% envelope | 3.234 V |
| Minimum series resistance, 2.2 kΩ ±1% | 2178 Ω |
| Conservative maximum injection, five HIGH inputs, assuming zero diode drop | 5 × (5.25 − 3.234) / 2178 = **4.63 mA** |
| Minimum load current, both 1 kΩ resistors at +1% | 2 × 3.234 / 1010 = **6.40 mA** |
| Minimum sink-current margin before MCU consumption | **1.78 mA** |
| Nominal continuous load | **6.6 mA**, **21.8 mW** total |
| Worst resistor dissipation at 3.366 V and −1% resistance | **11.5 mW per resistor**, below 62.5 mW rating |

The bound deliberately does **not** depend on weak TTL HIGH drive or MCU current
consumption. TTL HIGH may be lower than 5 V, which reduces injection. All five
HIGH inputs were nevertheless evaluated at the maximum supply voltage. The
selected LDO has a tighter nominal accuracy than this calculation's ±2% envelope.

**Accepted design decision (2026-11-09): retain the BAT54 clamps.** The user
accepts the forward-voltage margin risk and expects Vf at or below 0.3 V at the
intended sub-mA current. This is an accepted circuit assumption, with the
[nominal SPICE analysis](../simulations/bat54/README.md) supporting the choice.
It is not a pending approval condition or a reason to substitute the buffer.

The requested nominal current bound is `(5.0 − 3.3) / 2.2 kΩ = 0.773 mA` before
allowing for diode drop. The manufacturer proxy model gives **0.200 V at that
forced current, at 25°C**. Solving the actual series circuit gives **0.683 mA
and 0.197 V**. The earlier approximately 0.5 mA estimate is an expectation for
TTL-driven conditions, not the conservative resistor-only bound. The 4.63 mA
five-input injection budget above is retained.

For traceability, the selected JSCJ datasheet specifies up to 0.32 V at 1 mA /
25°C; the RP2350 recommended input maximum is IOVDD + 0.3 V. The user has accepted
that margin without claiming a guaranteed production corner. The available
simulation uses the Diodes Inc/Zetex BAT54 model, rather than a validated JSCJ
BAT54 model. Original datasheet references remain below.
[JSCJ electrical characteristics](https://datasheet.lcsc.com/lcsc/2304140030_Jiangsu-Changjing-Electronics-Technology-Co---Ltd--BAT54_C8590.pdf),
[RP2350 electrical limits](https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf)

For timing planning, 2.2 kΩ and an illustrative 20 pF total node capacitance give
44 ns RC time constant. With a 2.4 V HIGH step, reaching a 2.0 V threshold takes
about 79 ns in that simple model. This is a sizing example, not a worst-case
capacitance or measured BERR delay. Test the actual edges, capacitance, leakage,
pad pulls and cross-PIO sampling on the fixture before accepting bus timing.

## Target-power assumption

The board takes power **only from the host CPU socket**, while surrounding target
logic uses the same host 5 V rail. USB VBUS remains sense-only and SWD must not
supply power. No separate bus isolation circuit is selected in this prototype;
that is an accepted design assumption, not a claim that all local rails track
exactly in time.

The ICE's LDO creates its 3.3 V rail after the common 5 V input rises, so common
power does not itself prove FT GPIO exposure is safe during startup or decay.
Check 5 V, 3.3 V and driven bus voltages together during rise/fall, reset and USB
connection. GPIO0–39 tolerate 5 V only with the specified IOVDD present. A bleed
load also cannot hold an unpowered 3.3 V rail at zero if external inputs remain
HIGH. Externally powered signals, hot insertion and independent USB/SWD powering
are outside this shared-target-power assumption. These are validation conditions;
the removed `TBD_POWER_ISOLATION` BOM row is not a required part selection.

## Power, USB and reset

U2 is a candidate **TLV75533PDBVR** 5 V-to-3.3 V LDO. Its 500 mA capability is a
device rating, not the expected load or permissible dissipation in this PCB.
Plan initially for a 100 mA continuous/200 mA transient 3.3 V allocation, then
measure real MCU/USB/GPIO loads and confirm the target can supply them. At nominal
5 V input, LDO dissipation is 0.17 W at 100 mA and 0.34 W at 200 mA. Temperature,
copper area, target tolerance and transient behavior must determine acceptance
or a switcher alternative. [TI TLV755P datasheet](https://www.ti.com/lit/ds/symlink/tlv755p.pdf)

The MCU core uses its internal switching regulator: the reference 3.3 µH
Abracon AOTA-B201610S3R3-101-T, 4.7 µF local capacitors and 33 Ω/4.7 µF VREG_AVDD
filter. VREG_VIN is 3.3 V; feedback and DVDD are on 1.1 V. Preserve the reference
layout and marked inductor orientation, and check effective ceramic capacitance.
The 12 MHz crystal and 1 kΩ output damping resistor also follow the official
Minimal R4-S1 circuit. Decoupling shown on the A3 schematic must be placed at the
corresponding MCU pads. [Reference design and guide](https://pip.raspberrypi.com/categories/1214-rp2350)

The USB-C port is self-powered from the target. VBUS connects only to a resistor
and Q1's gate detector, with a gate-to-ground resistor; Q1's drain is pulled up to
board 3.3 V. `USB_PRESENT_N=0` means a cable source is present. There is no
intentional DC VBUS-to-board supply path. CC1 and CC2 have separate 5.1 kΩ Rd
resistors; the USB data pair uses 27 Ω series resistors and a ground-referenced
TPD2EUSB30A ESD part. Check attachment/detachment with the target off and every
power transition; the ROM bootloader's behavior must also be assessed for this
self-powered connection.

## Programming and debugging

J4 also supports automated SWD firmware uploads and source debugging, without
pressing BOOTSEL. See [programming.md](programming.md) for wiring and tool commands.

## Mode permission and arm reservation

`MODE_PERMIT` is the GPIO45 input from solder bridge JP1. Open JP1 gives a LOW
through R4 and selects passive-only permission. Bridging JP1 gives HIGH and tells
firmware that the user deliberately permits CPU-replacement operations. It does
not sense whether a CPU is physically installed. Firmware must still require the
physical CPU to be removed and an explicit host command before starting active
cycles. Merely closing JP1 must not start bus driving.

`BUS_ARM_REQUEST` on GPIO46 is a proposed firmware output for a future independent
output-enable circuit. **At present it connects only to R5's pull-down.** It does
not gate any GPIO or make the current board electrically incapable of driving
with a real CPU installed. It is a reservation, and GPIO46 can be reassigned if
that future circuit does not need it. Keep it LOW during reset/passive operation.
There is no implemented arm firmware yet.

These signals represent two different intentions: physical mode permission and a
later software request to enable hardware. JP1 alone provides only firmware-level
protection. An independently enforced output inhibit remains a separate design
item.

## Bidirectional open-drain RESET and HALT

**The current one-GPIO-per-signal connection can handle both directions.** HALT_N
is GPIO38 / QFN pad 47 / DIP pin 36; RESET_N is GPIO39 / QFN pad 48 / DIP pin 37.
Both are FT pads. Keep the input buffer enabled and the output latch fixed at
zero; control only the output enable:

| Operation | Output latch | Output enable | Input observation |
| --- | --- | --- | --- |
| Passive / released | 0 | Disabled | Read actual line level from the target/real CPU |
| Assert LOW | 0 | Enabled | Read the line LOW; firmware knows it is asserting it |
| Release again | 0 | Disabled | Target pull-up raises it unless another device still asserts LOW |

Disable internal pulls and retain the target's external pull-ups. Never drive
these lines HIGH. Configure an appropriate sink drive for the actual motherboard
pull-ups and check the resulting LOW voltage. The pad's `OD` bit means **output
disable**, not an automatic open-drain mode.

The planned SIO pattern with the Pico SDK is `gpio_put(pin, false)` before any
output enable, `gpio_set_dir(pin, GPIO_OUT)` to assert and `gpio_set_dir(pin,
GPIO_IN)` to release, with `gpio_set_input_enabled(pin, true)` retained. A PIO
implementation likewise keeps output data zero and changes pin direction.
[RP2350 pad controls, section 9.6 and GPIO38/39 registers](https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf),
[Pico SDK GPIO API](https://github.com/raspberrypi/pico-sdk/blob/master/src/rp2_common/hardware_gpio/include/hardware/gpio.h)

Track the emulator's own assertions. While it holds a wired line LOW, it cannot
determine whether another device is also pulling that line LOW. Once released,
a remaining LOW is observable as an external assertion. Target RESET and MCU
`MCU_RUN_N` remain separate: a target reset must not restart the analyzer MCU.
The emulated RESET instruction asserts the target RESET output without resetting
the interpreter; an external reset sequence and a double-bus-fault HALT output
need their distinct Motorola semantics.
[Motorola MC68000UM section 3.6](https://www.nxp.com/docs/en/reference-manual/MC68000UM.pdf)

These are firmware implementation requirements; there is no working bus firmware
in the repository yet. GPIO reset isolation/output-disable and early pull removal
also remain part of bring-up.

## USB presence

`USB_PRESENT_N` on GPIO47 means **VBUS present**, active LOW through Q1. It is
retained. Even though useful ICE operation needs USB, the target may stay powered
while the cable is unplugged, the host is off or a port removes VBUS. The self-
powered device should enable its USB attachment pull-up only when VBUS is present
and withdraw it when VBUS disappears. The detector lets application firmware make
that decision without powering the board from USB. It does not prove successful
enumeration, a data-capable cable or a running host application.
[USB self-powered VBUS guidance](https://www.st.com/content/st_com/en/technical-documents/an4879-introduction-to-usb-hardware-and-pcb-guidelines-using-stm32-mcus-stmicroelectronics_asset/chunk-003-topic-an4879-vbus-sensing-detection.html)

No current bus signal needs GPIO47. Keep the detection circuit; its operation in
application firmware and ROM BOOTSEL recovery still needs validation. Disconnecting
only the host application may leave VBUS present, so this signal is not a host
command/heartbeat watchdog.

## Shared pass-through decoupling

**Fit C23 once:** one 100 nF / Basic C1525 capacitor from the common J1/J2 5 V
supply to GND. The top and bottom contacts are electrically one pass-through at
the same X/Y location, so they do not each get a separate copy of this capacitor.
Place it near the common pin-13 supply contact and a short ground-plane return.

C4 (10 µF on 5 V) and C5 (10 µF on 3.3 V) are the LDO's input/output capacitors;
they serve different supply nodes and both remain. C9–C22 are local MCU
3.3 V/core bypass capacitors and also remain. C23 reuses their 100 nF catalog
part and introduces no new purchased part type.

## JLCPCB BOM and value reuse

[BOM.csv](../kicad/BOM.csv) is the full per-reference engineering BOM, including
LCSC C-numbers, JLCPCB Basic/Extended class, assembly method, source URL, selection
rationale and verification date. These fields are also embedded in schematic
symbols. [BOM_JLCPCB.csv](../kicad/BOM_JLCPCB.csv) is the grouped upload BOM, using
JLCPCB's Comment / Designator / Footprint / LCSC Part # columns.

**56 JLCPCB SMT placements use 20 distinct catalog numbers: 12 Basic and eight
Extended types.** There are 60 instantiated schematic positions in total. J1/J2
are manually fitted contact assemblies; J4 SWD pads and JP1's solder bridge are
PCB features. These four positions have no JLCPCB part number and are excluded
from the upload BOM. Each J1/J2 assembly represents two 24-contact rows.

The [dated catalog manifest](../kicad/parts_catalog.json) records direct JLCPCB
product-page classifications and hashes of the consulted HTML, not a historical
third-party Basic-parts list. All selected purchased parts are classified as SMT
assembly. Catalog classification does not guarantee present stock or reserve
parts. Recheck BOM matching, inventory and assembly charges before ordering.

| Function | Selection / LCSC | Library |
| --- | --- | --- |
| MCU | RP2354B / C39843328 | Extended |
| 3.3 V LDO | TLV75533PDBVR / C404027 | Extended |
| Input clamps | BAT54 / C8590, five identical single diodes | Extended |
| Core inductor | AOTA-B201610S3R3-101-T / C42411119 | Extended |
| Crystal | ABM8-272-T3 / C20625731 | Extended |
| USB-C | USB4105-GF-A / C3020560 | Extended |
| USB ESD | TPD2EUSB30ADRTR / C94934 | Extended |
| USB detector | JSCJ 2N7002 / C8545 | Basic |
| Recovery buttons | XUNPU TS-1088-AR02016 / C720477, both identical | Basic |
| Resistors | Seven values; only the required 27 Ω USB value is Extended | Six Basic types, one Extended |
| Capacitors | Shared 15 pF, 100 nF, 4.7 µF and 10 µF parts | Four Basic types |

The complete linked selection table, quantities and reasons for each Extended
choice are in [JLCPCB_parts.md](../kicad/JLCPCB_parts.md).

Value consolidation:

- RUN pull-up, mode/arm pull-downs, detector pull-up and VBUS gate series resistor
  all use the same **10 kΩ** Basic part. VBUS gate pull-down becomes **100 kΩ**,
  retaining the original 10:1 divider ratio and removing the former 1 MΩ SKU.
- The two permanent-load resistors reuse **1 kΩ**. All five clamp series resistors
  use one **2.2 kΩ** SKU, and all clamps use one BAT54 SKU.
- USB-C CC1/CC2 each keep **5.1 kΩ**. USB D+/D− retain the specified **27 Ω**
  Extended part. The investigated 0603 27 Ω part C25190 is also Extended; changing
  package would not remove that type. The Basic **33 Ω** VREG_AVDD filter stays
  at its reference value because changing it saves no Extended feeder type.
- Both crystal capacitors use the same Basic **15 pF C0G** part. Basic crystal
  C9002 has 20 pF load / 80 Ω ESR, unlike the reference crystal's 10 pF / 50 Ω;
  it was not substituted just because it is also 12 MHz.
- The three 4.7 µF sites and two 10 µF sites each share one Basic part. Check
  effective capacitance under bias, especially the core regulator's capacitors.
- The two former Wurth switches are replaced by the same **Basic two-pad SMT
  switch** and matching KiCad footprint. The unused four-pad custom footprint is
  removed. The core inductor retains its reference-derived footprint.

The under-US$10 electronics target remains unquoted. The earlier US$4.09 planning
subtotal is retired: the selected BOM and circuit have changed, and Extended
assembly/setup fees are separate from component prices. No PCB/CPL file exists
yet, so the upload BOM is a component-selection deliverable, not a complete
assembly order. The independent output interlock remains an explicit,
unimplemented, uncosted BOM item.

## Mechanical work still required

No PCB or connector footprint is supplied in this iteration. Do not route until
an actual placement study checks the co-registered 2.54 mm contact pitch,
15.24 mm DIP row pitch, 10 mm MCU body plus pads, socket opening, underside
standoff and extraction loads. Select J1/J2 footprints from supplier drawings.

The Preci-Dip 801 SMD female family is worth investigating; it is not yet a
selected 24-contact CPU socket. The 800...30-001101 SMD male family uses a
**0.76 mm mating pin**, so it must not be assumed to fit a motherboard DIP socket.
Likewise, a 350-series THT part is not an SMT footprint. Modified THT tails remain
an experimental alternative requiring fracture and retention tests.
[Preci-Dip connector catalogue](https://precidip.com/wp-content/uploads/2024/10/CATALOG-PCBCONNECTORS.pdf)

## Open items and next acceptance checks

| Item | Required resolution |
| --- | --- |
| Shared target-power assumption | Measure local 3.3 V startup/decay against bus drive; validate the accepted common-5-V assumption. Separate isolation is not selected in this revision. |
| BAT54 voltage/timing | Forward-voltage margin accepted by the user, supported by nominal SPICE evidence. Measure edge delay for PIO timing. |
| Independent output inhibit | JP1 only feeds firmware permission. It does not disable pad drivers. An independent inhibit compatible with passive capture is still required; tying MCU RUN low would disable the analyzer too. BUS_ARM_REQUEST reserves a pin for that circuit. |
| Passive loading | Check reset pull-downs, input leakage, added capacitance, stubs and timing on a fixture and a known-good target. |
| Target output compatibility | Check each motherboard input threshold, pull-up/loading and aggregate MCU current; 3.3 V is not universally compatible with every 5 V input. |
| RESET/HALT | Implement the documented input-enabled, latch-LOW/output-enable sequence; check target pull-up current and external reset/error semantics. |
| Timing | Write and assemble PIO programs; validate cross-block records, DTACK/VPA/E, resistor/clamp BERR, timeouts and two-wire arbitration. |
| Mechanical/BOM completion | Select actual top/bottom contacts and pad geometry; report clearance, insertion strength and cost before routing. |

The missing independent output interlock has a visible `TBD_` BOM row. The
shared-power assumption and accepted clamp margin are recorded on the single
A3 schematic and in this review. ERC cannot validate those requirements or operating margins. The
current circuit remains a review/bench prototype, without a fabrication release.

## Sources and attribution

Sources were consulted on 2026-11-09. Raspberry Pi's downloaded RP2350B Minimal
archive is R4-S1, with schematic date 2026-07-03. Its MIT notice is retained in
[kicad/reference](../kicad/reference/rp2350-minimal.LICENSE.txt). The inductor footprint was extracted from that board; instance-specific board
data and external 3D model references were removed. Switches now use the standard
KiCad TS-1088 footprint, checked against the selected XUNPU two-pad drawing. These remain subject to placement
and supplier-drawing review. Standard symbols derive from the installed KiCad
10.0.5 libraries, under KiCad's [library license and exception](https://www.kicad.org/libraries/license/).
