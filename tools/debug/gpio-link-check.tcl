# Read actual pad inputs, output latches and output enables on both chips.
# RP2350 SIO register offsets are from Pico SDK 2.3.1 hardware/regs/sio.h.
proc link_sample {target} {
    targets $target
    set input [expr {[lindex [read_memory 0xd0000004 32 1] 0] & 1}]
    set led_input [expr {([lindex [read_memory 0xd0000008 32 1] 0] >> 7) & 1}]
    set led_output [expr {([lindex [read_memory 0xd0000014 32 1] 0] >> 7) & 1}]
    set link_oe [expr {[lindex [read_memory 0xd0000030 32 1] 0] & 1}]
    set led_oe [expr {([lindex [read_memory 0xd0000034 32 1] 0] >> 7) & 1}]
    return [list $input $led_input $led_output $link_oe $led_oe]
}

set seen_low 0
set seen_high 0
set samples 0
# Keep both applications running. Halting the receiver can defer its GPIO IRQ,
# so a snapshot taken across separate halt requests is not a phase measurement.
# Bracket each receiver sample with source reads and skip a crossing edge.
for {set i 0} {$i < 20} {incr i} {
    set source [link_sample board1.cm0]
    sleep 10
    set receiver [link_sample board2.cm0]
    set after [link_sample board1.cm0]
    if {$source != $after} {
        echo "Skipping sample $i across a source edge"
        sleep 100
        continue
    }
    set level [lindex $source 0]
    if {[lindex $source 3] != 1 || [lindex $receiver 3] != 0} {
        error "GPIO0 direction incorrect: source=$source receiver=$receiver"
    }
    if {[lindex $source 4] != 1 || [lindex $receiver 4] != 1} {
        error "An LED output is disabled"
    }
    if {[lindex $receiver 0] != $level} {
        error "GPIO0 wire mismatch: source=$source receiver=$receiver"
    }
    if {[lindex $source 1] != $level || [lindex $source 2] != $level} {
        error "Source LED does not follow GPIO0"
    }
    if {[lindex $receiver 1] != (1 - $level) || [lindex $receiver 2] != (1 - $level)} {
        error "Receiver LED is not the inverse of GPIO0: source=$source receiver=$receiver"
    }
    if {$level} {set seen_high 1} else {set seen_low 1}
    incr samples
    echo "PASS sample $i: GPIO0=$level source_LED=[lindex $source 1] receiver_LED=[lindex $receiver 1]; source drives, receiver input"
    sleep 100
}
if {!$seen_low || !$seen_high || $samples < 8} {
    error "Need at least eight stable samples covering both GPIO0 levels"
}
echo "GPIO LINK CHECK PASSED: $samples stable samples, both wire levels, inverse LEDs, receiver GPIO0 input"
