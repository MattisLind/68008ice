# MAILBOX1/2 and IDADDR1/2 are resolved from matching ELF symbols by the host.
# Keep both CPUs running: mailbox requests are serviced by their main loops.
set scan_mask [expr {(1 << $SCAN_PIN_COUNT) - 1}]
proc scan_command {board pin up {high 0}} {
    global MAILBOX1 MAILBOX2
    set base [expr {$board == 1 ? $MAILBOX1 : $MAILBOX2}]
    targets board$board.cm0
    set completed [lindex [read_memory [expr {$base + 12}] 32 1] 0]
    set scan_sequence [expr {($completed + 1) & 0xffffffff}]
    mww [expr {$base + 16}] $pin
    mww [expr {$base + 20}] $up
    mww [expr {$base + 40}] $high
    mww [expr {$base + 8}] $scan_sequence
    set acknowledged 0
    for {set attempt 0} {$attempt < 100} {incr attempt} {
        set ack [lindex [read_memory [expr {$base + 12}] 32 1] 0]
        if {$ack == $scan_sequence} {set acknowledged 1; break}
        sleep 2
    }
    if {!$acknowledged} {error "Board $board mailbox timeout"}
    set status [read_memory [expr {$base + 24}] 32 2]
    if {[lindex $status 0] != $pin || [lindex $status 1] != 0} {
        error "Board $board did not apply requested pin $pin: $status"
    }
    if {[lindex [read_memory [expr {$base + 44}] 32 1] 0] != $high} {
        error "Board $board did not apply requested output level"
    }
}

proc scan_inputs {board} {
    global scan_mask
    targets board$board.cm0
    set words [read_memory 0xd0000004 32 2]
    return [expr {([lindex $words 0] | ([lindex $words 1] << 32)) & $scan_mask}]
}

proc scan_output_enable {board} {
    global scan_mask
    targets board$board.cm0
    set words [read_memory 0xd0000030 32 2]
    return [expr {([lindex $words 0] | ([lindex $words 1] << 32)) & $scan_mask}]
}

set result [catch {
    foreach board {1 2} {
        targets board$board.cm0
        poll
        if {[board$board.cm0 curstate] eq "halted"} {resume}
        set base [expr {$board == 1 ? $MAILBOX1 : $MAILBOX2}]
        set header [read_memory $base 32 2]
        if {[lindex $header 0] != 0x47434e31 || [lindex $header 1] != 2} {
            error "Board $board is not running the expected connectivity firmware"
        }
        if {[lindex [read_memory [expr {$base + 36}] 32 1] 0] != $SCAN_PIN_COUNT} {
            error "Board $board test range does not match the host"
        }
        set id_address [expr {$board == 1 ? $IDADDR1 : $IDADDR2}]
        set identity ""
        foreach byte [read_memory $id_address 8 16] {
            append identity [format %c $byte]
        }
        echo "BOARD $board $identity"
        scan_command $board 0xffffffff 0
    }
    echo "FORMAT 2 $SCAN_PIN_COUNT"

    # Bias each completely undriven harness both ways to expose stuck levels.
    foreach up {0 1} {
        scan_command 1 0xffffffff $up
        scan_command 2 0xffffffff $up
        sleep 5
        echo "BASELINE $up [scan_inputs 1] [scan_inputs 2]"
    }

    foreach high {0 1} {
      set up [expr {1 - $high}]
      foreach driver {1 2} {
        set receiver [expr {3 - $driver}]
        scan_command 1 0xffffffff $up
        scan_command 2 0xffffffff $up
        sleep 5
        set baseline_driver [scan_inputs $driver]
        set baseline_receiver [scan_inputs $receiver]
        for {set pin 0} {$pin < $SCAN_PIN_COUNT} {incr pin} {
            scan_command $driver $pin $up $high
            sleep 3
            set source1 [scan_inputs $driver]
            set receive1 [scan_inputs $receiver]
            sleep 3
            set source2 [scan_inputs $driver]
            set receive2 [scan_inputs $receiver]
            set source_oe [scan_output_enable $driver]
            set receiver_oe [scan_output_enable $receiver]
            if {$source_oe != (1 << $pin) || $receiver_oe != 0} {
                error "Unexpected output enables: driver=$source_oe receiver=$receiver_oe"
            }
            # Detect expiration rather than reporting a false open connection.
            targets board$driver.cm0
            set base [expr {$driver == 1 ? $MAILBOX1 : $MAILBOX2}]
            set status [read_memory [expr {$base + 24}] 32 2]
            if {[lindex $status 0] != $pin || [lindex $status 1] != 0} {
                error "Drive lease expired on board $driver GPIO$pin"
            }
            echo "SCAN $high $driver $pin $baseline_driver $baseline_receiver $source1 $receive1 $source2 $receive2"
            scan_command $driver 0xffffffff $up $high
            sleep 3
            echo "RELEASE $high $driver $pin [scan_inputs $driver] [scan_inputs $receiver]"
        }
      }
    }
} reason]

# Release both boards even after a failed scan. Firmware also releases an active
# drive after a one-second lease, provided its CPU remains running.
foreach board {1 2} {
    catch {scan_command $board 0xffffffff 0}
}
if {$result} {error $reason}
foreach board {1 2} {
    if {[scan_output_enable $board] != 0} {error "Board $board did not release test pins"}
}
echo "GPIO CONNECTIVITY SCAN COMPLETE"
