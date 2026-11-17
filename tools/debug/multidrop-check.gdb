set pagination off
set confirm off
set remotetimeout 15
python
import json
import os
from pathlib import Path
import time

instance = int(os.environ["ICE_MULTIDROP_INSTANCE"])
peer = 3 - instance
artifacts = Path(os.environ["ICE_MULTIDROP_TEST_DIR"])

def command(text):
    return gdb.execute(text, to_string=False)

def value(expression):
    return int(gdb.parse_and_eval(expression))

def halt():
    command("monitor halt")
    command("maintenance flush register-cache")

def barrier(stage):
    (artifacts / ("%d-%s.ready" % (instance, stage))).touch()
    deadline = time.monotonic() + 15
    while not (artifacts / ("%d-%s.ready" % (peer, stage))).exists():
        if time.monotonic() >= deadline:
            raise gdb.GdbError("Partner did not reach " + stage)
        time.sleep(0.05)

bp = None
try:
    halt()
    board = gdb.parse_and_eval("board_id").string()
    if value("*(unsigned int *)0x401000ac") & 15 != instance:
        raise gdb.GdbError("Wrong hardware SWD instance selected")
    print("BOARD %d: USB/chip ID %s" % (instance, board))
    barrier("attached")

    bp = gdb.Breakpoint("blink_tick", type=gdb.BP_HARDWARE_BREAKPOINT)
    command("continue")
    if value("$pc") != int(bp.locations[0].address):
        raise gdb.GdbError("Did not reach blink_tick breakpoint")
    pc = value("$pc")
    command("stepi")
    if value("$pc") == pc:
        raise gdb.GdbError("Instruction step did not advance PC")
    bp.delete()
    bp = None
    print("PASS: board %d breakpoint and single-step" % instance)
    barrier("stepped")

    # Both GDB connections stay open. In each phase one board is deliberately
    # held halted while the other runs, detecting accidental target aliasing
    # or cross-chip SMP grouping as well as ordinary halt/resume failures.
    for running in (1, 2):
        halt()
        before = value("blink_count")
        command("set variable blink_period_ms = 100")
        barrier("phase%d-start" % running)
        if instance == running:
            command("monitor resume")
            time.sleep(1.6)
            halt()
        barrier("phase%d-finish" % running)
        after = value("blink_count")
        if instance == running:
            if after - before < 8:
                raise gdb.GdbError("Running board did not advance fast enough")
            print("PASS: board %d ran %d ticks while board %d stayed halted" %
                  (instance, after - before, peer))
        else:
            if after != before:
                raise gdb.GdbError("Halted board changed while partner ran")
            print("PASS: board %d held counter %d while board %d ran" %
                  (instance, after, peer))
        barrier("phase%d-verified" % running)

    (artifacts / ("board%d.json" % instance)).write_text(json.dumps({
        "instance": instance, "board_id": board, "blink_count": value("blink_count"),
        "breakpoint": True, "single_step": True, "independent_halt_resume": True,
        "live_variable_write": True,
    }, indent=2) + "\n")
    print("MULTIDROP BOARD %d PASSED" % instance)
finally:
    if bp is not None:
        bp.delete()
    halt()
    command("set variable blink_period_ms = 500")
    command("monitor resume")
    command("detach")
end
quit
