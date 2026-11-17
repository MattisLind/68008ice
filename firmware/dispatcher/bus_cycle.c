// SPDX-License-Identifier: Apache-2.0
#include "bus_cycle.h"
#include "capture.h"
#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/pio.h"
#include "pico/stdlib.h"
#define ADDRESS_MASK 0xfffffu
#define DATA_MASK 0x0ff00000u
#define AS (1u<<28)
#define DS (1u<<29)
#define RW (1u<<30)
#define CONTROLS (AS|DS|RW)
static int cycle_dma;

void bus_cycle_prepare(int dma) {
    cycle_dma=dma;
    // Identical S0..S7 sequencer for the diagnostic generator and CPU.
    const uint16_t program[]={
        pio_encode_out(pio_pins,32)|pio_encode_delay(7),
        pio_encode_out(pio_pins,32)|pio_encode_delay(7),
        pio_encode_out(pio_pins,32)|pio_encode_delay(7),
        pio_encode_out(pio_pindirs,32),
        pio_encode_out(pio_pins,32)|pio_encode_delay(6),
        pio_encode_out(pio_pins,32)|pio_encode_delay(7),
        pio_encode_jmp_pin(8),pio_encode_jmp(10)|pio_encode_delay(6),
        pio_encode_nop()|pio_encode_delay(13),pio_encode_jmp(6),
        pio_encode_nop()|pio_encode_delay(7),pio_encode_in(pio_pins,32),
        pio_encode_out(pio_pins,32)|pio_encode_delay(4),
        pio_encode_out(pio_pindirs,32),pio_encode_out(pio_pins,32)};
    pio_clear_instruction_memory(pio0);pio_set_gpio_base(pio0,0);
    struct pio_program p={.instructions=program,.length=15,.origin=0};
    pio_add_program_at_offset(pio0,&p,0);
    pio_sm_config c=pio_get_default_sm_config();sm_config_set_wrap(&c,0,14);
    sm_config_set_out_pins(&c,0,31);sm_config_set_in_pins(&c,0);sm_config_set_in_pin_count(&c,32);
    sm_config_set_out_shift(&c,true,true,32);sm_config_set_in_shift(&c,true,true,32);
    sm_config_set_jmp_pin(&c,31);sm_config_set_clkdiv(&c,(float)clock_get_hz(clk_sys)/128000000);
    pio_sm_init(pio0,0,0,&c);
    pio_sm_set_pins_with_mask(pio0,0,CONTROLS,UINT32_MAX);
    pio_sm_set_pindirs_with_mask(pio0,0,ADDRESS_MASK|CONTROLS,UINT32_MAX);
    for(uint pin=0;pin<31;++pin)pio_gpio_init(pio0,pin);
    gpio_pull_up(31);
}

void bus_cycle_release(void) {
    pio_sm_set_enabled(pio0,0,false);dma_channel_abort(cycle_dma);
    pio_sm_set_pins_with_mask(pio0,0,CONTROLS,CONTROLS);
    pio_sm_set_pindirs_with_mask(pio0,0,0,UINT32_MAX);
}

static int pending(app_job *j,uint64_t end,bool cpu_signals) {
    if(j->abort || capture_stop)return CPU_BUS_ABORT;
    if(cpu_signals) {
        if(!gpio_get(BENCH_RESET))return CPU_BUS_RESET;
        if(!gpio_get(BENCH_BERR))return CPU_BUS_BERR;
        if(!gpio_get(BENCH_HALT))return CPU_BUS_HALT;
    }
    return time_us_64()>=end ? CPU_BUS_TIMEOUT : CPU_BUS_OK;
}

int bus_cycle_transfer(app_job *j,uint32_t address,bool write,uint8_t *data,uint64_t deadline,bool cpu_signals) {
    uint32_t addr=address&ADDRESS_MASK;
    uint32_t s2=addr|(write ? DS : RW),s3=s2|(write ? (uint32_t)*data<<20 : 0);
    uint32_t words[]={CONTROLS,addr|CONTROLS,s2,ADDRESS_MASK|CONTROLS|(write ? DATA_MASK : 0),
        s3,s3&~DS,addr|AS|DS|(write ? (uint32_t)*data<<20 : RW),ADDRESS_MASK|CONTROLS,addr|CONTROLS};
    uint64_t end=time_us_64()+capture_settings.cycle_timeout_us;
    if(end>deadline)end=deadline;
    int status;
    while(!gpio_get(31)) {
        status=pending(j,end,cpu_signals);if(status)return status;
        tight_loop_contents();
    }
    status=pending(j,end,cpu_signals);if(status)return status;
    pio_sm_set_enabled(pio0,0,false);pio0->fdebug=PIO_FDEBUG_BITS;
    dma_channel_config d=dma_channel_get_default_config(cycle_dma);
    channel_config_set_transfer_data_size(&d,DMA_SIZE_32);channel_config_set_read_increment(&d,true);
    channel_config_set_write_increment(&d,false);channel_config_set_dreq(&d,pio_get_dreq(pio0,0,true));
    dma_channel_configure(cycle_dma,&d,&pio0->txf[0],words,9,true);
    pio_sm_set_enabled(pio0,0,true);
    while(pio_sm_is_rx_fifo_empty(pio0,0) || !(pio0->fdebug&(1u<<PIO_FDEBUG_TXSTALL_LSB))) {
        status=pending(j,end,cpu_signals);
        if(status) {bus_cycle_release();return status;}
        tight_loop_contents();
    }
    uint32_t value=pio_sm_get(pio0,0);
    if(!write)*data=(value>>20)&255;
    return CPU_BUS_OK;
}
