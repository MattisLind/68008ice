# ICE dispatcher CDC protocol, version 1

USB CDC is a binary command channel. UART baud does not set USB throughput;
the host selects 115200 and preserves 1200 baud for BOOTSEL recovery. There is
no unsolicited text, prompt or log output on CDC. One host owns a command port.

## Framing and recovery

`FF 00` starts a frame, `FF 01` ends it, and `FF FF` represents one literal FF.
`FF 02` abandons an incomplete frame; it **does not stop an application**.
Any other escape abandons the frame. A new `FF 00` always starts fresh, even
inside a partial or oversized frame. Bytes outside frames are ignored.

After unescaping, all multi-byte fields are little-endian:

| Byte offset | Type | Field |
| --- | --- | --- |
| 0 | uint8 | Protocol version, 1 |
| 1 | uint8 | Command; response is command OR `0x80` |
| 2 | uint16 | Sequence number |
| 4 | uint16 | Payload length, 0..256 |
| 6 | uint16 | Status; requests must use zero |
| 8 | bytes | Payload |
| 8 + length | uint32 | IEEE/zlib CRC32 of the 8-byte header plus payload |

The maximum unescaped frame is 268 bytes; the maximum escaped frame including
delimiters is 540 bytes. No command executes before complete length, version,
request type/status and CRC validation. Bad frames are discarded silently.
The host times out and retries the identical encoded request once, using the
same sequence. Opening a client chooses a random initial uint16 sequence.

The device caches the most recent valid request's sequence/CRC and its response.
An immediate identical retry replays that response without repeating the
operation. Reusing that cached sequence with different content returns status
8. This is a one-entry replay cache, not durable transaction history; it is
cleared by reset and intervening commands replace it. Do not retry an old
operation after other commands or a reset. A timed-out command may have executed;
reconnect and inspect STATUS before deciding what to do next.

Statuses: 0 success, 1 invalid argument, 2 busy/wrong state, 3 bad image,
4 unavailable/no data, 5 unknown command, 6 internal response error,
7 drive permission missing, 8 sequence conflict. Application errors are
reported separately inside STATUS. Requests with valid framing but invalid
arguments return a response without starting a job.

## Commands

Unless stated otherwise, payload values are uint32 and success has no payload.

| ID | Command | Request | Response |
| --- | --- | --- | --- |
| 1 | HELLO | Empty | UTF-8 JSON: serial, firmware, protocol, SWD instance, actual dispatcher/worker core numbers, available PSRAM bytes, loaded app/source/code CRC |
| 2 | LIST | Empty | Two 28-byte image headers: generator then analyzer |
| 3 | LOAD | App ID, source | Validate and copy code into execution SRAM; app 1 generator / 2 analyzer; source 0 flash / 1 flash staged through PSRAM / 2 uploaded PSRAM |
| 4 | RUN | Bank, trigger GPIO, level, timeout ms, flags | Asynchronous acceptance; inspect STATUS for armed/completion |
| 5 | GO | Empty | Start an armed generator |
| 6 | STATUS | Empty | 16-word job record below |
| 7 | ABORT | Empty | Request worker abort; poll STATUS for error 7/completion |
| 8 | FILE | Bank | 64-byte flash record header; unavailable if no valid record |
| 9 | READ | Kind, bank, byte offset, count | Exactly count bytes; count <=256; kind 0 saved VCD / 1 last completed analyzer raw SRAM |
| 10 | Retired DISK | Reserved | Unknown-command status 5 in dispatcher 0.2; never reassigned |
| 11 | BOOTSEL | Empty | ACK, then enter ROM programming mode; refuses a running job |
| 12 | UPLOAD_BEGIN | Total image length | Reserve/reset the single PSRAM upload slot, 30..16412 bytes |
| 13 | UPLOAD_WRITE | Byte offset followed by 1..252 bytes | Require exactly the next offset and a bounded remaining length |
| 14 | UPLOAD_COMMIT | Empty | Validate complete image header and code CRC; make uploaded image loadable |

RUN accepts banks 0 (GPIO0–31) and 1 (GPIO32–44), trigger GPIO0..44, level 0/1,
timeout 10..30000 ms. Flag bit 0 permits generator outputs; bit 1 prepares the
generator HIGH and complements the pattern. Other bits are rejected. Generator
RUN prepares/holds its selected output bank, then waits for GO; analyzer RUN
arms immediately. The timeout bounds preparation/trigger wait, not flash-save
duration. USB remains responsive while waiting; responses can pause while
flash is erased/programmed after capture.

