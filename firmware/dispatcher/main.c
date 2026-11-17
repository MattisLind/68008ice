// SPDX-License-Identifier: Apache-2.0
// Resident core-0 dispatcher. Validated modules execute on core 1 from SRAM.
#include <stdio.h>
#include <string.h>
#include "engine.h"
#include "capture.h"
#include "cpu_fixture.h"
#include "memory_image.h"
#include "loader.h"
#include "protocol.h"
#include "hardware/clocks.h"
#include "hardware/structs/powman.h"
#include "hardware/sync.h"
#include "pico/bootrom.h"
#include "pico/multicore.h"
#include "pico/stdlib.h"
#include "pico/unique_id.h"
#include "trace_store.h"
#include "trace_usb.h"
#include "tusb.h"

char board_id[17];
app_job dispatcher_job;
static volatile bool worker_ready,worker_request;
static volatile uint32_t worker_core;
static uint8_t tx[540],cached[540];
static size_t tx_bytes,tx_at,cached_bytes;
static uint16_t last_seq;
static uint32_t last_crc;
static bool have_last;
static uint8_t pending_action;
static protocol_rx rx;
static uint32_t get32(const uint8_t *p) {uint32_t n;memcpy(&n,p,4);return n;}
static bool busy(void) {
    uint32_t s=dispatcher_job.state;
    return worker_request || (s!=JOB_IDLE && s!=JOB_DONE && s!=JOB_ERROR);
}

static void worker(void) {
    worker_core=get_core_num();multicore_lockout_victim_init();engine_init();worker_ready=true;__sev();
    while(true) {
        while(!worker_request)__wfe();
        __dmb();
        ((app_entry)(APP_ADDRESS|1u))(&dispatcher_job,&engine_api);
        engine_api.release();
        uint32_t state=dispatcher_job.error ? JOB_ERROR :
            ((loader_app==APP_ANALYZER || loader_app==APP_BUS_MEMORY || loader_app==APP_STATE_ANALYZER) ? JOB_RAW_DONE : JOB_DONE);
        worker_request=false;__dmb();dispatcher_job.state=state;__sev();
    }
}

