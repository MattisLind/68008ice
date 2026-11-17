// SPDX-License-Identifier: Apache-2.0
// Test-only adapter. Musashi is downloaded separately with its MIT notices.
#include <stdint.h>
#include <string.h>
#include "m68k.h"
#include "cpu68008.h"
#define BYTES 1048576u
static uint8_t actual[BYTES],reference[BYTES];
static cpu_read8 machine_read;
static cpu_write8 machine_write;
static void *machine_context;
static unsigned machine_fc,machine_error;
static void function_code(unsigned fc) {machine_fc=fc;}
unsigned int m68k_read_memory_8(unsigned int a) {
    if(machine_read) {uint8_t v=255;int status=machine_read(machine_context,a&(BYTES-1),machine_fc,&v);if(status)machine_error=status;return v;}
    return reference[a&(BYTES-1)];
}
unsigned int m68k_read_memory_16(unsigned int a) {return (m68k_read_memory_8(a)<<8)|m68k_read_memory_8(a+1);}
unsigned int m68k_read_memory_32(unsigned int a) {return (m68k_read_memory_16(a)<<16)|m68k_read_memory_16(a+2);}
unsigned int m68k_read_disassembler_8(unsigned int a) {return m68k_read_memory_8(a);}
unsigned int m68k_read_disassembler_16(unsigned int a) {return m68k_read_memory_16(a);}
unsigned int m68k_read_disassembler_32(unsigned int a) {return m68k_read_memory_32(a);}
void m68k_write_memory_8(unsigned int a,unsigned int v) {
    if(machine_write) {int status=machine_write(machine_context,a&(BYTES-1),machine_fc,v);if(status)machine_error=status;}
    else reference[a&(BYTES-1)]=v;
}
void m68k_write_memory_16(unsigned int a,unsigned int v) {m68k_write_memory_8(a,v>>8);m68k_write_memory_8(a+1,v);}
void m68k_write_memory_32(unsigned int a,unsigned int v) {m68k_write_memory_16(a,v>>16);m68k_write_memory_16(a+2,v);}
static int read8(void *ctx,uint32_t a,uint32_t fc,uint8_t *v) {(void)ctx;(void)fc;*v=actual[a];return 0;}
static int write8(void *ctx,uint32_t a,uint32_t fc,uint8_t v) {(void)ctx;(void)fc;actual[a]=v;return 0;}
// Result bits: actual failed, register mismatch, PC mismatch, SR mismatch, RAM mismatch.
unsigned compare_instruction(const uint8_t *initial,cpu68008 *c,uint32_t *expected,uint32_t *difference) {
    static int initialized;
    if(!initialized) {m68k_init();m68k_set_cpu_type(M68K_CPU_TYPE_68000);initialized=1;}
    machine_read=0;machine_write=0;
    memcpy(actual,initial,BYTES);memcpy(reference,initial,BYTES);
    m68k_pulse_reset();m68k_execute(0);m68k_set_reg(M68K_REG_SR,c->sr);
    m68k_set_reg(M68K_REG_USP,c->usp);m68k_set_reg(M68K_REG_ISP,c->ssp);
    for(unsigned i=0;i<8;++i) {m68k_set_reg(M68K_REG_D0+i,c->d[i]);m68k_set_reg(M68K_REG_A0+i,c->a[i]);}
    m68k_set_reg(M68K_REG_PC,c->pc);m68k_execute(1);
    unsigned result=cpu68008_execute(c,read8,write8,0)!=0 || c->state!=CPU_RUNNING;
    for(unsigned i=0;i<8;++i) {
        expected[i]=m68k_get_reg(0,M68K_REG_D0+i);expected[8+i]=m68k_get_reg(0,M68K_REG_A0+i);
        if(c->d[i]!=expected[i] || c->a[i]!=expected[8+i])result|=2;
    }
    expected[16]=m68k_get_reg(0,M68K_REG_PC);expected[17]=m68k_get_reg(0,M68K_REG_SR);
    if(c->pc!=expected[16])result|=4;
    if(c->sr!=expected[17])result|=8;
    *difference=UINT32_MAX;
    if(memcmp(actual,reference,BYTES)) {
        result|=16;
        for(unsigned i=0;i<BYTES;++i)if(actual[i]!=reference[i]) {*difference=i;break;}
    }
    return result;
}
static void machine_registers(uint32_t *out) {
    for(unsigned i=0;i<8;++i) {out[i]=m68k_get_reg(0,M68K_REG_D0+i);out[8+i]=m68k_get_reg(0,M68K_REG_A0+i);}
    out[16]=m68k_get_reg(0,M68K_REG_PC);out[17]=m68k_get_reg(0,M68K_REG_SR);
}
unsigned reference_machine_reset(cpu_read8 read,cpu_write8 write,void *ctx,uint32_t *out) {
    m68k_init();m68k_set_cpu_type(M68K_CPU_TYPE_68000);m68k_set_fc_callback(function_code);
    m68k_set_reg(M68K_REG_SR,0x2700);
    for(unsigned i=0;i<8;++i) {m68k_set_reg(M68K_REG_D0+i,0);m68k_set_reg(M68K_REG_A0+i,0);}
    m68k_set_reg(M68K_REG_USP,0);m68k_set_reg(M68K_REG_ISP,0);
    machine_read=read;machine_write=write;machine_context=ctx;machine_error=0;
    m68k_pulse_reset();m68k_execute(0);machine_registers(out);return machine_error;
}
unsigned reference_machine_step(uint32_t *out) {
    machine_error=0;m68k_execute(1);machine_registers(out);return machine_error;
}
unsigned reference_machine_run(unsigned budget,unsigned stop_pc,uint32_t *out) {
    machine_error=0;unsigned done=0;
    while(done<budget && m68k_get_reg(0,M68K_REG_PC)!=stop_pc && !machine_error) {m68k_execute(1);++done;}
    machine_registers(out);return done;
}
unsigned reference_machine_error(void) {return machine_error;}
unsigned reference_disassemble(char *out,unsigned pc) {return m68k_disassemble(out,pc,M68K_CPU_TYPE_68000);}
