// SPDX-License-Identifier: Apache-2.0
// Bench-only bus HAL and continuous capture. GPIO31 is DTACK on this fixture.
#include <string.h>
#include "capture.h"
#include "engine.h"
#include "bus_cycle.h"
#include "cpu_fixture.h"
#include "memory_image.h"
#include "generic_memory.h"
#include "abc1600_memory.h"
#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/pio.h"
#include "hardware/sync.h"
#include "pico/stdlib.h"

#define ADDRESS_MASK 0xfffffu
#define DATA_MASK 0x0ff00000u
#define AS (1u<<28)
#define DS (1u<<29)
#define RW (1u<<30)
#define ACK (1u<<31)
#define CONTROLS (AS|DS|RW)
#define DMA_WORDS 8192u
#define DMA_TRANSFERS 0x0fffffffu
#define FLAG_WRITES 4u
static volatile uint32_t *const acquisition=(volatile uint32_t *)0x20040000;
static uint32_t *const records=(uint32_t *)0x11040000;
static int sample_dma;
capture_config capture_settings;
capture_record capture_result;
volatile uint32_t capture_stop;
uint8_t capture_memory[1024];

void capture_init(int dma) {sample_dma=dma;capture_fast_init(dma);}
int capture_valid(const capture_config *c,uint32_t app) {
    if(!c->capacity || c->capacity>CAPTURE_MAX ||
       (c->pre_percent!=10 && c->pre_percent!=50 && c->pre_percent!=90) ||
       c->strobe>1 || c->edge>1 || c->address>ADDRESS_MASK || c->mask>ADDRESS_MASK ||
       c->memory_base>0xffc00u || (c->memory_base&1023) || !c->cycles || c->cycles>(app==APP_CPU_EMULATOR ? 2000000u : 65536u) ||
       c->idle_ms>30000 || c->cycle_timeout_us<10 || c->cycle_timeout_us>100000 || c->seed>255)return 0;
    if(app==APP_ANALYZER && (c->sample_hz<1000 || c->sample_hz>1000000))return 0;
    if(app==APP_BUS_MEMORY && c->sample_hz==CAPTURE_FAST_HZ &&
       (c->capacity>CAPTURE_FAST_MAX || c->mask || c->address))return 0;
    if(app==APP_ABC1600_MEMORY && (c->memory_base || c->sample_hz==CAPTURE_FAST_HZ || c->seed))return 0;
    return 1;
}