LOAD, RUN and upload commands refuse an active job.
FILE/READ refuse an active job. READ checks kind/bank/offset/count before
access. Raw SRAM is available only for the last successfully saved analyzer
job, the matching bank and until reset or another load/run. Saved VCD remains
available after reset. BOOTSEL requires no active job. ABORT can be sent while
armed/running and does nothing to an already finished job.

Dispatcher 0.2 exposes only CDC. The earlier DISK command and HELLO `disk`
field were removed; stored VCDs transfer through FILE/READ. The remaining
command IDs, frame format and protocol version are unchanged. ROM BOOTSEL
still provides its independent programming/recovery USB interface.

## Job record

STATUS is 16 uint32 words (64 bytes), in this order:

`bank`, `trigger_gpio`, `trigger_level`, `timeout_ms`, `flags`, `state`, `error`,
`start`, `abort`, `hz`, `samples`, `fdebug`, `remaining`, `raw_crc`, `vcd_bytes`,
`vcd_crc`.

States: 0 idle, 1 preparing, 2 armed, 3 generator running, 4 done,
5 error, 6 saving, 7 raw capture finished/pending save. Analyzer state 2 covers
the PIO trigger wait and brief hardware acquisition; it does not promise a
separately observable running transition. A successful job publishes all final
metadata before state 4. Intermediate fields are a live diagnostic snapshot.

Errors: 0 none, 1 setup/ABI/permission, 2 timeout, 3 receiver FIFO error/stall,
4 flash save failure, 7 requested abort. `remaining` is the data DMA's unfilled
word count. `fdebug` contains PIO0's raw FDEBUG register; terminal generator TX
stall after its finite burst is expected. Receiver FDEBUG must be zero for a
saved capture. Raw CRC32 covers 4096 little-endian sample bytes; VCD CRC32
covers the exact ASCII file. `hz` is the configured system/PIO clock.

FILE returns the existing 16-word flash header: magic `0x56434431`, version 1,
commit word 0, bank, GPIO base, pin count, sample count, sample Hz, VCD bytes,
VCD CRC32, FDEBUG, and five reserved words. Reserved words 0/1 now retain
trigger GPIO+1 and level; GPIO+1 zero denotes an older unspecified trigger.
Each slot's payload starts one flash sector after its header. Files have 1024
explicit timestamps at 1 ps scale; timestamps are nominal sample-relative time,
not wall-clock or a measured absolute trigger time.

## Dispatcher 0.3 extensions

Framing remains version 1. LIST now returns five 28-byte headers: app IDs
1 generator, 2 analyzer, 3 bus generator, 4 memory plus state analyzer,
5 passive state analyzer. Images use ABI 2, execution address `0x20030000`,
Thumb entry offset 1; ABI 1 uploads are rejected. HELLO reports `dispatcher-0.3`.
Existing 20-byte RUN, legacy FILE/READ and the 64-byte STATUS remain supported.

Extended RUN is **68 bytes**: the original five words followed by these twelve
little-endian uint32 values, in order:

`capacity`, `pre_percent`, `sample_hz`, `strobe`, `edge`, `address`, `mask`,
`memory_base`, `cycles`, `idle_ms`, `cycle_timeout_us`, `seed`.

| Field | Bounds and meaning |
| --- | --- |
| capacity | 1..65536 records |
| pre_percent | Exactly 10, 50 or 90; floor(capacity × percent / 100) history samples |
| sample_hz | For continuous timing app 2: 1000..1000000; other apps ignore it |
| strobe | State apps: 0 DS, 1 AS |
| edge | State apps: 0 assertion/falling, 1 release/rising |
| address, mask | 20-bit masked address comparator; mask 0 matches any state record |
| memory_base | 1 KiB-aligned address, 0..0xffc00 |
| cycles | Bus generator: 1..65536 |
| idle_ms | State/memory idle completion, 0 disabled or 1..30000; starts at RUN |
| cycle_timeout_us | 10..100000 |
| seed | Bus test pattern seed, 0..255 |

All fields are validated before scheduling, even when unused by that app.
Extended RUN requires working PSRAM. It is accepted by apps 2..5, with bank 0
required for bus/state apps. Continuous timing requires its trigger GPIO inside
the selected capture bank; the comparator uses the captured word. App 3 requires
flag 1 (drive); flag 4 additionally permits test writes/readback verification.
App 4 requires flag 1. App 2/5 need no output permission. Flag 2 is reserved for
the original pattern generator. New bus apps cannot use the legacy RUN format.
GO accepts app 1 or 3 in ARMED state.

