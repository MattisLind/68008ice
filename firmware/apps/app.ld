ENTRY(app_main)
SECTIONS {
    . = 0x20030000;
    .text : { KEEP(*(.entry)) *(.text*) *(.rodata*) }
    .data : { *(.data*) }
    .bss : { *(.bss*) *(COMMON) }
    ASSERT(SIZEOF(.bss) == 0, "Modules must keep state in the job/API buffers")
    ASSERT(. <= 0x20034000, "Module exceeds 16 KiB")
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
}
