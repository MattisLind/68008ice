// SPDX-License-Identifier: Apache-2.0
// Two bounded VCD records in the last 512 KiB of the standalone 16 MiB flash.
// No PSRAM or general-purpose CS discovery is used.
#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include "hardware/flash.h"
#include "hardware/sync.h"
#include "pico/stdlib.h"
#include "trace_store.h"
#ifdef ICE_DISPATCHER
#include "hardware/xip_cache.h"
#endif

#define RECORD_MAGIC 0x56434431u
#ifdef ICE_DISPATCHER
// The large timing ring owns SRAM banks 4..7; legacy VCD formatting uses a
// distinct PSRAM region, away from module staging and new capture records.
#define vcd ((char *)0x11200000u)
#else
static char vcd[TRACE_VCD_CAPACITY] __attribute__((aligned(256)));
#endif
static size_t used;
static bool full;
extern char __flash_binary_end;

uint32_t trace_crc32(const void *data, size_t length) {
    const uint8_t *p = data;
    uint32_t crc = UINT32_MAX;
    while (length--) {
        crc ^= *p++;
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

static const trace_record *record_address(unsigned bank) {
    return (const trace_record *)(XIP_BASE + TRACE_STORE_OFFSET + bank * TRACE_SLOT_BYTES);
}

const uint8_t *trace_record_data(unsigned bank) {
    return (const uint8_t *)record_address(bank) + FLASH_SECTOR_SIZE;
}

const trace_record *trace_record_get(unsigned bank) {
    if (bank > 1) return NULL;
    const trace_record *r = record_address(bank);
    if (r->magic != RECORD_MAGIC || r->version != 1 || r->committed != 0 || r->bank != bank ||
        r->samples != TRACE_SAMPLES || r->gpio_base != (bank ? 32u : 0u) ||
        r->pin_count != (bank ? 13u : 32u) || !r->sample_hz || !r->bytes ||
        r->bytes > TRACE_VCD_CAPACITY) return NULL;
    return trace_crc32(trace_record_data(bank), r->bytes) == r->crc32 ? r : NULL;
}

static void append(const char *format, ...) {
    if (full) return;
    va_list args;
    va_start(args, format);
    int n = vsnprintf(vcd + used, TRACE_VCD_CAPACITY - used, format, args);
    va_end(args);
    if (n < 0 || (size_t)n >= TRACE_VCD_CAPACITY - used) full = true;
    else used += (size_t)n;
}

bool trace_store_save(unsigned bank, const uint32_t *samples, uint32_t hz, uint32_t fdebug) {
    return trace_store_save_trigger(bank,samples,hz,fdebug,UINT32_MAX,0);
}

bool trace_store_save_trigger(unsigned bank, const uint32_t *samples, uint32_t hz,
                              uint32_t fdebug, uint32_t trigger_gpio, uint32_t trigger_level) {
    if (bank > 1 || !hz || (uintptr_t)&__flash_binary_end > XIP_BASE + TRACE_STORE_OFFSET) return false;
    const trace_record *old = record_address(bank);
    // Never erase unknown contents in the reserved tail of an existing board.
    if (old->magic != RECORD_MAGIC || old->version != 1) {
        const uint32_t *p = (const uint32_t *)old;
        for (size_t i = 0; i < TRACE_SLOT_BYTES / 4; ++i) if (p[i] != UINT32_MAX) return false;
    }
    unsigned base = bank ? 32 : 0, count = bank ? 13 : 32;
    uint32_t mask = bank ? 0x1fffu : UINT32_MAX;
    used = 0;
    full = false;
    append("$date device has no RTC $end\n$version 68008ice PIO bench 0.1 $end\n"
           "$comment 1024 raw samples; clk_sys=%" PRIu32 " Hz; PIO divider=1; fdebug=0x%08" PRIx32
           "; independent generator/receiver crystals; separate bank capture $end\n"
           "$timescale 1ps $end\n$scope module gpio $end\n", hz, fdebug);
    if(trigger_gpio<=44)
        append("$comment level trigger GPIO%" PRIu32 "=%" PRIu32
               "; PIO/DMA start latency precedes sample zero $end\n",trigger_gpio,trigger_level);
    for (unsigned pin = base; pin < base + count; ++pin)
        append("$var wire 1 g%02u GPIO%u $end\n", pin, pin);
    append("$upscope $end\n$enddefinitions $end\n");
    uint32_t previous = 0;
    for (unsigned i = 0; i < TRACE_SAMPLES; ++i) {
        uint32_t value = samples[i] & mask;
        append("#%llu\n", (unsigned long long)i * UINT64_C(1000000000000) / hz);
        uint32_t changed = i ? value ^ previous : mask;
        for (unsigned bit = 0; bit < count; ++bit)
            if (changed & (1u << bit)) append("%ug%02u\n", (value >> bit) & 1u, base + bit);
        previous = value;
    }
    if (full) return false;
    trace_record header = {.magic=RECORD_MAGIC, .version=1, .committed=UINT32_MAX,
        .bank=bank, .gpio_base=base, .pin_count=count, .samples=TRACE_SAMPLES,
        .sample_hz=hz, .bytes=(uint32_t)used, .crc32=trace_crc32(vcd, used), .fdebug=fdebug,
        .reserved={trigger_gpio<=44 ? trigger_gpio+1 : 0,trigger_level,0,0,0}};
    uint8_t page[FLASH_PAGE_SIZE] __attribute__((aligned(4)));
    memset(page, 0xff, sizeof page);
    memcpy(page, &header, sizeof header);
    size_t padded = (used + FLASH_PAGE_SIZE - 1) & ~(FLASH_PAGE_SIZE - 1);
    memset(vcd + used, 0xff, padded - used);
#ifdef ICE_DISPATCHER
    xip_cache_clean_all();
#endif
    uint32_t offset = TRACE_STORE_OFFSET + bank * TRACE_SLOT_BYTES;
    // Core 1 stays parked in ROM. The PIO/DMA transfer and USB detach finish
    // before this section. SDK flash routines execute from SRAM as required.
    uint32_t irq = save_and_disable_interrupts();
    flash_range_erase(offset, TRACE_SLOT_BYTES);
    flash_range_program(offset, page, sizeof page); // ownership, not committed
#ifdef ICE_DISPATCHER
    // Flash routines temporarily exit XIP, including PSRAM access. Stage
    // each page in SRAM before entering them, never pass a PSRAM pointer.
    for(size_t at=0;at<padded;at+=sizeof page) {
        memcpy(page,vcd+at,sizeof page);
        flash_range_program(offset+FLASH_SECTOR_SIZE+at,page,sizeof page);
    }
    memset(page,0xff,sizeof page);
#else
    flash_range_program(offset + FLASH_SECTOR_SIZE, (const uint8_t *)vcd, padded);
#endif
    header.committed = 0;
    memcpy(page, &header, sizeof header);
    flash_range_program(offset, page, sizeof page); // final 1 -> 0 commit
    restore_interrupts(irq);
    return trace_record_get(bank) != NULL;
}
