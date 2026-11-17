# ABC1600 keyboard wait, 2026-11-17

Verified on the two connected Core2350B boards, using the uploaded unmodified
16 KiB ABC1600 ROM. CPU serial F3217B63D8F6A7A5; memory AC740FAC748891BF.

- Host production CPU reaches keyboard wait after 552468 instructions.
- Independent Musashi reaches the same registers and RAM/VRAM contents.
  Its instruction count differs because the functional video clock advances
  with bus accesses. Peripheral behavior is shared for this comparison;
  this does not validate all peripherals against a running MAME machine.
- Hardware runs 600000 instructions, pauses at PC `$055C`, D0 `$54`:
  DART B receive character available is clear.
- All final D/A registers, PC, SR, read/write counts match host execution.
- 2636082 completed bus cycles: 2333634 reads, 302448 writes.
- Last 4096 DS-release samples match host addresses, data and direction.
- Zero bus errors, unsupported I/O accesses, function-code errors or PIO errors.
- Host verifies 100 consecutive keyboard polls and watchdog reads.
- 87274 independent Musashi instruction cases and 17133 MAME MAC accesses pass.
- 66 repository unit tests pass. Both dispatcher firmware builds pass.

Reproduce host validation from the repository root:

```sh
python3 tools/cpu_reference.py --prepare
python3 tools/abc1600_model.py
python3 tools/abc1600_boot.py
python3 -m unittest discover -s tools/tests
make dispatcher-build
```

After programming the two fixture boards with their respective dispatcher
images, run `python3 docs/validation/abc1600-keyboard-2026-11-17/run_fixture.py`
from the repository root. This script explicitly drives the existing 3.3 V
fixture, uploads ROM, permits its writes, asserts RESET and executes it.
Its fixed port names identify the fixture; inspect them before reuse.
Outputs are under `build/abc1600-boot/`.

`keyboard-wait.vcd` and `.bin` are the actual bus capture; `.json` describes
the capture. `bench-report.json` contains hardware registers and counters.
`host-report.json`, `instruction-report.json` and `mac-report.json` record host
checks. `capture-check.json` records the bytewise host/capture comparison.
Only the final bus window was retained; this is not a capture of every cycle.
The bounded instruction buffer retains only the first 128 snapshots.

Build tools: Pico SDK 2.3.1 / GCC 13.2.1 in the repository Docker image;
host Python 3.14.8 / Apple clang 21. The ROM SHA256 and pinned Musashi/MAME
revisions are recorded in the JSON reports. Mover PROM behavior, serial
timing, persistent RTC/NVRAM, interrupts, exceptions and a full machine boot
are outside this result. The CPU is paused by its budget, with RESET/HALT
released and bus outputs released after completion.
