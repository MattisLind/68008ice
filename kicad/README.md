# RP2354B / MC68008 schematic starter

Open [rp2350_68008_ice.kicad_pro](rp2350_68008_ice.kicad_pro) in **KiCad 10**,
then its schematic. Everything is on **one landscape A3 sheet**, with local
signal labels and real power symbols. The
[single-page PDF](rp2350_68008_ice.pdf) is a review export.

| Area | Contents |
| --- | --- |
| Upper left | Pin-for-pin top socket / motherboard plug, sharing C23 bypass |
| Upper centre | RP2354B, clock/recovery, SWD, five BAT54 clamps and mode permission |
| Upper right | U5 8 MiB PSRAM, R4 chip-select pull-up and C24/C25 decoupling |
| Lower left | Supplies, MCU decoupling and rail load |
| Lower centre | USB-C, VBUS detector and data protection |

The [hardware review](../docs/hardware.md) explains mapping, component choices,
PIO constraints, budget and unresolved electrical/mechanical work. Read it before
using [BOM.csv](BOM.csv) for procurement. J1/J2/JP1 lack footprints deliberately;
they do not imply a selected mechanical design. No PCB layout is included yet.
J4 is a purchased JST-SH connector for button-free firmware uploads and debugging
with the Raspberry Pi Debug Probe. The [programming guide](../docs/programming.md)
describes probe wiring and automation.

## Mapping and regeneration

- [mc68008_pinmap.csv](mc68008_pinmap.csv): all 48 DIP pins and their MCU paths.
- [rp2354b_gpio.csv](rp2354b_gpio.csv): all 48 GPIOs, including mode, USB sense and PSRAM select.
- [rp2350_ice.kicad_sym](rp2350_ice.kicad_sym): project symbols; RP2354B uses the
  documented RP2350B-compatible pinout, and socket symbols have passive pins.
- [rp2350_ice.pretty](rp2350_ice.pretty): reference-derived
  footprint for the core inductor, with the original license in `reference/`.
- [BOM.csv](BOM.csv): engineering BOM with C-numbers, Basic/Extended class,
  assembly method and selection evidence.
- [BOM_JLCPCB.csv](BOM_JLCPCB.csv): grouped JLCPCB upload BOM, including J4 and
  excluding J1/J2 manual contacts and the JP1 PCB solder bridge.
- [parts_catalog.json](parts_catalog.json) and [JLCPCB_parts.md](JLCPCB_parts.md):
  dated catalog selections and rationale for every Extended type.

The generated sheet is editable. Circuit definitions are in
[hardware_circuit.json](../tools/hardware_circuit.json); the generator holds the
placement table. Review/save any GUI changes before regeneration, which replaces
the drawing. From the repository root:

```sh
python3 tools/build_hardware.py --overwrite
```

The generator uses Python's standard library and installed KiCad 10 symbols.
Set `KICAD_SYMBOL_DIR` if they are outside the detected platform directories.
Keep mapping, catalog, generator, generated schematic and BOM changes together.

The saved drawing includes manual layout improvements. To update BOMs and the
GPIO table without replacing that drawing, use:

```sh
python3 tools/build_hardware.py --bom-only
```

The five single **R+O BAT54X / C19627026** clamps use SOD-523 footprints and plain
two-pin Schottky symbols beside the MCU. Pad 1 is cathode, pad 2 is anode;
the old SOT-23 symbol and NC terminal are removed. U5
**APS6404L-3SQR-ZR / C3040877** uses GPIO47 for QMI CS1 and
shares the dedicated QSPI clock/data pads with the 2 MB in-package flash.
USB_PRESENT_N moves to GPIO46 and BUS_ARM_REQUEST is removed. R4 is repurposed
as a 1 kΩ CS pull-up; R5 remains MODE_PERMIT's 10 kΩ pull-down. C24/C25 reuse
existing 4.7 µF / 100 nF parts. The rest of the saved layout is preserved.

J4 is **JST SM03B-SRSS-TB(LF)(SN) / C160403**, a side-entry, 3-pin, 1.0 mm
pitch SMT connector matching the Raspberry Pi Debug Probe's supplied cable.
Contacts are **1 SWCLK, 2 GND, 3 SWDIO**, with grounded mounting tabs and no
power/reference contact. Its standard KiCad footprint is assigned; plug access
and clearance from the CPU/socket remain placement checks.

The PSRAM uses KiCad's standard USON footprint with a 0.2 × 1.6 mm centre
paddle, left unconnected. Source, startup, power and timing details are in the
[PSRAM hardware notes](../docs/hardware.md#8-mib-psram). Firmware must select
GPIO47 explicitly; automatic CS discovery could drive target address lines.

## Checks and exports

With `kicad-cli` on PATH, from the repository root:

```sh
mkdir -p build/hardware
kicad-cli version
kicad-cli sch export netlist --format kicadxml \
  -o build/hardware/netlist.xml kicad/rp2350_68008_ice.kicad_sch
python3 tools/check_hardware.py build/hardware/netlist.xml
python3 tools/check_clamp_budget.py
kicad-cli sch erc --format json \
  -o build/hardware/erc.json kicad/rp2350_68008_ice.kicad_sch
kicad-cli sch export pdf \
  -o kicad/rp2350_68008_ice.pdf kicad/rp2350_68008_ice.kicad_sch
```

Validation with KiCad **10.0.5**: connectivity/BOM checks pass; ERC reports **zero
errors and zero warnings**. No ERC exclusions were added. The local inductor,
two-pad switch and three-pin JST-SH footprints were checked separately.
See [validation.md](validation.md). PCB DRC and mechanical measurements await an
actual placement project; shared-power transitions, interlock and PIO timing
remain open even where ERC is clear. The user accepts the BAT54 forward-voltage
margin, supported by the [nominal SPICE results](../simulations/bat54/README.md).
