// SPDX-License-Identifier: Apache-2.0
// Fast host execution of the production CPU and memory model.
#include <string.h>
#include "cpu68008.h"
#include "abc1600_memory.h"
static cpu68008 cpu;
static abc1600_memory memory;
static uint8_t rom[16384],ram[ABC1600_STORAGE_BYTES];
static uint32_t events[4096],total;
static int read_byte(void *ctx,uint32_t a,uint32_t fc,uint8_t *v) {(void)ctx;int s=abc1600_memory_access(&memory,rom,ram,a,fc,false,v);events[total++%4096]=a|((uint32_t)*v<<20)|(1u<<30);return s;}
static int write_byte(void *ctx,uint32_t a,uint32_t fc,uint8_t v) {(void)ctx;events[total++%4096]=a|((uint32_t)v<<20);return abc1600_memory_access(&memory,rom,ram,a,fc,true,&v);}
void boot_reset(const uint8_t *image) {
    total=0;memcpy(rom,image,sizeof rom);memset(ram,0,sizeof ram);abc1600_memory_init(&memory);cpu68008_init(&cpu);
    cpu68008_reset(&cpu,read_byte,0);
}
unsigned boot_run(unsigned budget,unsigned stop_pc) {
    unsigned done=0;
    while(done<budget && cpu.state==CPU_RUNNING && cpu.pc!=stop_pc) {
        cpu68008_execute(&cpu,read_byte,write_byte,0);++done;
    }
    return done;
}
const cpu68008 *boot_cpu(void) {return &cpu;}
const abc1600_memory *boot_memory(void) {return &memory;}
const uint8_t *boot_ram(void) {return ram;}
int boot_read(void *ctx,uint32_t a,uint32_t fc,uint8_t *v) {return read_byte(ctx,a,fc,v);}
int boot_write(void *ctx,uint32_t a,uint32_t fc,uint8_t v) {return write_byte(ctx,a,fc,v);}
const uint32_t *boot_events(void) {return events;}
unsigned boot_total(void) {return total;}
