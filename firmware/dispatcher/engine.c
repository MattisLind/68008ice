// SPDX-License-Identifier: Apache-2.0
// Shared PIO/DMA HAL. Core 1 owns these resources; core 0 owns USB/storage.
#include "engine.h"
#include "capture.h"
#include "bus_cycle.h"
#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/irq.h"
#include "hardware/pio.h"
#include "hardware/sync.h"
#include "hardware/timer.h"
#include "pico/stdlib.h"

static int data_dma, stop_dma, trigger_dma, alarm_num;
static bool bus_mode;
void engine_set_bus_mode(bool enabled) {bus_mode=enabled;}
static void dma_irq(void) {dma_hw->ints0=1u<<data_dma;}
static void timeout_irq(uint alarm) {(void)alarm;}

static void release(void) {
    capture_fast_release();
    pio_set_sm_mask_enabled(pio0,3,false);pio_set_sm_mask_enabled(pio1,1,false);
    dma_channel_abort(trigger_dma);dma_channel_abort(stop_dma);dma_channel_abort(data_dma);
    for (uint pin=0;pin<45;++pin) {
        if((bus_mode && pin>=28 && pin<=31) || pin==BENCH_RESET || pin==BENCH_HALT || pin==BENCH_BERR) {
            // Establish the inactive pull before releasing the pin function;
            // even a brief pull-down here looks like another bus cycle.
            gpio_pull_up(pin);gpio_init(pin);gpio_set_dir(pin,GPIO_IN);
        } else {gpio_init(pin);gpio_set_dir(pin,GPIO_IN);gpio_pull_down(pin);}
    }
}

static int prepare(app_job *j,uint32_t source) {
    engine_set_bus_mode(false);
    release();
    uint base=j->bank ? 32 : 0, width=j->bank ? 13 : 32;
    pio_clear_instruction_memory(pio0);pio_set_gpio_base(pio0,j->bank ? 16 : 0);
    uint16_t instruction=source ? pio_encode_out(pio_pins,32) : pio_encode_in(pio_pins,32);
    struct pio_program program={.instructions=&instruction,.length=1,.origin=0};
    if (pio_add_program_at_offset(pio0,&program,0)<0) {j->error=1;return 0;}
    pio_sm_config c=pio_get_default_sm_config();sm_config_set_clkdiv(&c,1);
    sm_config_set_wrap(&c,0,0);
    if (source) {
        sm_config_set_out_pins(&c,base,width);sm_config_set_out_shift(&c,true,true,32);
        sm_config_set_fifo_join(&c,PIO_FIFO_JOIN_TX);
    } else {
        sm_config_set_in_pins(&c,base);sm_config_set_in_pin_count(&c,width);
        sm_config_set_in_shift(&c,true,true,32);sm_config_set_fifo_join(&c,PIO_FIFO_JOIN_RX);
    }
    if (pio_sm_init(pio0,0,0,&c)!=PICO_OK) {j->error=1;return 0;}
    uint64_t mask=((UINT64_C(1)<<width)-1)<<base;
    pio_sm_set_pindirs_with_mask64(pio0,0,0,mask);
    pio_sm_set_pins_with_mask64(pio0,0,(j->flags&FLAG_INITIAL_HIGH) ? mask : 0,mask);
    for (uint pin=base;pin<base+width;++pin) {
        pio_gpio_init(pio0,pin);gpio_pull_down(pin);
        if (source) {
            gpio_set_drive_strength(pin,pin==39 ? GPIO_DRIVE_STRENGTH_8MA : GPIO_DRIVE_STRENGTH_4MA);
            gpio_set_slew_rate(pin,GPIO_SLEW_RATE_FAST);
        }
    }
    dma_channel_config d=dma_channel_get_default_config(data_dma);
    channel_config_set_transfer_data_size(&d,DMA_SIZE_32);channel_config_set_high_priority(&d,true);
    channel_config_set_read_increment(&d,source);channel_config_set_write_increment(&d,!source);
    channel_config_set_dreq(&d,pio_get_dreq(pio0,0,source));
    if (source) {
        pio_sm_set_pindirs_with_mask64(pio0,0,mask,mask);
        pio_sm_put(pio0,0,engine_api.pattern[0]);pio_sm_exec(pio0,0,pio_encode_pull(false,true));
        dma_channel_configure(data_dma,&d,&pio0->txf[0],engine_api.pattern+1,2047,true);
    } else {
        const uint16_t timer[]={pio_encode_jmp_x_dec(0),pio_encode_mov(pio_isr,pio_null),
                                pio_encode_push(false,true),pio_encode_jmp(3)};
        struct pio_program t={.instructions=timer,.length=4,.origin=1};
        pio_add_program_at_offset(pio0,&t,1);
        pio_sm_config tc=pio_get_default_sm_config();sm_config_set_wrap(&tc,4,4);
        pio_sm_init(pio0,1,1,&tc);
        pio_sm_put(pio0,1,1019);pio_sm_exec(pio0,1,pio_encode_pull(false,true));
        pio_sm_exec(pio0,1,pio_encode_mov(pio_x,pio_osr));
        dma_channel_configure(data_dma,&d,engine_api.samples,&pio0->rxf[0],1024,false);
        dma_channel_config sd=dma_channel_get_default_config(stop_dma);
        channel_config_set_read_increment(&sd,false);channel_config_set_write_increment(&sd,false);
        channel_config_set_dreq(&sd,pio_get_dreq(pio0,1,false));
        dma_channel_configure(stop_dma,&sd,&pio0->ctrl,&pio0->rxf[1],1,false);
        // A separate PIO block can observe any GPIO0..44, including a GPIO
        // outside the capture window. Its one-shot DMA starts both sampler
        // state machines in a single CTRL write. No GPIO output is required.
        pio_clear_instruction_memory(pio1);pio_set_gpio_base(pio1,j->trigger_gpio>=32 ? 16 : 0);
        uint16_t trigger[]={pio_encode_wait_gpio(j->trigger_level,j->trigger_gpio&31),
                           pio_encode_mov(pio_isr,pio_osr),pio_encode_push(false,true),pio_encode_jmp(3)};
        struct pio_program tp={.instructions=trigger,.length=4,.origin=0};
        pio_add_program_at_offset(pio1,&tp,0);
        pio_sm_config tr=pio_get_default_sm_config();sm_config_set_wrap(&tr,3,3);
        pio_sm_init(pio1,0,0,&tr);pio_sm_put(pio1,0,3);
        pio_sm_exec(pio1,0,pio_encode_pull(false,true));
        dma_channel_config td=dma_channel_get_default_config(trigger_dma);
        channel_config_set_read_increment(&td,false);channel_config_set_write_increment(&td,false);
        channel_config_set_dreq(&td,pio_get_dreq(pio1,0,false));
        dma_channel_configure(trigger_dma,&td,&pio0->ctrl,&pio1->rxf[0],1,false);
    }
    pio0->fdebug=PIO_FDEBUG_BITS;pio1->fdebug=PIO_FDEBUG_BITS;
    j->hz=clock_get_hz(clk_sys);j->samples=1024;
    return 1;
}

