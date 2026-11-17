// SPDX-License-Identifier: Apache-2.0
#ifndef ICE_TRACE_STORE_H
#define ICE_TRACE_STORE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define TRACE_SAMPLES 1024u
#define TRACE_SLOT_BYTES (256u * 1024u)
#define TRACE_STORE_OFFSET (PICO_FLASH_SIZE_BYTES - 2u * TRACE_SLOT_BYTES)
#define TRACE_VCD_CAPACITY (192u * 1024u)
typedef struct {
    uint32_t magic, version, committed, bank, gpio_base, pin_count;
    uint32_t samples, sample_hz, bytes, crc32, fdebug, reserved[5];
} trace_record;
uint32_t trace_crc32(const void *data, size_t length);
const trace_record *trace_record_get(unsigned bank);
const uint8_t *trace_record_data(unsigned bank);
bool trace_store_save(unsigned bank, const uint32_t *samples, uint32_t hz, uint32_t fdebug);
bool trace_store_save_trigger(unsigned bank, const uint32_t *samples, uint32_t hz,
                              uint32_t fdebug, uint32_t trigger_gpio, uint32_t trigger_level);
void trace_disk_refresh(void);
void trace_disk_sector(uint32_t sector, uint8_t data[512]);
#endif
