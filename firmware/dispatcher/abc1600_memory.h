// SPDX-License-Identifier: BSD-3-Clause
// Derived from MAME's ABC1600 MAC model; copyright Curt Coder.
#ifndef ICE_ABC1600_MEMORY_H
#define ICE_ABC1600_MEMORY_H
#include <stdbool.h>
#include <stdint.h>
#define ABC1600_RAM ((uint8_t *)0x11300000u)
#define ABC1600_ROM_BYTES 16384u
#define ABC1600_RAM_BYTES 1048576u
#define ABC1600_STORAGE_BYTES (ABC1600_RAM_BYTES+524288u)
typedef struct {
    uint16_t xsize,ysize,xto,xfrom,ty,fy,wrm,gmdi;
    uint8_t direction,flag,clocks_disabled,display,crtc_address,crtc[32],ms[16],ds[16];
    uint32_t ticks,moves,busy,row,column;
} abc1600_video;
typedef struct {
    uint32_t version,task,boote,magic,cause,reset_button,partst,cause_reads;
    uint32_t segment_writes,page_high_writes,page_low_writes,task_writes,ram_reads,ram_writes;
    uint32_t bus_errors,unsupported_io,last_address,last_physical,last_fc,last_write,last_target;
} abc1600_status;
typedef struct {
    abc1600_status status;
    uint8_t segment[1024];
    uint16_t page[1024];
    // Z8536 universal-bus register pointer, as wired in abc1600.cpp.
    uint8_t cio[48],cio_pointer,cio_state0,cio_output[3];
    uint32_t io_reads,io_writes;
    uint8_t dart[2][8],dart_pointer[2],dart_rr0[2];
    uint32_t keyboard_polls,keyboard_tx_count;
    uint8_t keyboard_tx[256];
    abc1600_video video;
    uint8_t scc[2][16],scc_pointer[2];
} abc1600_memory;
extern abc1600_memory abc1600_model;
void abc1600_memory_init(abc1600_memory *);
int abc1600_memory_access(abc1600_memory *,const uint8_t *rom,uint8_t *ram,
                          uint32_t address,uint32_t fc,bool write,uint8_t *value);
#endif
