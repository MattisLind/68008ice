# Single-cycle bench evidence, 2026-11-17

Board 1 (`F3217B63D8F6A7A5`, `/dev/cu.usbmodem24401`) generates the bus;
board 2 (`AC740FAC748891BF`, `/dev/cu.usbmodem24301`) simultaneously serves
1024-byte RAM and samples GPIO0..31 at 150 MHz. Both installed dispatcher-0.4
images were programmed and readback verified. Installed ELF hashes and tool
versions are in [report.json](report.json), with the [build log](build.txt).

Each of `write`, `read`, `write-delayed`, `write-early` and `read-late` has:

- `.vcd` and `.bin`: actual 4096-sample acquisition, with CRC in `.json`.
- `.report.json`: sampled edge indexes, phase widths, wait inference and both
  boards' completion/status records.
- `.memory.bin`: all 1024 bytes after the transaction, verified against the
  expected write of `0x5a` at offset zero, or unchanged zero RAM for a read.
- `.svg`: a zoom of the acquired samples around DS falling.

All five captures have FDEBUG zero. DS is at index 2048 for middle, 409 for
early and 3686 for late. The delayed write waited 2.5 seconds before source GO,
exercising endless DMA beyond a finite 28-bit count. Phase widths show one or
two responder wait states; 625/750 ns total cycle lengths are inferred from
the nominal generator phases. There is no captured CLK or independent clock
reference, and these captures do not demonstrate a 500 ns no-wait transaction.

[host-tests.txt](host-tests.txt) records 39 passing host tests.
[dispatcher-check.json](dispatcher-check.json) records 11 passing hardware
checks on the same firmware. The `timeout` capture was acquired earlier on
board 1 during bring-up: 100 ms without a trigger, 4096 samples, FDEBUG zero.
The final receiver build also passed that timeout check; the earlier artifact
is retained rather than presented as an acquisition from the final build.

Build with `make dispatcher-build`; run host checks with
`python3 -m unittest discover -s tools/tests -v`. Use the fixture wiring and
capture command in [single-cycle-timing.md](../../single-cycle-timing.md).
Omit `--allow-writes` for reads; add `--delay-ms 2500` for the delayed case,
or `--position early` / `--position late` for the other positions. Captures
pause receiver USB until trigger completion or the bounded timeout.
