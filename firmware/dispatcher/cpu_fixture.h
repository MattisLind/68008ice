// SPDX-License-Identifier: Apache-2.0
#ifndef ICE_CPU_FIXTURE_H
#define ICE_CPU_FIXTURE_H
#include "bus_cycle.h"
typedef struct {
    uint32_t version,profile,reset_asserted,reset_released,halt_seen,cycles,reads,writes;
    uint32_t first_address,last_address,first_fc,last_fc,fc_errors,reset_low_us,reset_high_us,halt_low_us;
} boot_memory_record;
extern cpu68008 cpu_result;
extern boot_memory_record boot_memory_result;
#define CPU_TRACE_CAPACITY 128u
extern cpu68008 cpu_trace[CPU_TRACE_CAPACITY];
extern uint32_t cpu_trace_count,cpu_trace_total;
int cpu_fixture_run(app_job *,int dma);
void boot_memory_prepare(uint32_t profile);
void boot_memory_start(void);
void boot_memory_poll(void);
bool boot_memory_cycle(uint32_t address,bool reading);
#endif
