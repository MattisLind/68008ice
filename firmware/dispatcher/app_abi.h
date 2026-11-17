// SPDX-License-Identifier: Apache-2.0
#ifndef ICE_APP_ABI_H
#define ICE_APP_ABI_H
#include <stdint.h>
#define APP_ABI 2u
#define APP_ADDRESS 0x20030000u
#define APP_CAPACITY 16384u
#define APP_MAGIC 0x41505031u
#define APP_GENERATOR 1u
#define APP_ANALYZER 2u
#define APP_BUS_GENERATOR 3u
#define APP_BUS_MEMORY 4u
#define APP_STATE_ANALYZER 5u
#define APP_CPU_EMULATOR 6u
#define FLAG_BOOT_MEMORY 8u
#define JOB_IDLE 0u
#define JOB_PREPARING 1u
#define JOB_ARMED 2u
#define JOB_RUNNING 3u
#define JOB_DONE 4u
#define JOB_ERROR 5u
#define JOB_SAVING 6u
#define JOB_RAW_DONE 7u
#define ERR_ABORT 7u
#define FLAG_DRIVE 1u
#define FLAG_INITIAL_HIGH 2u
typedef struct {
    uint32_t bank, trigger_gpio, trigger_level, timeout_ms, flags;
    volatile uint32_t state, error, start, abort;
    uint32_t hz, samples, fdebug, remaining, raw_crc, vcd_bytes, vcd_crc;
} app_job;
typedef struct {
    uint32_t abi;
    uint32_t *samples, *pattern;
    int (*prepare)(app_job *, uint32_t source);
    int (*transfer)(app_job *, uint32_t source);
    int (*wait_start)(app_job *);
    void (*release)(void);
    int (*extended)(app_job *, uint32_t app);
} app_api;
typedef void (*app_entry)(app_job *, const app_api *);
typedef struct {uint32_t magic, abi, app, address, entry, bytes, crc;} app_header;
#endif
