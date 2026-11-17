// SPDX-License-Identifier: Apache-2.0
#ifndef ICE_BUS_CYCLE_H
#define ICE_BUS_CYCLE_H
#include <stdbool.h>
#include "app_abi.h"
#include "cpu68008.h"
// Bench GPIO31 is DTACK (not the adapter's clock). GPIO35 is fixture RESET,
// avoiding the onboard LED on the adapter's GPIO39 RESET assignment.
#define BENCH_RESET 35u
#define BENCH_HALT 38u
#define BENCH_BERR 40u
#define BENCH_FC_MASK (UINT64_C(7)<<32)
void bus_cycle_prepare(int dma);
void bus_cycle_release(void);
int bus_cycle_transfer(app_job *,uint32_t address,bool write,uint8_t *data,
                       uint64_t deadline,bool cpu_signals);
#endif
