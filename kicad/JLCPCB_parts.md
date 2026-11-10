# JLCPCB selections — through 2026-11-10

Basic/Extended and SMT assembly were checked on JLCPCB product pages; each catalog entry carries its verification date. Stock and prices must be checked when ordering.
J1/J2 are manual assemblies and JP1 is a PCB feature, excluded from the JLCPCB upload BOM. J4 is a purchased JST-SH SMT connector included in the BOM.
The independent output interlock remains unimplemented and uncosted.

| LCSC | Library | MPN | Qty | References | Selection rationale |
| --- | --- | --- | --- | --- | --- |
| [C11702](https://jlcpcb.com/partdetail/0402WGF1001TCE/C11702) | Basic | 0402WGF1001TCE | 5 | R1, R2, R4, R19, R20 | Basic: share crystal/BOOTSEL series, two rail loads and strong PSRAM CS1 pull-up. |
| [C1525](https://jlcpcb.com/partdetail/CL05B104KO5NNNC/C1525) | Basic | CL05B104KO5NNNC | 16 | C9, C10, C11, C12, C13, C14, C15, C16, C17, C18, C19, C20, C21, C22, C23, C25 | Basic common MCU, PSRAM and connector high-frequency bypass part. |
| [C1548](https://jlcpcb.com/partdetail/0402CG150J500NT/C1548) | Basic | 0402CG150J500NT | 2 | C1, C2 | Basic C0G crystal load capacitors; both use the same part. |
| [C15850](https://jlcpcb.com/partdetail/CL21A106KAYNNNE/C15850) | Basic | CL21A106KAYNNNE | 2 | C4, C5 | Basic 25V X5R for LDO input/output; same exact part. |
| [C160403](https://jlcpcb.com/partdetail/JST-SM03B_SRSS_TB_LF_SN/C160403) | Extended | SM03B-SRSS-TB(LF)(SN) | 1 | J4 | Extended SMT genuine JST-SH 3-pin 1.0mm-pitch side-entry header, matching the Raspberry Pi Debug Probe supplied cable. Pins 1 SWCLK, 2 GND, 3 SWDIO; metal mounting pads to GND. Selected instead of probe pads; no qualified Basic mating-equivalent was established. Verify board-end cable access and CPU/socket clearance during placement. |
| [C19627026](https://jlcpcb.com/partdetail/BAT54X/C19627026) | Extended | BAT54X | 5 | D1, D2, D3, D4, D5 | User-selected Extended SMT R+O BAT54X / C19627026, SOD-523, 30V/200mA. Five identical upper clamps; pad 1 cathode to 3V3, pad 2 anode at the protected MCU node. Retain the accepted sub-mA forward-voltage margin and nominal proxy-model SPICE evidence. |
| [C20625731](https://jlcpcb.com/partdetail/ABM8-272-T3/C20625731) | Extended | ABM8-272-T3 | 1 | Y1 | Extended: reference 12MHz, 10pF, 50-ohm ESR part; Basic C9002 is 20pF/80-ohm and is not a drop-in replacement. |
| [C23733](https://jlcpcb.com/partdetail/CL05A475MP5NRNC/C23733) | Basic | CL05A475MP5NRNC | 4 | C6, C7, C8, C24 | Basic 10V X5R; share core/filter and PSRAM local bypass value; verify effective capacitance, including at least 1uF at PSRAM VDD. |
| [C25100](https://jlcpcb.com/partdetail/0402WGF270JTCE/C25100) | Extended | 0402WGF270JTCE | 2 | R9, R10 | Extended: keep RP2350 reference USB series termination value; 0603 candidate C25190 is also Extended. Share the exact SKU on D+ and D-. |
| [C25105](https://jlcpcb.com/partdetail/0402WGF330JTCE/C25105) | Basic | 0402WGF330JTCE | 1 | R6 | Basic reference VREG_AVDD filter value; no fee saving justifies changing it to 27 ohm. |
| [C25741](https://jlcpcb.com/partdetail/0402WGF1003TCE/C25741) | Basic | 0402WGF1003TCE | 1 | R12 | VBUS gate pull-down: 10:1 ratio with existing 10k maintains MOSFET gate drive. |
| [C25744](https://jlcpcb.com/partdetail/0402WGF1002TCE/C25744) | Basic | 0402WGF1002TCE | 4 | R3, R5, R11, R13 | Share RUN pull-up, MODE_PERMIT pull-down, VBUS gate series and detector pull-up. |
| [C25879](https://jlcpcb.com/partdetail/0402WGF2201TCE/C25879) | Basic | 0402WGF2201TCE | 5 | R14, R15, R16, R17, R18 | Common value for all five clamp series resistors. |
| [C25905](https://jlcpcb.com/partdetail/0402WGF5101TCE/C25905) | Basic | 0402WGF5101TCE | 2 | R7, R8 | Separate USB-C CC Rd resistors; preserve required value. |
| [C3020560](https://jlcpcb.com/partdetail/USB4105-GF-A/C3020560) | Extended | USB4105-GF-A | 1 | J3 | Extended: retain documented USB-C SMT-contact connector/footprint; alternative C165948 is also Extended. Shell stakes require placement review. |
| [C3040877](https://jlcpcb.com/partdetail/APMemory-APS6404L_3SQRZR/C3040877) | Extended | APS6404L-3SQR-ZR | 1 | U5 | Extended SMT: 64 Mbit / 8 MiB, 2.7-3.6 V SPI/QPI PSRAM; compact 3x2 mm USON package for the DIP adapter. No suitable Basic 8 MiB PSRAM was identified. Shared QSPI data/clock and separate GPIO47 QMI CS1; reuse existing capacitor and pull-up resistor SKUs. Stock/prices require order-time verification. |
| [C39843328](https://jlcpcb.com/partdetail/RP2354B/C39843328) | Extended | RP2354B | 1 | U1 | Extended: required 48-GPIO MCU with in-package flash; confirm supplied silicon stepping. |
| [C404027](https://jlcpcb.com/partdetail/TLV75533PDBVR/C404027) | Extended | TLV75533PDBVR | 1 | U2 | Extended: retain compact 500mA, 1%-accuracy, ceramic-stable reference choice. No qualified Basic drop-in was established in this review; one 3.3V regulator type is used. |
| [C42411119](https://jlcpcb.com/partdetail/AOTA-B201610S3R3-101-T/C42411119) | Extended | AOTA-B201610S3R3-101-T | 1 | L1 | Extended: preserve validated reference core-regulator inductor, current ratings and orientation mark; generic same inductance is insufficient. |
| [C720477](https://jlcpcb.com/partdetail/TS-1088-AR02016/C720477) | Basic | TS-1088-AR02016 | 2 | SW1, SW2 | Basic: replace both Wurth buttons with the same two-pad SMT switch. |
| [C8545](https://jlcpcb.com/partdetail/2N7002/C8545) | Basic | 2N7002 | 1 | Q1 | Basic 2N7002 for isolated VBUS presence detection. |
| [C94934](https://jlcpcb.com/partdetail/TPD2EUSB30ADRTR/C94934) | Extended | TPD2EUSB30ADRTR | 1 | U4 | Extended: low-capacitance ground-referenced ESD array avoids an extra clamp path to the supply. Alternative C7519 is also Extended and not equivalent. |
