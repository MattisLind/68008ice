// SPDX-License-Identifier: BSD-3-Clause
// Derived from MAME's ABC1600 MAC model; copyright Curt Coder.
#ifndef ICE_ABC1600_MEMORY_H
#define ICE_ABC1600_MEMORY_H
#include <stdbool.h>
#include <stdint.h>
#define ABC1600_RAM ((uint8_t *)0x11300000u)
#define ABC1600_ROM_BYTES 16384u
#define ABC1600_RAM_BYTES 1048576u
typedef struct {
    uint32_t version,task,boote,magic,cause,reset_button,partst,cause_reads;
    uint32_t segment_writes,page_high_writes,page_low_writes,task_writes,ram_reads,ram_writes;
    uint32_t bus_errors,unsupported_io,last_address,last_physical,last_fc,last_write,last_target;
} abc1600_status;
typedef struct {
    abc1600_status status;
    uint8_t segment[1024];
    uint16_t page[1024];
} abc1600_memory;
extern abc1600_memory abc1600_model;
void abc1600_memory_init(abc1600_memory *);
int abc1600_memory_access(abc1600_memory *,const uint8_t *rom,uint8_t *ram,
                          uint32_t address,uint32_t fc,bool write,uint8_t *value);
#endif
