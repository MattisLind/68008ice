// SPDX-License-Identifier: BSD-3-Clause
// Functional port of the MAC mapping/register behavior in MAME's
// src/mame/luxor/abc1600_mmu.cpp, copyright Curt Coder.
// See LICENSES/BSD-3-Clause-MAME.txt. Bus phase timing remains the PIO HAL's.
#include <string.h>
#include "abc1600_memory.h"
#include "cpu68008.h"
abc1600_memory abc1600_model;

void abc1600_memory_init(abc1600_memory *m) {
    memset(m,0,sizeof *m);m->status.version=1;
    memset(m->segment,255,sizeof m->segment);memset(m->page,255,sizeof m->page);
}
static uint32_t segment_address(abc1600_memory *m,uint32_t address,bool ifc2) {
    uint32_t a19=(address>>19)&1;
    uint32_t task=(!a19 && !ifc2) ? 0 : m->status.task;
    uint32_t sega19=a19 && (ifc2 || (address&0x100));
    return (task<<5)|(sega19<<4)|((address>>15)&15);
}
static int error(abc1600_memory *m,bool io) {
    ++m->status.bus_errors;if(io)++m->status.unsupported_io;return CPU_BUS_BERR;
}
int abc1600_memory_access(abc1600_memory *m,const uint8_t *rom,uint8_t *ram,
                          uint32_t address,uint32_t fc,bool write,uint8_t *value) {
    address&=0xfffff;
    m->status.last_address=address;m->status.last_fc=fc;m->status.last_write=write;
    m->status.last_physical=UINT32_MAX;
    if(fc!=1 && fc!=2 && fc!=5 && fc!=6)return error(m,false);
    bool fetch=fc==2 || fc==6;
    bool super=(fc&4)!=0;
    bool ifc2=(m->status.magic || !fetch || write) && !super;
    if(!write && !m->status.boote && address<0x20000) {
        m->status.last_target=0;*value=rom[address&0x3fff];return CPU_BUS_OK;
    }
    if(!ifc2 && (address&0x80000)) {
        m->status.last_target=1;
        // MAC register handlers in MAME decode with TR_READ/TR_WRITE even
        // when a user program fetch (MAGIC=0) routed into the MAC window.
        uint32_t sega=segment_address(m,address,!super);
        uint32_t pga=((m->segment[sega]&63)<<4)|((address>>11)&15);
        switch(address&7) {
        case 0:
            if(write) {m->page[pga]=((*value&0xc3)<<8)|(m->page[pga]&255);++m->status.page_high_writes;}
            else {uint32_t high=m->page[pga]>>8;*value=high|((high&2) ? 0x3c : 0);}
            break;
        case 1:
            if(write) {m->page[pga]=(m->page[pga]&0xff00)|*value;++m->status.page_low_writes;}
            else *value=m->page[pga]&255;
            break;
        case 3:
            if(write) {m->segment[sega]=*value&0x7f;++m->status.segment_writes;}
            else *value=(!m->status.magic<<7)|(m->segment[sega]&0x7f);
            break;
        case 5:
            if(write) {m->status.task=*value&15;m->status.boote=!(*value&64);m->status.magic=!(*value&128);++m->status.task_writes;}
            else *value=0;
            break;
        case 7:
            if(!write) {*value=m->status.reset_button|2|(m->status.partst ? 0 : m->status.cause);++m->status.cause_reads;}
            break;
        default:if(!write)*value=0;break;
        }
        return CPU_BUS_OK;
    }
    m->status.last_target=2;
    uint32_t sega=segment_address(m,address,ifc2);
    uint32_t pga=((m->segment[sega]&63)<<4)|((address>>11)&15);
    uint16_t page=m->page[pga];
    uint32_t physical=((page&1023)<<11)|(address&0x7ff);
    m->status.cause=((address>>13)&31)|4;m->status.last_physical=physical;
    if((page&0x8000) || (write && !(page&0x4000)))return error(m,false);
    if(physical<ABC1600_RAM_BYTES) {
        if(write) {ram[physical]=*value;++m->status.ram_writes;}
        else {*value=ram[physical];++m->status.ram_reads;}
    } else if(physical>=0x1fe000) {
        // No device needed by the first 105 instructions lives here. Fail
        // explicitly until the corresponding ABC1600 peripheral is modelled.
        m->status.last_target=4;return error(m,true);
    } else {m->status.last_target=3;if(!write)*value=255;}
    return CPU_BUS_OK;
}
