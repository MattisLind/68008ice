# Starter validation — revision 0.4, 2026-11-10

Tools: KiCad CLI 10.0.5, Python 3.14.8. Commands are listed in [README.md](README.md).

| Check | Result |
| --- | --- |
| Native project/schematic load and PDF export | Passed; one landscape A3 sheet, no child sheets |
| Saved-layout preservation | Diode centres/leads and unrelated drawing objects retained; J4 conversion changes only its symbol, former 3V3 branch, grounded mounting tabs and caption |
| Motorola Fig.11-5 DIP numbering | All 48 CSV entries match independent transcription |
| Top-to-bottom connectivity | All 48 like-numbered contacts share the correct net |
| Direct MCU connections | 40 connections match CSV and package GPIO names |
| Protected connections | Five distinct 2.2 kΩ paths; five R+O BAT54X / C19627026 SOD-523 parts, pad 2 anodes at MCU nodes, pad 1 cathodes at 3.3 V; no third pin |
| Signal labels | Local labels throughout; unlabelled physical wires checked by circuit-source net membership |
| Rail load | R19/R20 each 1 kΩ, in parallel from 3.3 V to ground |
| GPIO allocation | 48 distinct GPIOs and package pads; 45 bus signals + 3 auxiliary, with roles documented in CSV notes |
| Shared connector bypass | One C23 100 nF / C1525 across J1/J2 common 5 V/GND; C4 and C5 remain on separate regulator rails |
| MCU supply and dedicated interfaces | Netlist checks pass |
| PSRAM data/clock/select | U5 SIO0–3 and SCLK match dedicated QSPI pads; CS1 uses GPIO47 and stays separate from flash CS0 |
| PSRAM power/startup bias | R4 1 kΩ to 3.3 V; C24 4.7 µF and C25 100 nF; existing Basic SKUs reused; electrical startup/decoupling still requires bench checks |
| Auxiliary reassignment | GPIO45 MODE_PERMIT with R5 pull-down; GPIO46 USB_PRESENT_N; GPIO47 PSRAM_CS_N; arm reservation removed |
| USB data, VBUS separation and MCU/target reset separation | Netlist checks pass |
| SWD connector | J4 JST-SH C160403: 1 SWCLK, 2 GND, 3 SWDIO; both MP pads grounded; no power contact; 1.0 mm pitch footprint checked |
| Schematic/BOM correspondence | All 63 instantiated positions match values and footprints |
| Purchasing fields | All 60 SMT positions carry matching catalog C-numbers, library class and assembly method in schematic/BOM |
| JLCPCB upload BOM | 22 grouped catalog numbers, including J4; J1/J2 manual contacts and JP1 PCB bridge excluded |
| Catalog sourcing | 12 Basic / 10 Extended types; PSRAM C3040877, SOD-523 clamp C19627026 and JST-SH C160403 checked 2026-11-10, earlier choices retain their dates; all selected as SMT assembly |
| Footprints | Reference-derived inductor and two-pad switch checked; USON dimensions/paddle checked; SOD-523 K/A mapping verified against R+O polarity marking; JST-SH pin numbering and grounded mounting tabs checked against Raspberry Pi/JST drawings |
| ERC | 0 errors, 0 warnings; no exclusions |
| DC clamp-current budget | Conservative 4.628 mA injection bound versus 6.404 mA minimum rail load |
| Clamp forward-voltage decision | Margin risk explicitly accepted by the user; retain BAT54 |
| Nominal SPICE, forced 0.7727 mA / 25°C | Vf = 0.2003 V with manufacturer BAT54 proxy model |
| Nominal SPICE, full 5 V / 2.2 kΩ / 3.3 V circuit | If = 0.6834 mA, Vf = 0.1965 V at 25°C |
| PDF visual inspection | Complete A3 sheet inspected; normal symbol sizes retained |
| PCB/mechanical/DRC | Not performed: no PCB yet |
| Electrical, PIO timing, physical target behavior | Not performed: no hardware/firmware yet |

The final export resolves the supplied project library with no ERC warnings.
The local `fp-lib-table` and inductor `.kicad_mod` file are supplied; pad numbers
were also checked independently. No ERC severity changes or exclusions were added.

`BOM.csv` includes one `NOT_IMPLEMENTED_NOT_COSTED` row for independent output
inhibit. It is not a schematic instance and is excluded from both the component
correspondence check and the JLCPCB upload BOM. The previous separate power
isolation placeholder was removed following the accepted common target-power
prototype assumption; local supply ramps remain a bench-validation condition.

The grouped upload BOM lists selected catalog items, without a stock reservation
or price quotation. Layout, component positions/CPL and fabrication release are
not supplied yet.

Run the current-budget calculation separately:

```sh
python3 tools/check_clamp_budget.py
```

A passing current budget is not a proof of safe startup. The script records the
accepted forward-voltage assumption. The [SPICE report](../simulations/bat54/README.md)
contains the model provenance, temperature sweep and reproducible results. Netlist
checks establish connectivity and purchasing consistency; they do not establish
connector fit, bus timing or manufacturability.