The trigger record is the first post-trigger sample. The comparator waits for
the history quota before accepting a match. On trigger, excess older history
is discarded; exactly capacity minus history records, including the trigger,
complete the window. STOP, state idle completion and the overall timeout save
the retained partial window successfully, with a reason flag. Errors such as
FIFO stalls or DMA consumer overrun remain errors and do not replace storage.

| ID | Command | Request | Response |
| --- | --- | --- | --- |
| 16 | CAPTURE | Bank | 64-byte persistent raw-capture header below; unavailable if absent |
| 17 | STOP | Empty | Gracefully finish a continuous/state job and save its partial window |

Command 15 remains unassigned. READ adds kind 2 (persistent chronological raw
capture payload) and kind 3 (1024-byte emulated memory, bank 0, after app 4
completes). The same offset/count bounds and busy rejection apply. Kind 1
remains exclusively the last legacy analyzer SRAM capture. ABORT still
discards the current job, with error 7. STOP refuses apps without continuous
capture settings. STOP is accepted while preparing and armed. Preparation
does not clear an already accepted stop request.

CAPTURE header words:

`magic`, `version`, `committed`, `bank`, `app`, `count`, `stride`, `hz`,
`trigger`, `first_sequence`, `flags`, `bytes`, `crc`, `capacity`, `pre_percent`,
`edge_config`.

Magic is `0x43415032`, record version 1, committed 0. `count` may be zero.
Stride is 4 for timing or 12 for state records. `hz` is the actual divider-derived
nominal sample rate for timing, or system-clock timestamp frequency for state.
Trigger is the zero-based index in the downloaded window, or `0xffffffff` if
no trigger was accepted. `first_sequence` is the original acquisition record
number before discarded prehistory. Flags: 1 triggered, 2 manually stopped,
4 idle completion, 8 overall timeout; flags can combine. `bytes=count*stride`;
CRC32 covers those chronological raw bytes. `edge_config` bit 0 selects AS
instead of DS, bit 1 selects release instead of assertion. Other bits are zero.

Timing payload is uint32 sampled GPIO word (upper bank right aligned).
State records are three uint32s: GPIO0..31, timestamp low, timestamp high.
Timestamps are 64-bit PIO-clock counts from the acquisition's polling loop,
including inactive intervals; they are not host receipt times. Host VCD export
subtracts the first retained timestamp and adds a trigger marker. App 4 freezes
capture at a full window but continues memory service until STOP/idle/timeout.

STATUS `samples` is the retained count and `remaining` is capacity minus count
on a finished capture; they are not live counters. New captures use `raw_crc`;
VCD fields stay zero because formatting happens on the host. Generator error
8 indicates a test read-back mismatch. Missing/stuck DTACK or responder cycle
timeout uses error 2. FIFO stalls, exhausted DMA count or ring overrun use error 3.
Persistent raw slots are separate from the legacy VCD slots; select the desired
format explicitly when fetching. Full acquisition details are in
[bus-fixture.md](bus-fixture.md).

## Dispatcher 0.4: combined memory and fast timing

App 4 extended RUN with `sample_hz=150000000` selects combined memory/timing.
Capacity is 1..4096, bank is zero, and address/mask must be zero. AS/DS, edge
and 10/50/90-percent history fields select the hardware trigger. Other rates
retain app 4's existing state-capture mode. App image ABI remains 2.

RUN prepares resources and publishes ARMED. **GO also accepts app 4 in this
mode**. Its ACK is sent before acquisition starts; the dispatcher then parks
core 0 with USB IRQs masked. USB commands pause until capture/timeout, including
status and abort. The Python client automatically sends this GO after ARMED
and waits 10 ms before returning. Use the separate generator port to start
the bus cycle and configure a bounded receiver timeout.

CAPTURE flag **16** identifies app-4 fast timing: stride 4, 150000000 Hz,
GPIO0..31 words and uniform sample timestamps. Record layout and payload CRC
remain unchanged. `first_sequence` is zero in this mode, not a count of
discarded samples. The trigger index identifies the actual sampled edge.
A timeout without triggering saves the last capacity words with flags 16|8
and trigger `0xffffffff`; stopping before start can save an empty record.
VCD uses named bus signals. Receiver GPIO32 supplies a local SIO-to-PIO permit;
the bus generator must keep GPIO32 as input. See
[single-cycle-timing.md](single-cycle-timing.md) for wiring, commands and
current validation status.

