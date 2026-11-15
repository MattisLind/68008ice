# PCB placement and mechanical assumptions

The [native PCB](../kicad/rp2350_68008_ice.kicad_pcb) is an **unrouted placement
study**, dated 2026-11-10. All 63 schematic positions have footprints and matching
pad nets. The user will adapt the provisional DIP contact construction after
checking actual parts. Open the existing project in KiCad 10 and then PCB Editor.
The [two-page placement PDF](../kicad/placement.pdf) shows the top and the actual
bottom view at 2.5× scale. It is a review drawing, not a 1:1 fit template.

![Top placement, with the access extension below the CPU](../kicad/placement-top.svg)

## Outline and contact geometry

| Measurement | Starter value |
| --- | --- |
| Total PCB length | **70.96 mm** |
| Main CPU-section width | **21.00 mm** |
| Access-tab width | **27.00 mm** |
| Provisional socket body | **60.96 × 17.72 mm** |
| Extension past socket body at the connector end | **9.50 mm** |
| Extra PCB beyond the opposite socket end | **0.50 mm** |
| Total length added to the socket body | **10.00 mm** |
| Mating-contact pattern | 2 × 24, **2.54 mm** pitch, **15.24 mm** row spacing |
| First-to-last contact centre distance | **58.42 mm** |
| SMT land dimensions | **2.00 mm outward × 1.30 mm along the row** |
| SMT land row-centre spacing | **17.24 mm**, offset 1.00 mm outward per row |
| Clear copper corridor between the SMT lands | **15.24 mm** |
| QFN body / courtyard span | 10.00 mm / 11.20 mm |
| QFN courtyard to DIP land inner edges, each side | **2.02 mm** |
| Main-board edge to outer DIP copper, each side | **0.88 mm** |
| Proposed PCB thickness | **1.60 mm**, subject to stackup/fit review |

