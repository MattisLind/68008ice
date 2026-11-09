# RP2354B / MC68008 schematic starter

Open [rp2350_68008_ice.kicad_pro](rp2350_68008_ice.kicad_pro) in **KiCad 10**,
then its schematic. Everything is on **one landscape A3 sheet**, with local
signal labels and real power symbols. The
[single-page PDF](rp2350_68008_ice.pdf) is a review export.

| Area | Contents |
| --- | --- |
| Upper left | Pin-for-pin top socket / motherboard plug, sharing C23 bypass |
| Upper centre | RP2354B and GPIO allocation |
| Upper right | Five 2.2 kΩ/BAT54 clamps, rail load, clock and recovery |
| Lower left/centre | Supplies, decoupling, VBUS detector and mode permission |
| Lower right | USB-C and data protection |

The [hardware review](../docs/hardware.md) explains mapping, component choices,
PIO constraints, budget and unresolved electrical/mechanical work. Read it before
using [BOM.csv](BOM.csv) for procurement. J1/J2/J4/JP1 lack footprints deliberately;
they do not imply a selected mechanical design. No PCB layout is included yet.
J4's dedicated SWD signals support button-free firmware uploads and debugging;
the [programming guide](../docs/programming.md) describes probe wiring and automation.

## Mapping and regeneration

- [mc68008_pinmap.csv](mc68008_pinmap.csv): all 48 DIP pins and their MCU paths.
- [rp2354b_gpio.csv](rp2354b_gpio.csv): all 48 GPIOs, including mode/arm/USB sense.
- [rp2350_ice.kicad_sym](rp2350_ice.kicad_sym): project symbols; RP2354B uses the
  documented RP2350B-compatible pinout, and socket symbols have passive pins.
- [rp2350_ice.pretty](rp2350_ice.pretty): reference-derived
  footprint for the core inductor, with the original license in `reference/`.
- [BOM.csv](BOM.csv): engineering BOM with C-numbers, Basic/Extended class,
  assembly method and selection evidence.
- [BOM_JLCPCB.csv](BOM_JLCPCB.csv): grouped JLCPCB upload BOM, excluding J1/J2
  manual contacts and J4/JP1 PCB-only features.
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

The five single BAT54 / C8590 clamps replace the earlier dual packages. R14–R18
and D1–D5 are grouped in the upper right; BERR/BR's MCU labels are restored. Other
saved component positions, wiring and field layouts are retained.

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
errors and zero warnings**. No ERC exclusions were added. The local inductor
footprint and selected two-pad switch footprint were checked separately.
See [validation.md](validation.md). PCB DRC and mechanical measurements await an
actual placement project; shared-power transitions, interlock and PIO timing
remain open even where ERC is clear. The user accepts the BAT54 forward-voltage
margin, supported by the [nominal SPICE results](../simulations/bat54/README.md).
