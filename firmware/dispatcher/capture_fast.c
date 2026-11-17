// SPDX-License-Identifier: Apache-2.0
// Memory responder plus a full-rate, hardware-triggered circular timing trace.
#include <string.h>
#include "capture.h"
#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/pio.h"
#include "hardware/structs/sio.h"
#include "hardware/structs/bus_ctrl.h"
#include "hardware/structs/systick.h"
#include "hardware/sync.h"
#include "hardware/timer.h"
#include "pico/stdlib.h"

#define AS (1u<<28)
#define DS (1u<<29)
#define RW (1u<<30)
#define ACK (1u<<31)
#define DATA 0x0ff00000u
#define WORDS 8192u
static uint32_t *const samples=(uint32_t *)0x20040000;
static uint32_t *const saved=(uint32_t *)0x11040000;
static int data_dma,stop_dma,done_dma;
static uint32_t done_value=1;
static volatile uint32_t capture_done;
static bool initialized;
volatile uint32_t capture_fast_debug[12]; // stopped acquisition diagnostics

void capture_fast_init(int dma) {
    data_dma=dma;stop_dma=dma_claim_unused_channel(true);
    done_dma=dma_claim_unused_channel(true);
    initialized=true;
}
void capture_fast_release(void) {
    if(!initialized)return;
    pio_set_sm_mask_enabled(pio1,3,false);
    pio_set_sm_mask_enabled(pio2,1,false);
    dma_channel_abort(stop_dma);
    dma_channel_abort(done_dma);
}

static bool setup(uint32_t post,uint32_t pin,uint32_t level) {
    pio_clear_instruction_memory(pio0);pio_set_gpio_base(pio0,0);
    const uint16_t sample[]={pio_encode_in(pio_pins,32)};
    // JMP operands are program-relative; the SDK adds load offset 1.
    const uint16_t timer[]={pio_encode_jmp_x_dec(0),pio_encode_wait_gpio(!level,pin),
        pio_encode_wait_gpio(level,pin),pio_encode_mov(pio_x,pio_y),pio_encode_jmp_x_dec(4),
        pio_encode_mov(pio_isr,pio_null),pio_encode_push(false,true),pio_encode_jmp(7)};
    struct pio_program s={.instructions=sample,.length=1,.origin=0};
    struct pio_program t={.instructions=timer,.length=8,.origin=1};
    pio_add_program_at_offset(pio0,&s,0);pio_add_program_at_offset(pio0,&t,1);
    pio_sm_config c=pio_get_default_sm_config();
    sm_config_set_wrap(&c,0,0);sm_config_set_in_pins(&c,0);sm_config_set_in_pin_count(&c,32);
    sm_config_set_in_shift(&c,true,true,32);sm_config_set_fifo_join(&c,PIO_FIFO_JOIN_RX);
    if(pio_sm_init(pio0,0,0,&c)!=PICO_OK)return false;
    pio_sm_config tc=pio_get_default_sm_config();sm_config_set_wrap(&tc,8,8);
    pio_sm_init(pio0,1,1,&tc);
    // Capture extra samples after the requested window. Once stopped, locate
    // the actual sampled edge; DMA/PIO trigger latency never shifts midpoint.
    pio_sm_put(pio0,1,capture_settings.capacity+128);pio_sm_exec(pio0,1,pio_encode_pull(false,true));
    pio_sm_exec(pio0,1,pio_encode_mov(pio_x,pio_osr));
    pio_sm_put(pio0,1,post+64);pio_sm_exec(pio0,1,pio_encode_pull(false,true));
    pio_sm_exec(pio0,1,pio_encode_mov(pio_y,pio_osr));
    capture_fast_debug[11]=post+64;
    // CPU authorizes only decoded addresses, after read data has been driven.
    // PIO then acknowledges DS without a CPU polling delay, and releases on AS.
    // GPIO32 is a local SIO->PIO permit. It avoids a CPU peripheral-bus write
    // while PIO0's full-rate DMA owns that bus. Source GPIO32 remains input.
    const uint16_t ack[]={pio_encode_wait_gpio(1,0),pio_encode_wait_gpio(0,29),
        pio_encode_set(pio_pins,0),pio_encode_wait_gpio(1,28),pio_encode_set(pio_pins,1),
        pio_encode_wait_gpio(0,0)};
    struct pio_program a={.instructions=ack,.length=6,.origin=0};
    pio_clear_instruction_memory(pio2);pio_set_gpio_base(pio2,16);pio_add_program_at_offset(pio2,&a,0);
    pio_sm_config ac=pio_get_default_sm_config();sm_config_set_wrap(&ac,0,5);
    sm_config_set_set_pins(&ac,31,1);pio_sm_init(pio2,0,0,&ac);
    pio_sm_set_pins_with_mask(pio2,0,ACK,ACK);pio_sm_set_pindirs_with_mask(pio2,0,ACK,ACK);
    pio_gpio_init(pio2,31);
    gpio_init(32);gpio_put(32,0);gpio_set_dir(32,GPIO_OUT);

    dma_channel_config d=dma_channel_get_default_config(data_dma);
    channel_config_set_transfer_data_size(&d,DMA_SIZE_32);channel_config_set_high_priority(&d,true);
    channel_config_set_read_increment(&d,false);channel_config_set_write_increment(&d,true);
    channel_config_set_ring(&d,true,15);channel_config_set_dreq(&d,pio_get_dreq(pio0,0,false));
    dma_channel_configure(data_dma,&d,samples,&pio0->rxf[0],dma_encode_endless_transfer_count(),true);
    dma_channel_config td=dma_channel_get_default_config(stop_dma);
    channel_config_set_high_priority(&td,true);
    channel_config_set_read_increment(&td,false);channel_config_set_write_increment(&td,false);
    channel_config_set_dreq(&td,pio_get_dreq(pio0,1,false));
    channel_config_set_chain_to(&td,done_dma);
    dma_channel_configure(stop_dma,&td,&pio0->ctrl,&pio0->rxf[1],1,true);
    dma_channel_config dd=dma_channel_get_default_config(done_dma);
    channel_config_set_high_priority(&dd,true);
    channel_config_set_read_increment(&dd,false);channel_config_set_write_increment(&dd,false);
    capture_done=0;
    dma_channel_configure(done_dma,&dd,&capture_done,&done_value,1,false);
    pio0->fdebug=PIO_FDEBUG_BITS;pio1->fdebug=PIO_FDEBUG_BITS;
    return true;
}

