# Symbol addresses and BANK/ARTIFACTS are supplied from matching ELF files.
proc trace_addr {board} {global CONTROL1 CONTROL2;return [expr {$board==1 ? $CONTROL1 : $CONTROL2}]}
proc trace_words {board} {targets board$board.cm0;return [read_memory [trace_addr $board] 32 16]}
proc trace_request {board command bank} {
    set base [trace_addr $board];targets board$board.cm0
    set seq [expr {([lindex [read_memory [expr {$base+8}] 32 1] 0]+1)&0xffffffff}]
    mww [expr {$base+20}] $bank;mww [expr {$base+16}] $command;mww [expr {$base+8}] $seq
    return $seq
}
proc trace_wait {board seq state attempts} {
    for {set i 0} {$i<$attempts} {incr i} {
        set words [trace_words $board]
        if {[lindex $words 7]!=0 || [lindex $words 6]==4} {error "Board $board trace error: $words"}
        if {[lindex $words 3]==$seq && [lindex $words 6]==$state} {return $words}
        sleep 10
    }
    error "Board $board timed out waiting for state $state: $words"
}

set result [catch {
    foreach board {1 2} {
        targets board$board.cm0;poll
        if {[board$board.cm0 curstate] eq "halted"} {resume}
        set words [trace_words $board]
        if {[lindex $words 0]!=0x50494f31 || [lindex $words 1]!=1} {error "Wrong PIO trace firmware on board $board"}
    }
    set source_seq [trace_request 1 1 $BANK]
    trace_wait 1 $source_seq 1 100
    set receiver_seq [trace_request 2 1 $BANK]
    trace_wait 2 $receiver_seq 1 100
    set source_seq [trace_request 1 2 $BANK]
    # Keep SWD away from both SRAM buses during the microsecond PIO/DMA burst.
    sleep 20
    set source [trace_wait 1 $source_seq 3 100]
    set receiver [trace_wait 2 $receiver_seq 3 1500]
    echo "SOURCE $BANK $source"
    echo "RECEIVER $BANK $receiver"
    targets board2.cm0
    dump_image $ARTIFACTS/bank$BANK.bin $SAMPLES2 4096
} reason]
foreach board {1 2} {catch {trace_request $board 3 $BANK}}
if {$result} {error $reason}
echo "PIO TRACE BANK $BANK COMPLETE"