static void command(uint8_t op,uint16_t seq,const uint8_t *p,uint16_t n,uint32_t crc) {
    if(have_last && seq==last_seq) {
        if(crc==last_crc) {memcpy(tx,cached,cached_bytes);tx_bytes=cached_bytes;tx_at=0;return;}
        tx_bytes=protocol_encode(op|0x80,seq,8,NULL,0,tx);tx_at=0;return;
    }
    uint8_t out[256];uint16_t length=0,status=0;
    switch(op) {
    case 1: // HELLO
        if(n) {status=1;break;}
        length=snprintf((char *)out,sizeof out,
            "{\"serial\":\"%s\",\"firmware\":\"dispatcher-0.6\",\"protocol\":1,"
            "\"instance\":%u,\"core\":%u,\"worker_core\":%lu,\"psram\":%lu,"
            "\"app\":%lu,\"source\":%lu,\"image_crc\":%lu}",
            board_id,ICE_SWD_INSTANCE_ID,get_core_num(),(unsigned long)worker_core,(unsigned long)loader_psram,
            (unsigned long)loader_app,(unsigned long)loader_source,(unsigned long)loader_crc);
        break;
    case 2: // LIST built-in images
        if(n) {status=1;break;}
        for(uint32_t app=1;app<=APP_CPU_EMULATOR;++app) {
            const app_header *h=loader_builtin(app);
            memcpy(out+length,h,sizeof *h);length+=sizeof *h;
        }
        break;
    case 3: // LOAD: app, source (0 flash, 1 staged flash->PSRAM, 2 uploaded PSRAM)
        if(n!=8) {status=1;break;}
        if(busy()) {status=2;break;}
        status=loader_load(get32(p),get32(p+4));
        if(!status) {memset(&dispatcher_job,0,sizeof dispatcher_job);memset(&capture_settings,0,sizeof capture_settings);}
        break;
    case 4: // RUN: bank, GPIO, level, timeout_ms, flags
        if(n!=20 && n!=20+sizeof(capture_config)) {status=1;break;}
        if(busy()) {status=2;break;}
        if(!loader_app) {status=4;break;}
        if(get32(p)>1 || get32(p+4)>44 || get32(p+8)>1 ||
            get32(p+12)<10 || get32(p+12)>30000 || (get32(p+16)&~15u)) {status=1;break;}
        if((loader_app==APP_GENERATOR || loader_app==APP_BUS_GENERATOR || loader_app==APP_BUS_MEMORY || loader_app==APP_CPU_EMULATOR) &&
           !(get32(p+16)&FLAG_DRIVE)) {status=7;break;}
        if(n==20 && (loader_app>APP_ANALYZER || (get32(p+16)&~3u))) {status=1;break;}
        if(n>20) {
            capture_config c;memcpy(&c,p+20,sizeof c);
            if(!loader_psram) {status=4;break;}
            if(loader_app==APP_GENERATOR || !capture_valid(&c,loader_app) ||
               (loader_app!=APP_BUS_GENERATOR && loader_app!=APP_BUS_MEMORY && loader_app!=APP_CPU_EMULATOR && (get32(p+16)&~1u)) ||
               (loader_app==APP_CPU_EMULATOR && (get32(p+16)&~5u)) ||
               (loader_app==APP_BUS_GENERATOR && (get32(p+16)&~5u)) ||
               (loader_app==APP_BUS_MEMORY && (get32(p+16)&~9u)) ||
               ((get32(p+16)&FLAG_BOOT_MEMORY) && (c.memory_base || c.seed>3 || c.sample_hz==CAPTURE_FAST_HZ)) ||
               (loader_app>=APP_BUS_GENERATOR && get32(p)!=0) ||
               (loader_app==APP_ANALYZER && (get32(p+4)<(get32(p) ? 32u : 0u) ||
                   get32(p+4)>(get32(p) ? 44u : 31u)))) {status=1;break;}
            if((get32(p+16)&FLAG_BOOT_MEMORY) && c.seed==3 && !target_image.ready) {status=4;break;}
            capture_settings=c;
        } else {
            if(loader_app==APP_ANALYZER && !loader_psram) {status=4;break;}
            memset(&capture_settings,0,sizeof capture_settings);
        }
        capture_stop=0;
        memset(&cpu_result,0,sizeof cpu_result);memset(&boot_memory_result,0,sizeof boot_memory_result);
        memset(&dispatcher_job,0,sizeof dispatcher_job);memcpy(&dispatcher_job,p,20);
        dispatcher_job.state=JOB_PREPARING;__dmb();worker_request=true;__sev();
        break;
    case 5: // GO prepared generator
        if(n) {status=1;break;}
        if(loader_app==APP_BUS_MEMORY && capture_settings.sample_hz==CAPTURE_FAST_HZ &&
           dispatcher_job.state==JOB_ARMED && !dispatcher_job.start) {pending_action=4;break;}
        if((loader_app!=APP_GENERATOR && loader_app!=APP_BUS_GENERATOR && loader_app!=APP_CPU_EMULATOR) || dispatcher_job.state!=JOB_ARMED) {status=2;break;}
        dispatcher_job.start=1;__sev();break;
    case 6: // STATUS
        if(n) {status=1;break;}
        memcpy(out,&dispatcher_job,sizeof dispatcher_job);length=sizeof dispatcher_job;break;
    case 7: // ABORT; SIO FIFO IRQ wakes the worker's WFI without touching DMA SRAM.
        if(n) {status=1;break;}
        if(busy()) {dispatcher_job.abort=1;multicore_fifo_push_blocking(0x41424f52);__sev();}
        break;
    case 8: { // FILE metadata (persistent)
        if(n!=4 || get32(p)>1) {status=1;break;}
        if(busy()) {status=2;break;}
        const trace_record *r=trace_record_get(get32(p));
        if(!r) {status=4;break;}
        memcpy(out,r,sizeof *r);length=sizeof *r;break;
    }
    case 9: { // READ kind (0 VCD, 1 raw SRAM), bank, offset, bytes
        if(n!=16 || get32(p)>4 || get32(p+4)>1 || get32(p+12)>256) {status=1;break;}
        if(busy()) {status=2;break;}
        const void *data;uint32_t bytes;
        if(get32(p)==0) {
            const trace_record *r=trace_record_get(get32(p+4));
            if(!r) {status=4;break;}
            data=trace_record_data(get32(p+4));bytes=r->bytes;
        } else if(get32(p)==1) {
            if(loader_app!=APP_ANALYZER || dispatcher_job.state!=JOB_DONE ||
                capture_settings.capacity || get32(p+4)!=dispatcher_job.bank) {status=4;break;}
            data=engine_api.samples;bytes=4096;
        } else if(get32(p)==2) {
            const capture_record *r=capture_saved(get32(p+4));
            if(!r) {status=4;break;}
            data=capture_saved_data(get32(p+4));bytes=r->bytes;
        } else if(get32(p)==4) {
            if(loader_app!=APP_BUS_MEMORY || !target_image.ready || get32(p+4)) {status=4;break;}
            data=TARGET_MEMORY;bytes=TARGET_MEMORY_BYTES;
        } else {
            if(loader_app!=APP_BUS_MEMORY || dispatcher_job.state!=JOB_DONE || get32(p+4)) {status=4;break;}
            data=capture_memory;bytes=sizeof capture_memory;
        }
        uint32_t offset=get32(p+8),count=get32(p+12);
        if(offset>bytes || count>bytes-offset) {status=1;break;}
        memcpy(out,(const uint8_t *)data+offset,count);length=count;break;
    }
    // Command 10 was DISK in 0.1. It is retired and returns unknown-command.
    case 11: // BOOTSEL after ACK
        if(n) {status=1;break;}
        if(busy()) {status=2;break;}
        pending_action=3;break;
    case 12: // UPLOAD BEGIN; volatile PSRAM only
        if(n!=4) {status=1;break;}
        if(busy()) {status=2;break;}
        status=loader_upload_begin(get32(p));break;
    case 13:
        if(n<5) {status=1;break;}
        if(busy()) {status=2;break;}
        status=loader_upload_write(get32(p),p+4,n-4);break;
    case 14:
        if(n) {status=1;break;}
        if(busy()) {status=2;break;}
        status=loader_upload_commit();break;
    case 16: { // extended capture metadata, persistent
        if(n!=4 || get32(p)>1) {status=1;break;}
        if(busy()) {status=2;break;}
        const capture_record *r=capture_saved(get32(p));
        if(!r) {status=4;break;}
        memcpy(out,r,sizeof *r);length=sizeof *r;break;
    }
    case 17: // graceful stop: retain partial continuous/state capture
        if(n) {status=1;break;}
        if(!capture_settings.capacity || (loader_app!=APP_ANALYZER && loader_app!=APP_BUS_MEMORY &&
           loader_app!=APP_STATE_ANALYZER && loader_app!=APP_CPU_EMULATOR)) {status=2;break;}
        capture_stop=1;__sev();break;
    case 18: // stopped fast-capture diagnostic snapshot; no live bus access
        if(n) {status=1;break;}
        if(busy()) {status=2;break;}
        if(loader_app!=APP_BUS_MEMORY || capture_settings.sample_hz!=CAPTURE_FAST_HZ) {status=4;break;}
        memcpy(out,(const void *)capture_fast_debug,sizeof capture_fast_debug);length=sizeof capture_fast_debug;break;
    case 19: // CPU registers and completion cause, stopped job only
        if(n) {status=1;break;}
        if(busy()) {status=2;break;}
        if(loader_app!=APP_CPU_EMULATOR || !cpu_result.version) {status=4;break;}
        memcpy(out,&cpu_result,64);length=64;break;
    case 20: // memory-side reset / HALT / FC observations, stopped job only
        if(n) {status=1;break;}
        if(busy()) {status=2;break;}
        if(loader_app!=APP_BUS_MEMORY || !(dispatcher_job.flags&FLAG_BOOT_MEMORY) || !boot_memory_result.version) {status=4;break;}
        memcpy(out,&boot_memory_result,sizeof boot_memory_result);length=sizeof boot_memory_result;break;
    case 21: // Begin a volatile ROM upload into the separate 1 MiB target map.
        if(n!=8) {status=1;break;}
        if(busy()) {status=2;break;}
        if(loader_app!=APP_BUS_MEMORY || !loader_psram) {status=4;break;}
        status=memory_image_begin(&target_image,TARGET_MEMORY,get32(p),get32(p+4));break;
    case 22:
        if(n<5) {status=1;break;}
        if(busy()) {status=2;break;}
        if(loader_app!=APP_BUS_MEMORY || !loader_psram) {status=4;break;}
        status=memory_image_write(&target_image,TARGET_MEMORY,get32(p),p+4,n-4);break;
    case 23:
        if(n) {status=1;break;}
        if(busy()) {status=2;break;}
        if(loader_app!=APP_BUS_MEMORY || !loader_psram) {status=4;break;}
        status=memory_image_commit(&target_image,TARGET_MEMORY);break;
    case 24:
        if(n) {status=1;break;}
        if(busy()) {status=2;break;}
        memcpy(out,&target_image,sizeof target_image);length=sizeof target_image;break;
    case 25: // Complete CPU register file, stopped worker only.
        if(n) {status=1;break;}
        if(busy()) {status=2;break;}
        if(loader_app!=APP_CPU_EMULATOR || !cpu_result.version) {status=4;break;}
        memcpy(out,&cpu_result,sizeof cpu_result);length=sizeof cpu_result;break;
    case 26: // Bounded post-reset / post-instruction snapshots.
        if(n!=4) {status=1;break;}
        if(busy()) {status=2;break;}
        if(loader_app!=APP_CPU_EMULATOR || !cpu_result.version) {status=4;break;}
        if(get32(p)==UINT32_MAX) {
            uint32_t meta[]={1,cpu_trace_count,cpu_trace_total,cpu_trace_total-cpu_trace_count};
            memcpy(out,meta,sizeof meta);length=sizeof meta;
        } else if(get32(p)>=cpu_trace_count)status=1;
        else {memcpy(out,&cpu_trace[get32(p)],sizeof(cpu68008));length=sizeof(cpu68008);}
        break;
    case 27: // Host writes one non-ROM byte of the volatile target map.
        if(n!=8 || get32(p)>=TARGET_MEMORY_BYTES || get32(p+4)>255) {status=1;break;}
        if(busy()) {status=2;break;}
        if(loader_app!=APP_BUS_MEMORY || !target_image.ready) {status=4;break;}
        if(get32(p)<target_image.bytes) {status=1;break;}
        TARGET_MEMORY[get32(p)]=get32(p+4);break;
    default:status=5;break;
    }
    if(length>sizeof out) {status=6;length=0;}
    tx_bytes=protocol_encode(op|0x80,seq,status,out,length,tx);tx_at=0;
    memcpy(cached,tx,tx_bytes);cached_bytes=tx_bytes;
    have_last=true;last_seq=seq;last_crc=crc;
}

