set pagination off
set confirm off
set remotetimeout 15
python
import time

def command(text):
    return gdb.execute(text, to_string=False)

def value(name):
    return int(gdb.parse_and_eval(name))

def halt():
    command("monitor halt")
    command("maintenance flush register-cache")

try:
    command("monitor reset halt")
    bp = gdb.Breakpoint("blink_tick", type=gdb.BP_HARDWARE_BREAKPOINT)
    command("continue")
    if value("$pc") != int(bp.locations[0].address):
        raise gdb.GdbError("Did not stop at the blink_tick hardware breakpoint")
    print("PASS: hardware breakpoint reached blink_tick")
    command("list blink_tick")
    command("info registers pc sp xpsr")
    pc = value("$pc")
    command("stepi")
    if value("$pc") == pc:
        raise gdb.GdbError("Single-step did not advance PC")
    print("PASS: instruction single-step advanced PC")
    bp.delete()

    before = value("blink_count")
    command("monitor resume")
    time.sleep(1.6)
    halt()
    after = value("blink_count")
    if after <= before:
        raise gdb.GdbError("Blink counter did not advance while running")
    print("PASS: resume advanced blink_count: %d -> %d" % (before, after))

    time.sleep(1.1)
    frozen = value("blink_count")
    if frozen != after:
        raise gdb.GdbError("Blink counter changed while CPU was halted")
    print("PASS: halt held blink_count=%d for 1.1 seconds" % frozen)
    command("print led_state")
    command("print blink_period_ms")

    command("set variable blink_period_ms = 100")
    if value("blink_period_ms") != 100:
        raise gdb.GdbError("Debugger variable write did not read back")
    command("monitor resume")
    time.sleep(1.6)
    halt()
    faster = value("blink_count")
    if faster - frozen < 8:
        raise gdb.GdbError("Changing blink_period_ms did not accelerate blinking")
    print("PASS: live variable write changed timing; %d toggles in 1.6 s" % (faster - frozen))
    print("DEBUG CHECK PASSED")
finally:
    # Return the board to its normal 500 ms blink, including on test failure.
    command("monitor reset run")
    command("detach")
end
quit
