// SPDX-License-Identifier: Apache-2.0
#ifndef ICE_CAPTURE_H
#define ICE_CAPTURE_H
#include "app_abi.h"
#include "capture_window.h"
// RUN may append these twelve uint32 values to its original five words.
typedef struct {
    uint32_t capacity, pre_percent, sample_hz, strobe, edge;
    uint32_t address, mask, memory_base, cycles, idle_ms, cycle_timeout_us, seed;
} capture_config;
// Persistent header, and command 16 response. Raw payload is chronological.
typedef struct {
    uint32_t magic, version, committed, bank, app, count, stride, hz;
    uint32_t trigger, first_sequence, flags, bytes, crc, capacity, pre_percent, reserved;
} capture_record;
#define CAPTURE_MAGIC 0x43415032u
#define CAPTURE_TRIGGERED 1u
#define CAPTURE_STOPPED 2u
#define CAPTURE_IDLE 4u
#define CAPTURE_TIMEOUT 8u
#define CAPTURE_MEMORY_TIMING 16u
#define CAPTURE_FAST_HZ 150000000u
#define CAPTURE_FAST_MAX 4096u
extern capture_config capture_settings;
extern volatile uint32_t capture_stop;
extern capture_record capture_result;
extern uint8_t capture_memory[1024];
int capture_valid(const capture_config *,uint32_t app);
int capture_run(app_job *,uint32_t app);
void capture_init(int dma);
void capture_fast_init(int dma);
void capture_fast_release(void);
int capture_fast_run(app_job *);
extern volatile uint32_t capture_fast_debug[12];
bool capture_save(void);
const capture_record *capture_saved(uint32_t bank);
const uint8_t *capture_saved_data(uint32_t bank);
#endif