int main(void) {
    powman_hw->dbgconfig=POWMAN_PASSWORD_BITS|ICE_SWD_INSTANCE_ID;
    pico_get_unique_board_id_string(board_id,sizeof board_id);
    for(uint pin=0;pin<45;++pin) {
        gpio_init(pin);gpio_set_dir(pin,GPIO_IN);
        if(pin==BENCH_RESET || pin==BENCH_HALT || pin==BENCH_BERR)gpio_pull_up(pin);
        else gpio_pull_down(pin);
    }
    loader_init_psram(); // before core 1 or USB can access XIP
    multicore_launch_core1(worker);
    while(!worker_ready)__wfe();
    trace_usb_init();
    while(true) {
        trace_usb_task();
        if(tx_at<tx_bytes && tud_cdc_connected()) {
            tx_at+=tud_cdc_write(tx+tx_at,tx_bytes-tx_at);tud_cdc_write_flush();
        }
        if(tx_at==tx_bytes) {
            while(tud_cdc_available() && tx_at==tx_bytes) {
                uint8_t b;tud_cdc_read(&b,1);protocol_byte(&rx,b,command);
            }
        }
        if(dispatcher_job.state==JOB_RAW_DONE) {
            dispatcher_job.state=JOB_SAVING;
            if(capture_settings.capacity) {
                multicore_lockout_start_blocking();
                bool ok=capture_save();
                multicore_lockout_end_blocking();
                if(ok)dispatcher_job.raw_crc=capture_result.crc;
                else dispatcher_job.error=4;
                __dmb();dispatcher_job.state=ok ? JOB_DONE : JOB_ERROR;
                continue;
            }
            if(dispatcher_job.bank)for(unsigned i=0;i<1024;++i)engine_api.samples[i]&=0x1fff;
            dispatcher_job.raw_crc=protocol_crc(engine_api.samples,4096);
            multicore_lockout_start_blocking();
            bool ok=trace_store_save_trigger(dispatcher_job.bank,engine_api.samples,dispatcher_job.hz,
                dispatcher_job.fdebug,dispatcher_job.trigger_gpio,dispatcher_job.trigger_level);
            multicore_lockout_end_blocking();
            if(ok) {
                const trace_record *r=trace_record_get(dispatcher_job.bank);
                dispatcher_job.vcd_bytes=r->bytes;dispatcher_job.vcd_crc=r->crc32;
            } else dispatcher_job.error=4;
            __dmb();dispatcher_job.state=ok ? JOB_DONE : JOB_ERROR;
        }
        if(pending_action && tx_at==tx_bytes && !tud_cdc_write_available())continue;
        if(pending_action && tx_at==tx_bytes) {
            // Give the final ACK time to reach the host before reenumerating.
            if(pending_action==4) {
                for(unsigned i=0;i<5;++i) {trace_usb_task();tud_cdc_write_flush();sleep_ms(1);}
                // USB register traffic can stall a full-rate PIO DMA beat.
                // ACK first, then keep this core and its USB IRQ quiet until
                // the worker finishes. Worker SysTick still bounds no-trigger
                // acquisition; SEV wakes us after output release.
                uint32_t irq=save_and_disable_interrupts();
                pending_action=0;dispatcher_job.start=1;__dmb();__sev();
                while(worker_request)__wfe();
                restore_interrupts(irq);continue;
            }
            for(unsigned i=0;i<50;++i) {trace_usb_task();tud_cdc_write_flush();sleep_ms(1);}
            pending_action=0;reset_usb_boot(0,0);
        }
    }
}