static int sampler(app_job *j,bool state) {
    pio_clear_instruction_memory(pio0);pio_set_gpio_base(pio0,j->bank ? 16 : 0);
    pio_sm_config c=pio_get_default_sm_config();
    // PIO's divider is at most 65536. Add instruction delay for low sample
    // rates instead of passing an out-of-range divider to the SDK.
    uint32_t timing_cycles=capture_settings.sample_hz<3000 ? 32 : 1;
    uint16_t timing[]={pio_encode_in(pio_pins,32)|pio_encode_delay(timing_cycles-1)};
    // Two counters measure all elapsed PIO clocks, including time with no
    // bus activity. HIGH iterations cost 2 clocks, LOW iterations 3 clocks,
    // and each emitted triple costs 7 clocks. No CPU timestamp jitter.
    uint16_t falling[]={pio_encode_jmp_y_dec(1),pio_encode_jmp_pin(3),pio_encode_jmp(0),
        pio_encode_jmp_x_dec(4),pio_encode_jmp_pin(3),
        pio_encode_mov(pio_isr,pio_pins),pio_encode_push(false,true),
        pio_encode_mov(pio_isr,pio_x),pio_encode_push(false,true),
        pio_encode_mov(pio_isr,pio_y),pio_encode_push(false,true),pio_encode_jmp(0)};
    uint16_t rising[]={pio_encode_jmp_x_dec(1),pio_encode_jmp_pin(0),
        pio_encode_jmp_y_dec(3),pio_encode_jmp_pin(5),pio_encode_jmp(2),
        pio_encode_mov(pio_isr,pio_pins),pio_encode_push(false,true),
        pio_encode_mov(pio_isr,pio_x),pio_encode_push(false,true),
        pio_encode_mov(pio_isr,pio_y),pio_encode_push(false,true),pio_encode_jmp(0)};
    struct pio_program program={.instructions=state ? (capture_settings.edge ? rising : falling) : timing,
                               .length=state ? 12 : 1,.origin=0};
    if(pio_add_program_at_offset(pio0,&program,0)<0)return 0;
    sm_config_set_wrap(&c,0,program.length-1);
    sm_config_set_in_pins(&c,j->bank ? 32 : 0);
    sm_config_set_in_pin_count(&c,j->bank ? 13 : 32);
    sm_config_set_in_shift(&c,true,!state,32);sm_config_set_fifo_join(&c,PIO_FIFO_JOIN_RX);
    sm_config_set_jmp_pin(&c,capture_settings.strobe ? 28 : 29);
    sm_config_set_clkdiv(&c,state ? 1.0f : (float)clock_get_hz(clk_sys)/(capture_settings.sample_hz*timing_cycles));
    if(pio_sm_init(pio0,0,0,&c)!=PICO_OK)return 0;
    pio_sm_exec(pio0,0,pio_encode_mov_not(pio_x,pio_null));
    pio_sm_exec(pio0,0,pio_encode_mov_not(pio_y,pio_null));
    dma_channel_config d=dma_channel_get_default_config(sample_dma);
    channel_config_set_transfer_data_size(&d,DMA_SIZE_32);channel_config_set_high_priority(&d,true);
    channel_config_set_read_increment(&d,false);channel_config_set_write_increment(&d,true);
    // DMA RING_SIZE is four bits: the hardware maximum is 32 KiB. The
    // independent logical PSRAM ring still holds up to 65536 records.
    channel_config_set_ring(&d,true,15);channel_config_set_dreq(&d,pio_get_dreq(pio0,0,false));
    dma_channel_configure(sample_dma,&d,acquisition,&pio0->rxf[0],DMA_TRANSFERS,true);
    pio0->fdebug=PIO_FDEBUG_BITS;
    if(!state) {
        // Publish the actual divider-derived rate, rather than the requested
        // rate rounded to the PIO's 16.8-bit divider.
        uint32_t div=pio0->sm[0].clkdiv>>8;
        uint32_t period=div*timing_cycles;
        j->hz=((uint64_t)clock_get_hz(clk_sys)*256+period/2)/period;
    } else j->hz=clock_get_hz(clk_sys);
    return 1;
}

