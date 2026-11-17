// SPDX-License-Identifier: Apache-2.0
#include <string.h>
#include "cpu_fixture.h"
#include "capture.h"
#include "memory_image.h"
#include "hardware/sync.h"
#include "pico/stdlib.h"

cpu68008 cpu_result;
boot_memory_record boot_memory_result;
cpu68008 cpu_trace[CPU_TRACE_CAPACITY];
uint32_t cpu_trace_count,cpu_trace_total;
static uint64_t cpu_deadline,boot_start,reset_release;
static void snapshot(void) {
    if(cpu_trace_count<CPU_TRACE_CAPACITY)cpu_trace[cpu_trace_count++]=cpu_result;
    ++cpu_trace_total;
}
static void sideband_inputs(void) {
    const uint pins[]={BENCH_RESET,BENCH_HALT,BENCH_BERR};
    for(unsigned i=0;i<3;++i) {
        gpio_init(pins[i]);gpio_put(pins[i],0);gpio_set_dir(pins[i],GPIO_IN);
        gpio_pull_up(pins[i]);gpio_set_input_enabled(pins[i],true);
    }
}
static int read_byte(void *context,uint32_t address,uint32_t fc,uint8_t *data) {
    app_job *j=context;
    gpio_put_masked64(BENCH_FC_MASK,(uint64_t)fc<<32);
    int status=bus_cycle_transfer(j,address,false,data,cpu_deadline,true);
    if(status==CPU_BUS_OK)++j->samples;
    return status;
}
static int write_byte(void *context,uint32_t address,uint32_t fc,uint8_t data) {
    app_job *j=context;
    if(!(j->flags&4u))return CPU_BUS_WRITE_DENIED;
    gpio_put_masked64(BENCH_FC_MASK,(uint64_t)fc<<32);
    int status=bus_cycle_transfer(j,address,true,&data,cpu_deadline,true);
    if(status==CPU_BUS_OK)++j->samples;
    return status;
}
int cpu_fixture_run(app_job *j,int dma) {
    cpu68008_init(&cpu_result);sideband_inputs();
    cpu_trace_count=0;cpu_trace_total=0;
    cpu_deadline=time_us_64()+(uint64_t)j->timeout_ms*1000;
    j->hz=8000000;j->state=JOB_ARMED;__dmb();
    while(!j->start && !j->abort && !capture_stop && time_us_64()<cpu_deadline)tight_loop_contents();
    if(j->abort || capture_stop || !j->start)goto finish;
    j->state=JOB_RUNNING;
    // Require an observed reset assertion, rather than fetching vectors merely
    // because RUN/GO was issued. All bus outputs remain disabled until release.
    while(!j->abort && !capture_stop && time_us_64()<cpu_deadline) {
        while((gpio_get(BENCH_RESET) || gpio_get(BENCH_HALT)) &&
              !j->abort && !capture_stop && time_us_64()<cpu_deadline)tight_loop_contents();
        if(j->abort || capture_stop || time_us_64()>=cpu_deadline)break;
        cpu_result.reset_seen=1;
        while((!gpio_get(BENCH_RESET) || !gpio_get(BENCH_HALT)) &&
              !j->abort && !capture_stop && time_us_64()<cpu_deadline)tight_loop_contents();
        if(j->abort || capture_stop || time_us_64()>=cpu_deadline)break;
        bus_cycle_prepare(dma);
        gpio_put_masked64(BENCH_FC_MASK,UINT64_C(6)<<32);
        gpio_set_dir_out_masked64(BENCH_FC_MASK);
        int status=cpu68008_reset(&cpu_result,read_byte,j);
        snapshot();
        while(status==CPU_BUS_OK && cpu_result.state==CPU_RUNNING && cpu_result.instructions<capture_settings.cycles) {
            status=cpu68008_execute(&cpu_result,read_byte,write_byte,j);snapshot();
        }
        if(status==CPU_BUS_OK && cpu_result.state==CPU_RUNNING)cpu_result.state=CPU_PAUSED;
        bus_cycle_release();gpio_set_dir_in_masked64(BENCH_FC_MASK);
        if(status==CPU_BUS_RESET)continue;
        if(cpu_result.state==CPU_HALTED) {
            // A reset-vector BERR halts the CPU. Hold open-drain HALT long
            // enough for the memory-side poller, then release on job cleanup.
            gpio_put(BENCH_HALT,0);gpio_set_dir(BENCH_HALT,GPIO_OUT);
            uint64_t until=time_us_64()+1000;
            while(time_us_64()<until && time_us_64()<cpu_deadline && !j->abort && !capture_stop)tight_loop_contents();
        } else if(status==CPU_BUS_TIMEOUT)j->error=2;
        else if(status==CPU_BUS_ABORT) {if(j->abort)j->error=ERR_ABORT;}
        else if(status!=CPU_BUS_OK || (cpu_result.state!=CPU_STOPPED && cpu_result.state!=CPU_PAUSED))j->error=9;
        goto finish;
    }
finish:
    if(j->abort)j->error=ERR_ABORT;
    else if(!capture_stop && time_us_64()>=cpu_deadline && cpu_result.state!=CPU_STOPPED && cpu_result.state!=CPU_HALTED)j->error=2;
    cpu_result.reset_level=gpio_get(BENCH_RESET);cpu_result.halt_level=gpio_get(BENCH_HALT);
    j->remaining=capture_settings.cycles-cpu_result.instructions;
    return 1;
}