// All instructions/data used for bus response stay outside the sampler's SRAM
// banks. Core 0 and its USB IRQ stay quiet until this worker releases sampling.
static uint32_t __attribute__((noinline)) __not_in_flash_func(memory_loop)(app_job *j,uint32_t base) {
    uint32_t polls=0,flags=0,pins,last=systick_hw->cvr;
    uint64_t elapsed=0;
    bool activity=false;
    while(true) {
        pins=sio_hw->gpio_in;
        if(!(pins&AS)) {
            capture_fast_debug[0]=1;capture_fast_debug[2]=pins;
            uint32_t offset=(pins&0xfffffu)-base;
            if(offset<1024) {
                bool reading=(sio_hw->gpio_in&RW)!=0;
                if(reading) {
                    sio_hw->gpio_clr=DATA;
                    sio_hw->gpio_set=(uint32_t)capture_memory[offset]<<20;
                    sio_hw->gpio_oe_set=DATA;
                }
                sio_hw->gpio_hi_set=1; // GPIO32: authorize PIO DTACK
                uint32_t cycle=systick_hw->cvr;
                capture_fast_debug[0]=2;
                while((pins=sio_hw->gpio_in)&DS) {
                    if((++polls&63)==0 &&
                       (((cycle-systick_hw->cvr)&0xffffffu)>=capture_settings.cycle_timeout_us*150 || j->abort)) {
                        j->error=j->abort ? ERR_ABORT : 2;return flags;
                    }
                }
                if(!reading)capture_memory[offset]=(pins>>20)&255;
                capture_fast_debug[0]=3;capture_fast_debug[2]=pins;
                while(!(sio_hw->gpio_in&AS)) {
                    if((++polls&63)==0 &&
                       (((cycle-systick_hw->cvr)&0xffffffu)>=capture_settings.cycle_timeout_us*150 || j->abort)) {
                        j->error=j->abort ? ERR_ABORT : 2;return flags;
                    }
                }
                // Hold read data past strobe release for the timing trace.
                for(unsigned hold=0;hold<16;++hold)__asm volatile("nop");
                sio_hw->gpio_oe_clr=DATA;
                sio_hw->gpio_hi_clr=1;
                capture_fast_debug[0]=4;++capture_fast_debug[1];
            }
            activity=true;
        }
        if((++polls&255)==0) {
            uint32_t now=systick_hw->cvr;
            elapsed+=(last-now)&0xffffffu;last=now;
            if(j->abort) {j->error=ERR_ABORT;break;}
            if(capture_stop) {flags=CAPTURE_STOPPED;break;}
            if(elapsed>=(uint64_t)j->timeout_ms*150000) {flags=CAPTURE_TIMEOUT;break;}
            // The DMA completion flag is in SRAM. Polling DMA/PIO registers
            // here would contend with the full-rate peripheral read master.
            if(activity && capture_done)break;
        }
    }
    return flags;
}

