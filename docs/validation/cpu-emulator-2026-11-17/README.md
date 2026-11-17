# CPU reset/vector/STOP verification, 2026-11-17

Both standalone Core2350B boards were built and USB-programmed with dispatcher
0.5.0. `picotool load -u -v -x` reported successful flash verification for each
matching serial. Native USB HELLO reported dispatcher-0.5; core 0 serves USB,
core 1 executes the loaded application, and each board reports 8388608 bytes
of PSRAM. No adapter or valuable target was used.

| Role | Serial | CDC port | SWD instance |
| --- | --- | --- | --- |
| CPU / generator | `F3217B63D8F6A7A5` | `/dev/cu.usbmodem24401` | 1 |
| Memory / analyzer | `AC740FAC748891BF` | `/dev/cu.usbmodem24301` | 2 |

The existing same-number GPIO0–44 wires and common ground were retained.
FC0–2 use GPIO32–34, fixture RESET GPIO35, HALT GPIO38 and BERR GPIO40.
RESET/HALT assertions use fixed LOW latches and output enable; release returns
the pins to inputs. The CPU required an observed RESET/HALT pulse before
fetching vectors. Bench pulls on GPIO35/38/40 hold them inactive after cleanup.

| Check | Observed result |
| --- | --- |
| Builds | Both SWD instances build with `-Wall -Wextra -Werror` |
| Host tests | 48 passed, including eight portable C CPU cases and corrupted physical-trace rejection |
| Reset → STOP | Twelve PIO-captured reads, SSP `$400`, PC `$104`, SR `$2700`, one instruction, no writes or HALT assertion |
| Reset → NOP → STOP | Fourteen reads, PC `$106`, two instructions, no HALT assertion |
| Reset-vector BERR | Fault at address zero, no completed CPU reads/instructions, CPU halted, memory board sampled HALT LOW |
| RESET timing | Commanded reset release 1000–1001 us after assertion in the saved cases |
| Function codes | FC=6 at all decoded cycles; zero memory-side FC errors |
| State acquisition | Zero receiver FDEBUG; all normal captured address/direction/data bytes match RAM |
| Missing RESET | 100 ms overall timeout, error 2, zero bus reads |
| Abort while waiting RESET | Error 7, zero bus reads, outputs released |
| Invalid CPU drive flags | Missing drive and memory-only flag rejected before scheduling |
| Existing bus fixture | All 11 cases passed, including 65536 records, RAM verification, trigger positions, partial stops, invalid requests and unmapped timeout |
| Shared PIO timing | Read and write 4096-sample captures at 150 MS/s passed with exact midpoint trigger and zero sampling stalls |

In the reset-fault case HALT LOW was observed 1143 us after reset start;
this is a software polling observation. The bounded test asserts HALT for up
to 1 ms then releases it during job cleanup. It does not implement an
indefinitely halted replacement CPU. The GPIO0–31 state trace does not record
upper-bank sidebands synchronously; HALT/FC evidence is in the separate
memory-side report. The normal STOP trace contains no physical HALT assertion.

The cycle-phase checks reused the existing fast-memory fixture; their timing
is distinct from the software-serviced boot-memory path. No CPU throughput,
instruction-cycle accuracy or full instruction compatibility was established.

## Reproduce

The Docker toolchain is `68008ice-pico:2.3.1`: Pico SDK 2.3.1, GCC 13.2.1,
CMake 3.28.3 and Ninja 1.11.1, with the existing Debug configuration.
USB programming used picotool 2.3.1. Builds and complete logs are in
`build/cpu-emulator-build.log`, `build/cpu-host-tests.log`,
`build/cpu-check.log`, `build/cpu-check-halt.log`,
`build/cpu-bus-regression.log` and `build/cpu-timing-{read,write}.log`.

```sh
make dispatcher-build
python3 -m unittest discover -s tools/tests -v
python3 tools/cpu_check.py --cpu /dev/cu.usbmodem24401 \
  --memory /dev/cu.usbmodem24301 --allow-drive
python3 tools/cpu_check.py --cpu /dev/cu.usbmodem24401 \
  --memory /dev/cu.usbmodem24301 --allow-drive --halt-test \
  --output build/cpu-check-halt
python3 tools/bus_check.py --generator /dev/cu.usbmodem24401 \
  --receiver /dev/cu.usbmodem24301 --full --output build/cpu-bus-regression
python3 tools/bus_timing.py --generator /dev/cu.usbmodem24401 \
  --receiver /dev/cu.usbmodem24301 --allow-drive \
  --output build/cpu-bus-regression/timing-read.vcd
python3 tools/bus_timing.py --generator /dev/cu.usbmodem24401 \
  --receiver /dev/cu.usbmodem24301 --allow-drive --allow-writes \
  --output build/cpu-bus-regression/timing-write.vcd
```

Generated CPU module files are
`build/multidrop/{1,2}/app_cpu_emulator.{elf,bin,app}`; both dispatchers have
`.elf`, `.bin` and `.uf2` outputs in those same directories. The module's
46-byte packaged entrypoint calls the resident CPU implementation through
ABI 2, following the existing bus-app structure. File hashes and sizes are
retained in [artifacts.json](artifacts.json).

Retained results:

- [CPU/register/reset/HALT report](report.json)
- [STOP byte trace](stop.csv), [VCD](stop.vcd), [raw](stop.bin),
  [capture metadata](stop.json), [memory image](stop-memory.bin)
- [NOP/STOP VCD](nop-stop.vcd) and [reset-fault VCD](reset-fault.vcd)
- [Host test output](host-tests.txt) and [11-case bus regression](bus-regression.json)
- [Read phase timing](timing-read.report.json) and [write phase timing](timing-write.report.json)

The MCL68+ source/license review and limitations are in
[cpu-emulator.md](../../cpu-emulator.md). Full opcode support, exception and
interrupt handling, writes, arbitration, prefetch, STOP wakeup and target-clock
synchronization remain future milestones. Only the standalone 3.3 V fixture
was validated. No hardware design, PCB or schematic was changed.