Command **18 TIMING_DEBUG** takes an empty request and returns twelve uint32
values: `phase`, `completed_cycles`, `last_pins`, `trigger_search_index`,
`end_index`, `fdebug`, `timer_pc`, `ack_pc`, `pio_ctrl`, `stop_remaining`,
`stop_ctrl`, `timer_seed`. It reads only saved diagnostics and refuses an
active job or a configuration other than app-4 fast timing. Ring indexes are
modulo 8192; the trigger search index is an estimate derived from the stopped
pointer, not the selected logical trigger index. `timer_seed` is the requested
post-trigger count plus 64 guard clocks. Phase 0 means no decoded cycle, 1 AS
seen, 2 authorized/waiting for DS, 3 DS seen/waiting for AS release, 4 cycle
completed. Use `ice.py --port PORT timing-debug` after completion.

## Dispatcher 0.5: CPU reset/STOP fixture

Framing, protocol version, ABI 2, image capacity and the 64-byte STATUS are
unchanged. HELLO reports `dispatcher-0.5`; LIST returns six 28-byte headers,
adding app **6 CPU emulator**. Host/device image validation accepts IDs 1..6.
App 6 requires extended RUN, bank 0 and exactly flag 1 (drive). GO accepts an
armed app 6. Its `cycles` field is an instruction budget (1..65536), not a
byte-cycle count. The other twelve-field limits still apply. STATUS `samples`
counts completed byte reads, `remaining` is instruction budget minus executed
instructions, and `hz=8000000` describes nominal PIO phase timing only.
Error 9 reports an unsupported/limited interpreter operation or instruction
budget exhaustion; existing timeout 2 and abort 7 remain. STOP command 17
also accepts app 6 and ends its job without executing a CPU STOP instruction.
Terminal CPU STOP or reset-vector halt is successful JOB_DONE; the separate
register report identifies the CPU state. Cleanup releases all outputs.

App 4 accepts flags **1|8** to load a boot image and issue the fixture's
RESET/HALT pulse. With flag 8, `memory_base` must be zero, `sample_hz` must
not be 150000000, and `seed` selects 0 STOP, 1 NOP/STOP, 2 reset-vector BERR.
All combinations are validated before scheduling. Without flag 8 the existing
RAM/state or fast-timing behavior is unchanged. The CPU application rejects
flag 8. `READ` kind 3 still downloads the resulting 1024-byte RAM.

| ID | Command | Request | Response |
| --- | --- | --- | --- |
| 19 | CPU_STATUS | Empty | Sixteen uint32 values; app 6 after job completion/error |
| 20 | BOOT_STATUS | Empty | Sixteen uint32 values; app 4 boot profile after completion/error |

Both refuse active jobs with status 2 and unavailable records with status 4.
Reports are volatile, cleared on each accepted RUN, and are not part of the
persistent capture record. Command 19 words are:

`version`, `state`, `ssp`, `pc`, `sr`, `opcode`, `instructions`, `reads`,
`resets`, `fault`, `address`, `fc`, `reset_seen`, `halt_asserted`,
`reset_level`, `halt_level`.

Version is 1. CPU states: 0 waiting reset, 1 fetching vectors, 2 running,
3 STOP, 4 catastrophic halt, 5 unsupported/failed. Faults: 0 none, 1 bus,
2 alignment, 3 opcode, 4 unsupported STOP SR. `address`/`fc` identify the
last attempted byte. Pad levels are sampled at interpreter exit, before
dispatcher output cleanup. `halt_asserted` distinguishes CPU assertion from
an external HALT input; STOP leaves it zero.

Command 20 words are:

`version`, `profile`, `reset_asserted`, `reset_released`, `halt_seen`,
`cycles`, `reads`, `writes`, `first_address`, `last_address`, `first_fc`,
`last_fc`, `fc_errors`, `reset_low_us`, `reset_high_us`, `halt_low_us`.

