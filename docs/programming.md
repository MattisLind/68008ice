# Programming and debugging through SWD

The RP2354B's dedicated SWD interface, exposed at J4, supports firmware upload,
flash verification, reset/run and source-level debugging. **BOOTSEL does not need
to be pressed for normal SWD uploads.** It uses the same debug approach as a
Pico 2, with RP2350-capable OpenOCD tooling and a CMSIS-DAP probe.
[Raspberry Pi Debug Probe documentation](https://www.raspberrypi.com/documentation/microcontrollers/debug-probe.html#starting-a-debug-session)

## Hardware

The recommended debugger is the **Raspberry Pi Debug Probe**, a CMSIS-DAP USB
probe supported by the RP2350 OpenOCD/GDB workflow. Connect its **D** port to J4
using the three-pin JST cable supplied with the probe. A spare Pico/Pico 2 running
Raspberry Pi's [debugprobe firmware](https://github.com/raspberrypi/debugprobe)
also works with suitable wiring.
The probe connects to the development computer by USB. The ICE's own USB-C port
can remain connected for its normal commands and trace traffic.

J4 is **JST SM03B-SRSS-TB(LF)(SN)**, a keyed **3-pin, 1.0 mm pitch JST-SH,
side-entry SMT connector**, selected as **JLCPCB C160403 / Extended**. Its pinout
matches the [Raspberry Pi three-pin debug connector specification](https://datasheets.raspberrypi.com/debug/debug-connector-specification.pdf).

| ICE J4 contact | Signal | Probe connection |
| --- | --- | --- |
| 1 | SWCLK | SC, orange wire |
| 2 | GND | GND, black wire on the Raspberry Pi probe cable |
| 3 | SWDIO | SD, yellow wire |

The two metal hold-down pads, identified as MP in KiCad, also connect to GND.
The standard footprint is
`Connector_JST:JST_SH_SM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal`.
The connector body is nominally 5 mm wide, 4.25 mm deep and 2.9 mm high.
Place it at an accessible board end, with room for the plug, cable and optional
upper CPU/socket. Cable insertion/bend clearance remains a placement check.
Mark the connector **SWD** on the PCB. SWCLK/SWDIO use dedicated MCU pins.
[JST drawing](https://www.jst-mfg.com/product/pdf/eng/eSH.pdf),
[JLCPCB selection](https://jlcpcb.com/partdetail/JST-SM03B_SRSS_TB_LF_SN/C160403)

Power the ICE from the motherboard, with a common probe/ICE ground. **J4 has no
power or VTref contact**; the previous four-pad layout and 3V3 reference contact
are removed. The Raspberry Pi probe uses fixed 3.3 V nominal logic and only
clock, data and ground on its D connector. A RUN connection is not required for
normal SWD reset/upload. BOOTSEL and the local RUN button remain for recovery.

If future tools require a conventional Arm connector with VTref/RUN, a keyed
2 × 5, 1.27 mm Cortex Debug header is the larger alternative; it is not fitted
in this compact design. A bare three-wire adapter is insufficient for a probe
that requires VTref sensing.

## Existing adapter compatibility

Assessment dated 2026-11-09; none of these particular adapters has been tested
against this board.

| Adapter | RP2354B use |
| --- | --- |
| ST-Link V2 with stock firmware | Not supported by the current OpenOCD path: RP2350 uses ADIv6 and the ST-Link driver explicitly rejects ADIv6 AP access. Having SWD pins alone is insufficient. |
| Altera/Intel USB-Blaster | JTAG / FPGA serial programming cable; no supported stock SWD path to J4. |
| Lattice HW-USBN-2A | FPGA/CPLD JTAG/SPI programmer; no supported stock SWD path to J4. |
| Atmel ATDH1150USB-K | ATF15xx CPLD JTAG ISP cable, not an Atmel-ICE; no supported stock SWD path to J4. |
| Microchip PICkit 3 | PIC/dsPIC ICSP programmer/debugger; no supported SWD/CMSIS-DAP path to the RP2354B. |
| Xilinx Platform Cable | FPGA JTAG/configuration cable; no supported stock SWD path to J4. |

The user confirmed that the listed Atmel adapter is the ATDH1150USB-K.
PICkit 3 uses [Microchip's ICSP interface](https://developerhelp.microchip.com/xwiki/bin/view/software-tools/programmers-and-debuggers/archive/pickit3/);
it is not one of the newer tools supporting
[CMSIS-DAP switching](https://developerhelp.microchip.com/xwiki/bin/view/software-tools/ides/extensions/cmsis-dap/).

This conclusion follows from the [RP2350 ADIv6 target configuration](https://github.com/raspberrypi/openocd/blob/rpi-common/tcl/target/rp2350.cfg)
and the [ST-Link driver's ADIv6 rejection](https://github.com/raspberrypi/openocd/blob/rpi-common/src/jtag/drivers/stlink_usb.c),
plus the manufacturers' [USB-Blaster](https://www.intel.com/content/dam/support/us/en/programmable/support-resources/bulk-container/pdfs/literature/ug/archives/ug-usb-blstr-15.1.pdf),
[Lattice cable](https://www.latticesemi.com/products/developmentboardsandkits/programmingcablesforpcs),
[ATDH1150USB](https://www.microchip.com/en-us/development-tool/atdh1150usb)
and [Platform Cable](https://www.amd.com/en/products/adaptive-socs-and-fpgas/board-accessories/hw-usb-ii-g.html)
documentation. A pin adapter alone does not translate JTAG into SWD.

Some ST-Link hardware can be converted to
[Black Magic firmware](https://black-magic.org/docs/intro/hardware/), but that is a
separate firmware conversion requiring hardware/flash-size and RP2350 build
support checks. It is not a verified reuse option here. Custom FTDI cable
adaptations likewise need their actual buffers/pin direction and software
configuration checked; the table describes normal supported use.

## Automated upload workflow

Use an OpenOCD build that includes **RP2350 support**. Raspberry Pi's Pico VS Code
extension supplies compatible OpenOCD, toolchain and GDB tools; an unrelated
older system OpenOCD installation may lack the target/flash driver.
The official [RP2350 target configuration](https://github.com/raspberrypi/openocd/blob/rpi-common/tcl/target/rp2350.cfg)
defaults to the two Cortex-M33 cores used by this project.

Once a firmware CMake target exists, a build-and-upload task can execute:

```sh
cmake --build build/firmware
openocd -f interface/cmsis-dap.cfg -f target/rp2350.cfg -c "adapter speed 5000" -c "program build/firmware/ice.elf verify reset exit"
```

`ice.elf` is an illustrative output name, not a file currently present in this
repository. The upload writes flash, verifies it, resets the MCU and starts the
program. A build task should run the second command only after the build succeeds.
This can become one `program` target or IDE action, without touching buttons or
unplugging cables. Use the ELF file for this workflow rather than copying a UF2
to a mounted drive.

For source-level debugging, build with debug information and launch OpenOCD as a
GDB server, or let the Pico VS Code extension handle the session. It can load
the program, stop at breakpoints, single-step, and inspect variables/registers.
SWD does not depend on the application's USB command interface being functional,
so it is also useful while developing or recovering that interface.

No upload has been exercised yet: there is no firmware target or attached
prototype in this repository, and `openocd`/`picotool` were not found on PATH in
the current environment. These are the documented integration steps, not a claim
of a tested build/flash command.

## USB-only option

Button-free uploads over the ICE's own USB connection are also possible when
running firmware includes the Pico SDK's compatible USB reset/stdio support:

```sh
picotool load -f -v -x build/firmware/ice.uf2
```

The force option asks cooperative firmware to enter the ROM USB loader, followed
by loading, verification and execution. It needs that reset support in the running
application; a custom USB protocol alone does not automatically provide it.
SWD remains the normal development/recovery path when the USB firmware is broken.
[Official picotool documentation](https://github.com/raspberrypi/picotool)

## ICE-specific debug behavior

Program and debug bus firmware with the bus released and the target in an
appropriate bench/passive state. Halting a Cortex-M33 core does not automatically
release output GPIOs or stop every PIO/DMA engine. Low-level bus recovery and
output inhibition must therefore be designed independently of CPU debugger
breakpoints. MCU RUN/reset and target RESET remain separate nets.