int capture_fast_run(app_job *j) {
    const capture_config *c=&capture_settings;
    for(unsigned i=0;i<12;++i)capture_fast_debug[i]=0;
    if(clock_get_hz(clk_sys)!=CAPTURE_FAST_HZ) {j->error=1;return 1;}
    uint32_t pre=c->capacity*c->pre_percent/100;
    if(!setup(c->capacity-pre,c->strobe ? 28 : 29,c->edge)) {j->error=1;return 1;}
    memset(capture_memory,0,sizeof capture_memory);
    j->hz=CAPTURE_FAST_HZ;j->state=JOB_ARMED;__dmb();
    absolute_time_t deadline=make_timeout_time_ms(j->timeout_ms);
    while(!j->start && !j->abort && !capture_stop && !time_reached(deadline))tight_loop_contents();
    uint32_t flags=0,count=0;
    if(j->abort) {j->error=ERR_ABORT;return 1;}
    if(!j->start)flags=capture_stop ? CAPTURE_STOPPED : CAPTURE_TIMEOUT;
    uint32_t priority=bus_ctrl_hw->priority,irq=save_and_disable_interrupts();
    if(!flags) {
        systick_hw->csr=0;systick_hw->rvr=0xffffff;systick_hw->cvr=0;systick_hw->csr=5;
        pio_sm_set_enabled(pio2,0,true);
        bus_ctrl_hw->priority=BUSCTRL_BUS_PRIORITY_DMA_R_BITS|BUSCTRL_BUS_PRIORITY_DMA_W_BITS;
        pio_set_sm_mask_enabled(pio0,3,true); // sampler and edge timer start together
        flags=memory_loop(j,c->memory_base);
        count=c->capacity;
    }
    systick_hw->csr=0;
    // On a trigger the hardware has already stopped PIO. On timeout, release
    // DMA bus priority first so the CPU can reach PIO's stop register.
    bus_ctrl_hw->priority=priority;__dmb();
    pio_set_sm_mask_enabled(pio0,3,false);pio_set_sm_mask_enabled(pio1,3,false);
    dma_channel_abort(data_dma);
    uint32_t end=(dma_hw->ch[data_dma].write_addr-(uintptr_t)samples)/4;
    j->fdebug=pio0->fdebug;
    uint32_t snapshot=(end+WORDS-(c->capacity-pre)-64)&(WORDS-1);
    capture_fast_debug[3]=snapshot;capture_fast_debug[4]=end;capture_fast_debug[5]=j->fdebug;
    capture_fast_debug[6]=pio0->sm[1].addr;capture_fast_debug[7]=pio2->sm[0].addr;
    capture_fast_debug[8]=pio0->ctrl;
    capture_fast_debug[9]=dma_hw->ch[stop_dma].transfer_count;
    capture_fast_debug[10]=dma_hw->ch[stop_dma].ctrl_trig;
    restore_interrupts(irq);capture_fast_release();
    if(j->fdebug && !j->error)j->error=3;
    if(j->error)return 1;
    uint32_t start=(end+WORDS-count)&(WORDS-1),trigger=CAPTURE_NO_TRIGGER;
    if(capture_done && !flags) {
        if(!capture_timing_window(samples,WORDS,snapshot,end,c->capacity,pre,
                                  c->strobe ? 28 : 29,c->edge,&start)) {j->error=3;return 1;}
        trigger=pre;flags|=CAPTURE_TRIGGERED;
    }
    for(uint32_t i=0;i<count;++i)saved[i]=samples[(start+i)&(WORDS-1)];
    j->samples=count;j->remaining=c->capacity-count;
    capture_result=(capture_record){.magic=CAPTURE_MAGIC,.version=1,.committed=UINT32_MAX,
        .bank=0,.app=APP_BUS_MEMORY,.count=count,.stride=4,.hz=CAPTURE_FAST_HZ,
        .trigger=trigger,.flags=flags|CAPTURE_MEMORY_TIMING,.bytes=count*4,
        .capacity=c->capacity,.pre_percent=c->pre_percent,.reserved=0};
    return 1;
}
