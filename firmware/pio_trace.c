// SPDX-License-Identifier: Apache-2.0
// Standalone Core2350B bench only: bank 0 GPIO0..31, bank 1 GPIO32..44.
// Board 1 generates, board 2 captures. One bank at a time; no 45-bit claim.
#include <stdint.h>
#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/irq.h"
#include "hardware/pio.h"
#include "hardware/structs/powman.h"
#include "hardware/sync.h"
#include "hardware/watchdog.h"
#include "hardware/timer.h"
#include "pico/stdlib.h"
#include "pico/unique_id.h"
#include "trace_store.h"
#if ICE_SWD_INSTANCE_ID == 2
#include "trace_usb.h"
#endif

#define SOURCE (ICE_SWD_INSTANCE_ID == 1)
#define PATTERN_SAMPLES 2048u
typedef struct {
    uint32_t magic,version,request_seq,completed_seq,command,bank,state,error;
    uint32_t sys_hz,samples,fdebug,dma_remaining,vcd_bytes,vcd_crc,sample_crc,captures;
} trace_mailbox;
volatile trace_mailbox trace_control={.magic=0x50494f31,.version=1,.samples=TRACE_SAMPLES};
char board_id[PICO_UNIQUE_BOARD_ID_SIZE_BYTES*2+1];
uint32_t trace_samples[TRACE_SAMPLES] __attribute__((aligned(4096)));
#if ICE_SWD_INSTANCE_ID == 1
static uint32_t pattern[PATTERN_SAMPLES] __attribute__((aligned(4096)));
#endif
static int data_dma,stop_dma;
static int transfer_alarm;
#if ICE_SWD_INSTANCE_ID == 1
static absolute_time_t source_lease;
#endif
static PIO const pio=pio0;
static bool saved_irqs[NUM_IRQS];
static void dma_done_irq(void) {dma_hw->ints0=1u<<data_dma;}
static void transfer_timeout_irq(uint alarm) {(void)alarm;}

static uint32_t capture_irq_enter(void) {
    uint32_t state=save_and_disable_interrupts();
    // An unrelated pending USB/timer IRQ would make WFI return immediately
    // while PRIMASK is set. Keep only our completion and timeout wake sources.
    for(uint irq=0;irq<NUM_IRQS;++irq) {saved_irqs[irq]=irq_is_enabled(irq);irq_set_enabled(irq,false);}
    irq_set_enabled(DMA_IRQ_0,true);
    irq_set_enabled(hardware_alarm_get_irq_num(transfer_alarm),true);
    return state;
}
static void capture_irq_leave(uint32_t state) {
    for(uint irq=0;irq<NUM_IRQS;++irq)irq_set_enabled(irq,saved_irqs[irq]);
    restore_interrupts(state);
}

static void release_pins(void) {
    pio_set_sm_mask_enabled(pio,3,false);
    uint64_t pio_mask=UINT64_C(0xffffffff)<<pio_get_gpio_base(pio);
    pio_sm_set_pindirs_with_mask64(pio,0,0,pio_mask);
    for(uint pin=0;pin<45;++pin) {
        gpio_init(pin);gpio_set_dir(pin,GPIO_IN);gpio_pull_down(pin);
    }
}

static void stop_transfer(void) {
    pio_set_sm_mask_enabled(pio,3,false);
    dma_channel_abort(data_dma);
    dma_channel_abort(stop_dma);
    release_pins();
}