static int acquire(app_job *j,uint32_t app) {
    bool abc=app==APP_ABC1600_MEMORY;
    bool state=app!=APP_ANALYZER, memory=app==APP_BUS_MEMORY || abc;
    bool boot=abc || (memory && (j->flags&FLAG_BOOT_MEMORY));
    bool image=!abc && boot && capture_settings.seed==3;
    uint8_t *ram=image ? TARGET_MEMORY : capture_memory;
    uint32_t ram_bytes=image || abc ? TARGET_MEMORY_BYTES : sizeof capture_memory;
    capture_window w;
    if(!capture_window_init(&w,capture_settings.capacity,capture_settings.pre_percent) || !sampler(j,state)) {
        j->error=1;return 1;
    }
    if(memory) {
        memset(capture_memory,0,sizeof capture_memory);
        if(boot)boot_memory_prepare(abc ? 4 : capture_settings.seed);
        if(abc) {abc1600_memory_init(&abc1600_model);memset(ABC1600_RAM,0,ABC1600_STORAGE_BYTES);}
        gpio_put(31,1);gpio_set_dir(31,GPIO_OUT);
    }
    uint32_t read=0,sequence=0,stride=state ? 3 : 1;
    uint64_t last_activity=time_us_64(),deadline=last_activity+(uint64_t)j->timeout_ms*1000;
    uint64_t cycle_start=0,release_at=0;
    bool responding=false,reading=false,finish=false,berr=false;
    uint32_t finish_flags=0;
    j->state=JOB_ARMED;__dmb();pio_sm_set_enabled(pio0,0,true);
    if(boot)boot_memory_start();
    while(!finish || responding) {
        if(boot)boot_memory_poll();
        uint64_t now=time_us_64();
        uint32_t pins=gpio_get_all();
        bool selected=!(pins&(AS|DS));
        if(memory && !responding && !finish && selected) {
            uint32_t address=pins&ADDRESS_MASK;
            if(address>=capture_settings.memory_base && address-capture_settings.memory_base<ram_bytes) {
                uint32_t offset=address-capture_settings.memory_base;
                reading=(pins&RW)!=0;
                berr=boot && boot_memory_cycle(address,reading);
                uint8_t value=(pins>>20)&255;
                uint32_t fc=(gpio_get_all64()>>32)&7;
                if(!berr && abc)berr=abc1600_memory_access(&abc1600_model,TARGET_MEMORY,ABC1600_RAM,address,fc,!reading,&value)!=CPU_BUS_OK;
                else if(!berr && image)berr=generic_memory_access(&target_image,ram,offset,fc,!reading,&value)!=CPU_BUS_OK;
                else if(!berr && reading)value=ram[offset];
                else if(!berr)ram[offset]=value;
                if(berr)gpio_set_dir(BENCH_BERR,GPIO_OUT);
                else if(reading) {
                    gpio_put_masked(DATA_MASK,(uint32_t)value<<20);
                    gpio_set_dir_out_masked(DATA_MASK);
                }
                __dmb();if(!berr)gpio_put(31,0);responding=true;cycle_start=now;release_at=0;
                last_activity=now;
            }
        }
        if(responding && (!selected || now-cycle_start>=capture_settings.cycle_timeout_us)) {
            // Preserve read data beyond the strobe's release, so the PIO
            // release-edge sample sees valid data. Time is in microseconds;
            // this intentionally stretches inter-cycle recovery on the bench.
            if(!release_at)release_at=now+1;
            if(now>=release_at) {
                gpio_set_dir_in_masked(DATA_MASK);gpio_put(31,1);responding=false;
                if(berr)gpio_set_dir(BENCH_BERR,GPIO_IN);
                if(selected) {j->error=2;break;}
            }
        }
        uint32_t produced=DMA_TRANSFERS-dma_hw->ch[sample_dma].transfer_count;
        if(produced-read>DMA_WORDS || pio0->fdebug || produced>=DMA_TRANSFERS) {j->error=3;break;}
        // Limit each batch so memory service, aborts and idle checks keep
        // running even under a continuous stream of captured state records.
        unsigned batch=0;
        uint32_t batch_start=read;
        while(!w.done && produced-read>=stride && batch++<64) {
            uint32_t value=acquisition[read&(DMA_WORDS-1)];
            uint32_t x=0,y=0;
            if(state) {
                x=acquisition[(read+1)&(DMA_WORDS-1)];
                y=acquisition[(read+2)&(DMA_WORDS-1)];
            }
            uint32_t slot;
            bool match=state ? ((value&capture_settings.mask)==(capture_settings.address&capture_settings.mask)) :
                (((value>>(j->trigger_gpio-(j->bank ? 32 : 0)))&1)==j->trigger_level);
            slot=capture_window_push(&w,match);
            records[slot*stride]=value&(j->bank ? 0x1fff : UINT32_MAX);
            if(state) {
                uint64_t ticks=(uint64_t)(~x)*2+(uint64_t)(~y)*3-1+(uint64_t)sequence*7;
                records[slot*3+1]=(uint32_t)ticks;records[slot*3+2]=(uint32_t)(ticks>>32);
            }
            read+=stride;++sequence;last_activity=now;
        }
        __dmb();
        // Conservatively require the entire batch to retain DMA ownership
        // through its final copy, including when it completes the capture.
        // Reading the DMA register once per batch keeps the 1 MS/s budget.
        if(DMA_TRANSFERS-dma_hw->ch[sample_dma].transfer_count-batch_start>DMA_WORDS) {
            j->error=3;break;
        }
        if(w.done) {
            // Keep servicing memory after freezing the trace, until the
            // source becomes idle or STOP is requested. No records are lost
            // silently: this is an explicitly completed capture window.
            read=produced;
            if(!memory)finish=true;
        }
        if(j->abort) {j->error=ERR_ABORT;break;}
        if(capture_stop) {finish=true;finish_flags|=CAPTURE_STOPPED;}
        if(now>=deadline) {finish=true;finish_flags|=CAPTURE_TIMEOUT;}
        if(state && capture_settings.idle_ms && now-last_activity>=(uint64_t)capture_settings.idle_ms*1000) {
            finish=true;finish_flags|=CAPTURE_IDLE;
        }
    }
    pio_sm_set_enabled(pio0,0,false);dma_channel_abort(sample_dma);
    j->fdebug=pio0->fdebug;j->samples=w.count;j->remaining=w.capacity-w.count;
    if(j->fdebug && !j->error)j->error=3;
    if(j->error)return 1;
    // Move the logical ring to chronological order while saving, not here.
    capture_result=(capture_record){.magic=CAPTURE_MAGIC,.version=1,.committed=UINT32_MAX,
        .bank=j->bank,.app=app,.count=w.count,.stride=stride*4,.hz=j->hz,
        .trigger=capture_window_trigger(&w),.first_sequence=w.total-w.count,
        .flags=finish_flags|(w.triggered ? CAPTURE_TRIGGERED : 0),.bytes=w.count*stride*4,
        .capacity=w.capacity,.pre_percent=capture_settings.pre_percent,.reserved=capture_window_start(&w)};
    return 1;
}