void boot_memory_prepare(uint32_t profile) {
    sideband_inputs();
    boot_memory_result=(boot_memory_record){.version=1,.profile=profile};
    if(profile==3)return; // Host committed a ROM image; preserve its RAM too.
    // Big endian SSP=$00000400, PC=$00000100. Profile 1 adds a NOP.
    const uint8_t vectors[]={0,0,4,0,0,0,1,0};
    const uint8_t program[]={0x4e,0x72,0x27,0};
    memcpy(capture_memory,vectors,sizeof vectors);
    unsigned at=0x100;
    if(profile==1) {capture_memory[at++]=0x4e;capture_memory[at++]=0x71;}
    memcpy(capture_memory+at,program,sizeof program);
}
void boot_memory_start(void) {
    boot_start=time_us_64();reset_release=boot_start+1000;
    // Fixed LOW latches, input sensing enabled, never drive either line HIGH.
    gpio_set_dir(BENCH_RESET,GPIO_OUT);gpio_set_dir(BENCH_HALT,GPIO_OUT);
    boot_memory_result.reset_asserted=1;
}
void boot_memory_poll(void) {
    uint64_t now=time_us_64();
    if(!boot_memory_result.reset_released && now>=reset_release) {
        gpio_set_dir(BENCH_HALT,GPIO_IN);gpio_set_dir(BENCH_RESET,GPIO_IN);
        boot_memory_result.reset_released=1;
        boot_memory_result.reset_high_us=(uint32_t)(now-boot_start);
    }
    if(boot_memory_result.reset_released && !gpio_get(BENCH_HALT) && !boot_memory_result.halt_seen) {
        boot_memory_result.halt_seen=1;boot_memory_result.halt_low_us=(uint32_t)(now-boot_start);
    }
}
bool boot_memory_cycle(uint32_t address,bool reading) {
    uint32_t fc=(gpio_get_all64()>>32)&7;
    if(!boot_memory_result.cycles) {boot_memory_result.first_address=address;boot_memory_result.first_fc=fc;}
    ++boot_memory_result.cycles;
    if(reading)++boot_memory_result.reads;else ++boot_memory_result.writes;
    boot_memory_result.last_address=address;boot_memory_result.last_fc=fc;
    if(fc!=6 && (boot_memory_result.profile!=3 || fc!=5))++boot_memory_result.fc_errors;
    return boot_memory_result.profile==2 && address==0;
}