static bool setup(unsigned bank) {
    stop_transfer();
    if(bank>1)return false;
    uint base=bank ? 32 : 0,width=bank ? 13 : 32;
    pio_clear_instruction_memory(pio);
    if(pio_set_gpio_base(pio,bank ? 16 : 0)!=PICO_OK)return false;
    uint16_t instructions[3];
    unsigned length;
    if(SOURCE) {instructions[0]=pio_encode_out(pio_pins,32);length=1;}
    else {
        // The SDK relocates WAIT GPIO for GPIOBASE when adding the program.
        uint trigger=base&31u;
        instructions[0]=pio_encode_wait_gpio(false,trigger);
        instructions[1]=pio_encode_wait_gpio(true,trigger);
        instructions[2]=pio_encode_in(pio_pins,32);length=3;
    }
    struct pio_program program={.instructions=instructions,.length=length,.origin=0};
    pio_add_program_at_offset(pio,&program,0);
    pio_sm_config config=pio_get_default_sm_config();
    sm_config_set_clkdiv(&config,1.0f);
    if(SOURCE) {
        sm_config_set_out_pins(&config,base,width);
        sm_config_set_out_shift(&config,true,true,32);
        sm_config_set_fifo_join(&config,PIO_FIFO_JOIN_TX);
        sm_config_set_wrap(&config,0,0);
    } else {
        sm_config_set_in_pins(&config,base);
        sm_config_set_in_pin_count(&config,width);
        sm_config_set_in_shift(&config,true,true,32);
        sm_config_set_fifo_join(&config,PIO_FIFO_JOIN_RX);
        sm_config_set_wrap(&config,2,2);
    }
    if(pio_sm_init(pio,0,0,&config)!=PICO_OK)return false;
#if ICE_SWD_INSTANCE_ID == 2
    // A second SM emits a delayed zero to RX1. Its DMA writes CTRL=0 just
    // after the 1024th sample, avoiding a CPU stop and trailing FIFO overflow.
    // Both SMs wait on the same trigger and start on the same PIO clock.
    uint trigger=base&31u;
    const uint16_t timer_instructions[]={
        pio_encode_wait_gpio(false,trigger),pio_encode_wait_gpio(true,trigger),
        // JMP targets are relative to this program's load address (3).
        pio_encode_jmp_x_dec(2),pio_encode_mov(pio_isr,pio_null),
        pio_encode_push(false,true),pio_encode_jmp(5),
    };
    struct pio_program timer_program={.instructions=timer_instructions,.length=6,.origin=3};
    pio_add_program_at_offset(pio,&timer_program,3);
    pio_sm_config timer_config=pio_get_default_sm_config();
    sm_config_set_clkdiv(&timer_config,1.0f);sm_config_set_wrap(&timer_config,8,8);
    if(pio_sm_init(pio,1,3,&timer_config)!=PICO_OK)return false;
    pio_sm_put(pio,1,1019);pio_sm_exec(pio,1,pio_encode_pull(false,true));
    pio_sm_exec(pio,1,pio_encode_mov(pio_x,pio_osr));
#endif
    pio_sm_set_pindirs_with_mask64(pio,0,0,UINT64_C(0xffffffff)<<pio_get_gpio_base(pio));
    pio_sm_set_pins_with_mask64(pio,0,0,((UINT64_C(1)<<width)-1)<<base);
    for(uint pin=base;pin<base+width;++pin) {
        pio_gpio_init(pio,pin);gpio_pull_down(pin);
        if(SOURCE) {
            gpio_set_drive_strength(pin,pin==39 ? GPIO_DRIVE_STRENGTH_8MA : GPIO_DRIVE_STRENGTH_4MA);
            gpio_set_slew_rate(pin,GPIO_SLEW_RATE_FAST);
        }
    }
    pio->fdebug=PIO_FDEBUG_BITS;
    trace_control.fdebug=0;trace_control.error=0;trace_control.dma_remaining=0;
    trace_control.sys_hz=clock_get_hz(clk_sys);
    trace_control.vcd_bytes=0;trace_control.vcd_crc=0;trace_control.sample_crc=0;
    return true;
}