Version is 1; reset flags/times describe commanded transitions, with LOW at
time zero and release at least 1000 us later. `halt_seen` latches an actual
LOW pad sample after reset release, excluding the reset pulse's own HALT.
Read/write counts include decoded attempted cycles (including the faulted
read). FC error count compares against supervisor program FC=6. Software
times are microseconds relative to reset start and have polling latency.
The state VCD/raw format remains GPIO0..31 plus timestamp; it contains no
synchronously sampled upper-bank sideband signals. See
[cpu-emulator.md](cpu-emulator.md) for fixture mapping and limitations.

## Dispatcher 0.6: uploaded ROM and instruction snapshots

HELLO reports `dispatcher-0.6`. Framing, app IDs, ABI 2, image headers,
STATUS and saved capture formats are unchanged. App 6 now accepts flags 1
(drive/read only) or 5 (drive plus CPU memory writes). Instruction-budget
completion is successful JOB_DONE, CPU state **6 paused**; it releases bus
outputs without asserting HALT. CPU opcode failures retain job error 9.
STATUS `samples` counts completed byte transfers, including permitted writes;
`remaining` counts unexecuted instruction budget.

App 4 boot flag 8 adds `seed=3`, **uploaded image**, requiring a committed
image. Base must be zero and fast-timing mode remains forbidden. This profile
serves a full 1 MiB target map at PSRAM `0x11200000`. The uploaded range starts
at target zero and is read-only to the CPU; writes to it receive BERR. The rest
is RAM. Existing three built-in boot profiles retain their 1 KiB memory.
Uploading clears the 1 MiB map; image RUN preserves ROM and RAM contents.
Uploaded image/RAM is volatile across MCU reset. No upload writes flash.

| ID | Command | Request | Response |
| --- | --- | --- | --- |
| 21 | MEMORY_BEGIN | ROM byte length, CRC32 | Clear target map and invalidate prior image; require 8..1048576 bytes |
| 22 | MEMORY_WRITE | Sequential byte offset and 1..252 data bytes | Reject gaps, repeats, overruns, empty writes and writes after commit |
| 23 | MEMORY_COMMIT | Empty | Require all bytes and matching CRC; status 3 for incomplete/corrupt image |
| 24 | MEMORY_INFO | Empty | Six uint32: version 1, capacity, ROM bytes, expected CRC, uploaded bytes, ready |
| 25 | CPU_REGISTERS | Empty | Full 140-byte CPU register record below |
| 26 | CPU_TRACE | Snapshot index, or `0xffffffff` for metadata | Full register record, or four-word trace metadata |
| 27 | MEMORY_POKE | Target address, byte value | Set one RAM byte outside the committed ROM range |

All commands refuse active worker jobs (status 2). Commands 21–23 require
app 4 and working PSRAM. Invalid upload bounds/order return status 1.
MEMORY_POKE requires app 4, a committed image, address below 1048576 and
value 0..255; ROM addresses return status 1. It changes only emulated RAM,
without a physical bus cycle. MEMORY_INFO is also available without a
committed image. READ adds **kind 4** for the target map: app 4, bank zero,
committed image, address/count within 1 MiB. Existing count <=256 and busy
checks apply. READ kind 3 remains the original 1024-byte fixture RAM.

CPU_STATUS (19) retains its original 64-byte prefix, with CPU record version
**2**. CPU_REGISTERS (25) returns that same prefix followed by D0..D7,
A0..A7, USP, completed byte-write count and attempted instruction PC:
35 little-endian uint32 values, 140 bytes. SSP tracks supervisor A7; USP
tracks user A7. Reports require app 6 and a completed/error job. `opcode` and
`instruction_pc` identify unsupported instructions even when PC has advanced
past their opcode/extension bytes.

CPU_TRACE metadata is version 1, retained snapshot count, total snapshot
count, dropped count. The first snapshot follows reset-vector acquisition;
subsequent snapshots follow each attempted instruction. The first 64 are
retained; later snapshots increment the explicit dropped count. An out-of-range
index returns status 1. The trace and full CPU record are volatile and reset
on the next CPU RUN. CPU state in a post-instruction snapshot describes that
instruction's result; the final report changes RUNNING to PAUSED when the
budget is reached. Resuming a paused instruction stream is not implemented;
the next RUN requires a fresh external reset sequence.

The image boot profile accepts supervisor program FC=6 and data FC=5 in its
memory-side checks. Its generic RAM byte at `$80007` is set to `$02` by the
ABC1600 helper to stand in for the reset cause register. This is a minimal
fixture, not a complete ABC1600 peripheral/MMU implementation. See
[ABC1600 execution and validation](abc1600.md).