The documented socket envelope is from CviLux **CS0748D1A00**, catalogue page 5.
It is a dimensional reference, not a selected or qualified bendable socket.
The user requested a normal DIP-48 socket with outward-bent tails; the underside
will probably use a similar socket with male-to-male contacts. Actual contact
style, formed lead length, bend radius, height and retention remain to be chosen.
[CviLux drawing](https://www.cvilux.com/uploads/download/catalog/2025%20I-CS.pdf)

The board centre at X=100, Y=100 mm is the centre of the DIP mating pattern.
The outline runs from Y=69.02 to 139.98 mm. The access tab begins near Y=131 mm;
0.5 mm chamfers remove sharp convex corners. The tab is wider to fit both cable
connectors, two buttons and the mode bridge in the requested length extension.
Check its 3 mm overhang on each side of the main section against the motherboard.

## Provisional hand-solder footprints

- J1: `rp2350_ice:DIP48_BentTail_Top` on F.Cu.
- J2: `rp2350_ice:DIP48_BentTail_Bottom_Mirrored` on B.Cu.
- JP1: `rp2350_ice:SolderBridge_2_Open_HandSolder`, two 1 × 1 mm pads with a
  0.30 mm open gap. It remains a solder bridge, not a purchased pin header.

The DIP footprints have **surface copper and mask openings only: no drilled
holes and no stencil paste**. The inner land edges stop at the original mating
row centre lines. Lead forming extends outward, preserving the centre for MCU
fanout and support circuits. Drawn pin-centre reference lines are distinct from
the outward-offset solder lands.

Opposite-face pads are separate copper until routed; sharing X/Y and a net name
does not connect them through the laminate. Reserve a through via and short
traces for every top/bottom pair. Tented vias between adjacent lands can keep
these pass-through connections out of the central fanout corridor. They are
not placed or routed in this starter.

J1/J2 pin numbers coincide in PCB coordinates: viewed from above, pin 1 is at
the upper left, pin 24 lower left, pin 25 lower right and pin 48 upper right.
Looking from below reverses left/right. **The bottom library definition already
compensates for the flip**. The saved J2 is on B.Cu at a native angle of 180°
after KiCad's left/right flip; do not change that angle just to match J1's 0°.
The checker verifies every numbered pad's X/Y and net independently. Both
connector footprints are locked; move them together when adapting the geometry.

The DIP courtyards bound the solder lands and hand-solder access. They do **not**
claim that the whole socket housing can overlap components. The full body is
shown on F.Fab/B.Fab; plastic side rails, end bars and any centre webs require a
separate height/shape check. No manufacturer-approved SMT footprint is claimed.

## Height and mounting checks

```text
                 optional real MC68008
             ┌─────────────────────────┐
             └─┬─────────────────────┬─┘
               female DIP socket / frame
                │                   │
      outward ──┘  top components    └── outward solder feet
    ═════════════════ 1.6 mm PCB ═════════════════
      outward ──┐ bottom components  ┌── outward solder feet
                │ underside adapter │
                │ + male-male pins  │   construction provisional
                ↓                   ↓
             motherboard's existing socket
```

Before fixing this mechanical design, measure the actual socket's open window,
web positions and underside. Plastic crossing over the MCU, regulator or other
parts needs a standoff greater than the fitted component height plus assembly
clearance; a flat web resting on the PCB will collide with those components.
Also measure male-pin diameter, usable insertion length and clearance to
motherboard components. No vertical fit is established by the 2D courtyard check.

Form a spare connector in a jig and compare it against the lands before ordering
the PCB. Inspect contact movement/fracture and solder-foot coplanarity, then test
insertion/extraction forces. Support the assembly during CPU removal; the solder
joints alone have not been qualified for those loads. Do not use an unmodified
female socket as a male motherboard plug without the intended male contacts.

## Placement and access

USB-C J3 and JST-SH SWD J4 face the extended end. BOOTSEL SW1, RUN SW2 and JP1
are on the same tab, beyond the provisional CPU/socket envelope. J3's library
PCB-edge line coincides with the end of Edge.Cuts. The SWD receptacle is slightly
inset. Check the actual plug housings, finger/iron access and cable bend space.

U1 is central and rotated 180° so its USB/QSPI/regulator edge faces the access
end. U5 is nearby on shared QSPI. The crystal, regulator and local supplies are
grouped around the MCU; the USB series resistors sit near the MCU, and the ESD
part is towards J3. D1–D5/R14–R18 are on the bottom near the protected GPIOs.
C6/C19/C21/C23 are also on the bottom. This makes **46 purchased SMT placements
on top and 14 underneath**. J1/J2 are hand fitted, and JP1 is board copper.
This is a two-sided assembly and requires underside component/adapter clearance.

These positions establish physical space, not final regulator/QSPI fanout or
decoupling loops. Review power-loop routing against Raspberry Pi's Minimal
reference, maintain an exposed-pad ground/via area, and adjust before routing.
The independent output interlock remains an unimplemented circuit item, so this
is not a complete fabrication layout.

## Four-layer stack and routing setup

| Layer | Role | Adjacent provisional dielectric |
| --- | --- | --- |
| L1 F.Cu | Components and signals | 0.18 mm FR4 to L2 |
| L2 In1.Cu, named GND | Continuous ground plane | 1.10 mm core to L3 |
| L3 In2.Cu, named 3V3 | Continuous 3.3 V plane | 0.18 mm FR4 to L4 |
| L4 B.Cu | Components and signals | — |

Four 35 µm copper layers plus these dielectrics total 1.60 mm excluding mask.
This is a setup assumption, not a reserved JLCPCB laminate stack. GND/+3V3 zone
outlines are assigned on their layers, currently **unfilled and unstitched**.
Add ground/power vias and return connections as routing proceeds, then refill
and inspect. The custom `.kicad_dru` file forbids tracks on the inner planes.

Top signals reference GND; bottom signals reference the 3.3 V plane. Provide
nearby GND-to-3V3 decoupling paths when signals change reference layers. Keep
the USB pair on top over GND where possible. Plane cuts and reference changes
must be reviewed during routing.

Default track/clearance is 0.15/0.15 mm, with a 0.127 mm minimum and 0.60/0.30 mm
through vias. Power tracks default to 0.40 mm. USB defaults to 0.18 mm width /
0.15 mm gap **as placeholders**; calculate the 90 Ω differential geometry from
the selected fabrication stack before treating those as impedance dimensions.
No blind, buried or microvias are planned.

## Footprint coverage and validation

All **63 positions** now have footprints, covering **17 distinct footprint IDs**.
All 60 purchased SMT positions retain their selected C-numbers. The three newly
assigned footprints are the two manual contact assemblies and the PCB bridge;
they add no purchased part. Standard KiCad 10 footprints are required alongside
the supplied project library. A per-reference coverage report is generated as
`build/hardware/footprint_audit.csv`.

`tools/check_pcb.py` verifies all pad nets/values, schematic UUID links, 48-pad
co-registration, pin order, SMT-only/no-paste DIP lands, layer count, zones and
closed outline dimensions. KiCad's schematic-parity check reports **zero
differences**. ERC reports **zero violations**. DRC still reports **244 unrouted
connections** and **four J3 hole-to-copper violations**: the standard USB
footprint measures about 0.1944 mm around its two locating holes versus the
0.20 mm rule. No DRC exclusions were added, and the footprint was not silently
altered. Review the land pattern/fabrication clearance with JLCPCB before release.
[GCT USB4105 drawing](https://gct.co/files/drawings/usb4105.pdf),
[JLCPCB capabilities](https://jlcpcb.com/capabilities/pcb-capabilities/)

There are no routed tracks or vias, and no footprint courtyard overlaps in the
current check. Plane connectivity, 3D contact fit and electrical operation remain
unverified. The placement PDF and SVG are the retained review exports; raw DRC,
ERC, audit files and reference snapshots remain disposable under `build/`.

## Reproduce checks and preserve edits

Use Python with KiCad's `pcbnew` module, for example the interpreter bundled
with KiCad on macOS, or the distribution Python with KiCad scripting on Linux:

```sh
kicad-cli sch export netlist --format kicadxml \
  -o build/hardware/netlist.xml kicad/rp2350_68008_ice.kicad_sch
python3 tools/check_hardware.py build/hardware/netlist.xml
python3 tools/check_pcb.py
kicad-cli pcb drc --format json --schematic-parity \
  -o build/hardware/layout-drc-current.json kicad/rp2350_68008_ice.kicad_pcb
```

`tools/start_pcb.py` creates a board from the exported schematic and the starter
placement table. It refuses to overwrite an existing PCB by default. Use GUI
editing for further work; `--overwrite` deliberately discards saved placement
and routing. `tools/build_hardware.py --bom-only` remains the safe way to refresh
purchasing outputs without replacing the manually edited schematic.
