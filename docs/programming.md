# Programming and debugging through SWD

The RP2354B's dedicated SWD interface, exposed at J4, supports firmware upload,
flash verification, reset/run and source-level debugging. **BOOTSEL does not need
to be pressed for normal SWD uploads.** It uses the same debug approach as a
Pico 2, with RP2350-capable OpenOCD tooling and a CMSIS-DAP probe.
[Raspberry Pi Debug Probe documentation](https://www.raspberrypi.com/documentation/microcontrollers/debug-probe.html#starting-a-debug-session)

## Hardware

Connect a Raspberry Pi Debug Probe's **D** port, or a spare Pico/Pico 2 running
Raspberry Pi's [debugprobe firmware](https://github.com/raspberrypi/debugprobe).
The probe connects to the development computer by USB. The ICE's own USB-C port
can remain connected for its normal commands and trace traffic.

| ICE J4 pad | Signal | Probe connection |
| --- | --- | --- |
| 1 | 3V3 reference | VTref sense only if the chosen probe needs it; leave open with the three-wire Raspberry Pi Debug Probe |
| 2 | GND | GND, black wire on the Raspberry Pi probe cable |
| 3 | SWCLK | SC, orange wire |
| 4 | SWDIO | SD, yellow wire |

J4 is currently four provisional pads, not the standard Raspberry Pi three-pin
JST connector pinout; use an appropriate adapter or test fixture. The physical
footprint and access clearance still need selecting during placement. SWCLK and
SWDIO use dedicated MCU pins, leaving the bus GPIO allocation intact.

Power the ICE from the motherboard, with a common probe/ICE ground. J4 pad 1 is
not a power input: do not connect a probe power-output pin to it. The Raspberry
Pi probe operates at 3.3 V logic levels and uses only clock, data and ground on
its D connector. A RUN connection is not required for the normal SWD reset/upload
workflow. BOOTSEL and the local RUN button remain available for recovery.

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