static int generate(app_job *j) {
    bus_cycle_prepare(sample_dma);
    j->hz=8000000;j->state=JOB_ARMED;
    uint64_t deadline=time_us_64()+(uint64_t)j->timeout_ms*1000;
    while(!j->start && !j->abort && time_us_64()<deadline)tight_loop_contents();
    if(j->abort) {j->error=ERR_ABORT;return 1;}
    if(!j->start) {j->error=2;return 1;}
    j->state=JOB_RUNNING;
    for(uint32_t n=0;n<capture_settings.cycles;++n) {
        uint32_t offset=n&1023,addr=capture_settings.memory_base+offset;
        bool write=(j->flags&FLAG_WRITES) && !(n&1024);
        uint32_t data=(offset^(offset>>8)^capture_settings.seed)&255;
        uint8_t value=data;
        int status=bus_cycle_transfer(j,addr,write,&value,deadline,false);
        if(status!=CPU_BUS_OK) {j->error=status==CPU_BUS_ABORT ? ERR_ABORT : 2;break;}
        if(!write && (j->flags&FLAG_WRITES) && value!=data) {j->error=8;break;}
        ++j->samples;
        if(time_us_64()>=deadline) {j->error=2;break;}
    }
    bus_cycle_release();
    j->remaining=capture_settings.cycles-j->samples;
    return 1;
}

int capture_run(app_job *j,uint32_t app) {
    engine_set_bus_mode(app>=APP_BUS_GENERATOR);
    if(app==APP_ANALYZER && !capture_settings.capacity)return 0; // legacy finite 150 MS/s
    if(!capture_valid(&capture_settings,app) ||
       ((app==APP_BUS_GENERATOR || app==APP_BUS_MEMORY || app==APP_CPU_EMULATOR || app==APP_ABC1600_MEMORY) && !(j->flags&FLAG_DRIVE))) {j->error=1;return 1;}
    if(app>=APP_BUS_GENERATOR)for(uint pin=28;pin<=31;++pin)gpio_pull_up(pin);
    if((j->flags&FLAG_BOOT_MEMORY) && (app!=APP_BUS_MEMORY || capture_settings.memory_base ||
       capture_settings.seed>3 || (capture_settings.seed==3 && !target_image.ready) ||
       capture_settings.sample_hz==CAPTURE_FAST_HZ)) {j->error=1;return 1;}
    if(app==APP_ABC1600_MEMORY && (!target_image.ready || target_image.bytes!=ABC1600_ROM_BYTES || target_image.crc!=0x9372f6f2u)) {j->error=1;return 1;}
    if(app==APP_CPU_EMULATOR)return cpu_fixture_run(j,sample_dma);
    if(app==APP_BUS_MEMORY && capture_settings.sample_hz==CAPTURE_FAST_HZ)return capture_fast_run(j);
    return app==APP_BUS_GENERATOR ? generate(j) : acquire(j,app);
}