static int wait_start(app_job *j) {
    absolute_time_t deadline=make_timeout_time_ms(j->timeout_ms);
    while (!j->start && !j->abort && !time_reached(deadline))sleep_us(100);
    if (j->abort)j->error=ERR_ABORT;
    else if (!j->start)j->error=2;
    return j->error==0;
}

static int transfer(app_job *j,uint32_t source) {
    dma_hw->ints0=1u<<data_dma;irq_clear(DMA_IRQ_0);
    absolute_time_t deadline=make_timeout_time_ms(source ? 10 : j->timeout_ms);
    hardware_alarm_set_target(alarm_num,deadline);
    uint32_t irq=save_and_disable_interrupts();
    if (source)pio_sm_set_enabled(pio0,0,true);
    else {
        dma_start_channel_mask((1u<<data_dma)|(1u<<stop_dma)|(1u<<trigger_dma));
        pio_sm_set_enabled(pio1,0,true);
    }
    while (dma_channel_is_busy(data_dma) && !j->abort && !time_reached(deadline))__wfi();
    hardware_alarm_cancel(alarm_num);
    j->remaining=dma_hw->ch[data_dma].transfer_count;
    if (source)busy_wait_us_32(5);
    else if (!j->remaining) {
        while (dma_channel_is_busy(stop_dma) && !time_reached(deadline))tight_loop_contents();
    }
    pio_set_sm_mask_enabled(pio0,3,false);
    j->fdebug=pio0->fdebug;
    restore_interrupts(irq);
    if (j->abort)j->error=ERR_ABORT;
    else if (j->remaining)j->error=2;
    else if (!source && j->fdebug)j->error=3;
    return j->error==0;
}

// Keep the legacy full-rate finite buffer in dedicated scratch bank 8.
// Continuous capture has its own larger DMA ring in capture.c.
const app_api engine_api={APP_ABI,(uint32_t *)0x20080000,(uint32_t *)0x20050000,
                         prepare,transfer,wait_start,release,capture_run};
void engine_init(void) {
    data_dma=dma_claim_unused_channel(true);stop_dma=dma_claim_unused_channel(true);
    capture_init(data_dma);
    trigger_dma=dma_claim_unused_channel(true);
    irq_set_exclusive_handler(DMA_IRQ_0,dma_irq);dma_channel_set_irq0_enabled(data_dma,true);
    irq_set_enabled(DMA_IRQ_0,true);
    alarm_num=hardware_alarm_claim_unused(true);hardware_alarm_set_callback(alarm_num,timeout_irq);
    release();
}