#if ICE_SWD_INSTANCE_ID == 1
static bool prepare_source(unsigned bank) {
    if(!setup(bank))return false;
    unsigned width=bank ? 13 : 32;uint32_t value=0;
    for(unsigned i=0;i<PATTERN_SAMPLES;++i) {value^=1u<<(i%width);pattern[i]=value;}
    pio_sm_set_consecutive_pindirs(pio,0,bank ? 32 : 0,width,true);
    pio_sm_put(pio,0,pattern[0]);
    pio_sm_exec(pio,0,pio_encode_pull(false,true));
    dma_channel_config c=dma_channel_get_default_config(data_dma);
    channel_config_set_transfer_data_size(&c,DMA_SIZE_32);
    channel_config_set_read_increment(&c,true);channel_config_set_write_increment(&c,false);
    channel_config_set_dreq(&c,pio_get_dreq(pio,0,true));channel_config_set_high_priority(&c,true);
    dma_channel_configure(data_dma,&c,&pio->txf[0],pattern+1,PATTERN_SAMPLES-1,true);
    source_lease=make_timeout_time_ms(2000);
    return true;
}
static bool run_source(void) {
    dma_hw->ints0=1u<<data_dma;irq_clear(DMA_IRQ_0);
    absolute_time_t deadline=make_timeout_time_ms(10);
    hardware_alarm_set_target(transfer_alarm,deadline);
    uint32_t irq=capture_irq_enter();
    pio->fdebug=PIO_FDEBUG_BITS;
    pio_sm_set_enabled(pio,0,true);
    while(dma_channel_is_busy(data_dma) && !time_reached(deadline))__wfi();
    hardware_alarm_cancel(transfer_alarm);
    trace_control.dma_remaining=dma_hw->ch[data_dma].transfer_count;
    busy_wait_us_32(5); // FIFO drains; terminal TX stall holds the last output.
    trace_control.fdebug=pio->fdebug;
    pio_sm_set_enabled(pio,0,false);
    capture_irq_leave(irq);
    stop_transfer();
    return trace_control.dma_remaining==0;
}
#else
static bool receive(unsigned bank,uint32_t request) {
    if(!setup(bank))return false;
    trace_usb_detach();
    dma_channel_config c=dma_channel_get_default_config(data_dma);
    channel_config_set_transfer_data_size(&c,DMA_SIZE_32);
    channel_config_set_read_increment(&c,false);channel_config_set_write_increment(&c,true);
    channel_config_set_dreq(&c,pio_get_dreq(pio,0,false));channel_config_set_high_priority(&c,true);
    dma_channel_config stop=dma_channel_get_default_config(stop_dma);
    channel_config_set_transfer_data_size(&stop,DMA_SIZE_32);
    channel_config_set_read_increment(&stop,false);channel_config_set_write_increment(&stop,false);
    channel_config_set_high_priority(&stop,true);
    channel_config_set_dreq(&stop,pio_get_dreq(pio,1,false));
    dma_channel_configure(stop_dma,&stop,&pio->ctrl,&pio->rxf[1],1,false);
    dma_channel_configure(data_dma,&c,trace_samples,&pio->rxf[0],TRACE_SAMPLES,false);
    dma_hw->ints0=1u<<data_dma;irq_clear(DMA_IRQ_0);
    absolute_time_t deadline=make_timeout_time_ms(2000);
    hardware_alarm_set_target(transfer_alarm,deadline);
    uint32_t irq=capture_irq_enter();
    dma_start_channel_mask((1u<<data_dma)|(1u<<stop_dma));
    pio_enable_sm_mask_in_sync(pio,3);
    trace_control.state=1;trace_control.completed_seq=request;
    // Sleep rather than polling SRAM: a CPU mailbox load can otherwise steal
    // a bank cycle from the one-word-per-clock DMA stream and create gaps.
    while(dma_channel_is_busy(data_dma) && !time_reached(deadline))__wfi();
    hardware_alarm_cancel(transfer_alarm);
    trace_control.dma_remaining=dma_hw->ch[data_dma].transfer_count;
    while(dma_channel_is_busy(stop_dma) && !time_reached(deadline))tight_loop_contents();
    pio_sm_set_enabled(pio,0,false);
    trace_control.fdebug=pio->fdebug;
    capture_irq_leave(irq);
    stop_transfer();
    if(trace_control.dma_remaining) {trace_control.error=2;trace_usb_attach();return false;}
    trace_control.state=2;
    uint32_t mask=bank ? 0x1fffu : UINT32_MAX;
    for(unsigned i=0;i<TRACE_SAMPLES;++i)trace_samples[i]&=mask;
    trace_control.sample_crc=trace_crc32(trace_samples,sizeof trace_samples);
    bool saved=trace_store_save(bank,trace_samples,trace_control.sys_hz,trace_control.fdebug);
    if(saved) {
        const trace_record *record=trace_record_get(bank);
        trace_control.vcd_bytes=record->bytes;trace_control.vcd_crc=record->crc32;
        ++trace_control.captures;
    } else trace_control.error=3;
    trace_usb_attach();return saved;
}
#endif

int main(void) {
    powman_hw->dbgconfig=POWMAN_PASSWORD_BITS|ICE_SWD_INSTANCE_ID;
    pico_get_unique_board_id_string(board_id,sizeof board_id);
    data_dma=dma_claim_unused_channel(true);stop_dma=dma_claim_unused_channel(true);
    irq_set_exclusive_handler(DMA_IRQ_0,dma_done_irq);
    dma_channel_set_irq0_enabled(data_dma,true);irq_set_enabled(DMA_IRQ_0,true);
    transfer_alarm=hardware_alarm_claim_unused(true);
    hardware_alarm_set_callback(transfer_alarm,transfer_timeout_irq);
    release_pins();
#if ICE_SWD_INSTANCE_ID == 1
    stdio_init_all();
#else
    trace_usb_init();
#endif
    while(true) {
#if ICE_SWD_INSTANCE_ID == 2
        trace_usb_task();
#else
        if(trace_control.state==1 && time_reached(source_lease)) {stop_transfer();trace_control.state=0;}
#endif
        uint32_t request=trace_control.request_seq;
        if(request!=trace_control.completed_seq) {
            uint32_t command=trace_control.command;
            bool ok=false;trace_control.error=0;
            if(command==1) {
#if ICE_SWD_INSTANCE_ID == 1
                ok=prepare_source(trace_control.bank);trace_control.state=ok ? 1 : 4;
#else
                ok=receive(trace_control.bank,request);trace_control.state=ok ? 3 : 4;
#endif
            } else if(command==2 && SOURCE && trace_control.state==1) {
#if ICE_SWD_INSTANCE_ID == 1
                ok=run_source();trace_control.state=ok ? 3 : 4;
#endif
            } else if(command==3) {stop_transfer();trace_control.state=0;ok=true;}
            else if(command==4) {
                stop_transfer();trace_control.completed_seq=request;sleep_ms(250);
                watchdog_reboot(0,0,10);while(true)tight_loop_contents();
            }
            if(!ok && !trace_control.error)trace_control.error=1;
            trace_control.completed_seq=request;
        }
    }
}
