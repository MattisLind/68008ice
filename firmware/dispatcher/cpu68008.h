// SPDX-License-Identifier: Apache-2.0
#ifndef ICE_CPU68008_H
#define ICE_CPU68008_H
#include <stdint.h>

// Portable interpreter; all target accesses use callbacks, including extensions.
enum {CPU_WAIT_RESET, CPU_RESET_VECTOR, CPU_RUNNING, CPU_STOPPED, CPU_HALTED, CPU_FAILED, CPU_PAUSED};
enum {CPU_BUS_OK, CPU_BUS_TIMEOUT, CPU_BUS_ABORT, CPU_BUS_RESET, CPU_BUS_BERR, CPU_BUS_HALT, CPU_BUS_WRITE_DENIED};
enum {CPU_FAULT_NONE, CPU_FAULT_BUS, CPU_FAULT_ALIGNMENT, CPU_FAULT_OPCODE, CPU_FAULT_SR};
typedef int (*cpu_read8)(void *context,uint32_t address,uint32_t fc,uint8_t *value);
typedef int (*cpu_write8)(void *context,uint32_t address,uint32_t fc,uint8_t value);
typedef struct {
    uint32_t version,state,ssp,pc,sr,opcode,instructions,reads,resets,fault;
    uint32_t address,fc,reset_seen,halt_asserted,reset_level,halt_level;
    uint32_t d[8],a[8],usp,writes,instruction_pc;
} cpu68008;
void cpu68008_init(cpu68008 *);
int cpu68008_reset(cpu68008 *,cpu_read8,void *);
int cpu68008_step(cpu68008 *,cpu_read8,void *);
int cpu68008_execute(cpu68008 *,cpu_read8,cpu_write8,void *);
#endif
