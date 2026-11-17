// SPDX-License-Identifier: Apache-2.0
// Raw capture storage before the two legacy VCD slots; never erase unknown
// contents. VCD generation happens on the host, without a file-size limit.
#include <string.h>
#include "capture.h"
#include "protocol.h"
#include "trace_store.h"
#include "hardware/flash.h"
#include "hardware/sync.h"
#include "hardware/xip_cache.h"
#include "pico/stdlib.h"
#define SLOT_BYTES (1024u*1024u)
#define STORE_OFFSET (TRACE_STORE_OFFSET-2*SLOT_BYTES)
extern char __flash_binary_end;
static bool checked[2],valid[2];
static const capture_record *address(uint32_t bank) {
    return (const capture_record *)(XIP_BASE+STORE_OFFSET+bank*SLOT_BYTES);
}
const uint8_t *capture_saved_data(uint32_t bank) {
    return (const uint8_t *)address(bank)+FLASH_SECTOR_SIZE;
}
const capture_record *capture_saved(uint32_t bank) {
    if(bank>1)return NULL;
    const capture_record *r=address(bank);
    if(checked[bank])return valid[bank] ? r : NULL;
    checked[bank]=true;valid[bank]=false;
    if(r->magic!=CAPTURE_MAGIC || r->version!=1 || r->committed || r->bank!=bank ||
       (r->app!=APP_ANALYZER && r->app!=APP_BUS_MEMORY && r->app!=APP_STATE_ANALYZER) ||
       ((r->flags&CAPTURE_MEMORY_TIMING) && (r->app!=APP_BUS_MEMORY || r->bank ||
          r->capacity>CAPTURE_FAST_MAX || r->hz!=CAPTURE_FAST_HZ)) ||
       r->stride!=((r->app==APP_ANALYZER || (r->flags&CAPTURE_MEMORY_TIMING)) ? 4u : 12u) ||
       !r->capacity || r->capacity>CAPTURE_MAX ||
       r->count>r->capacity || r->bytes!=r->count*r->stride || !r->hz ||
       (r->trigger!=CAPTURE_NO_TRIGGER && r->trigger>=r->count) ||
       (r->pre_percent!=10 && r->pre_percent!=50 && r->pre_percent!=90))return NULL;
    valid[bank]=protocol_crc(capture_saved_data(bank),r->bytes)==r->crc;
    return valid[bank] ? r : NULL;
}
bool capture_save(void) {
    capture_record h=capture_result;
    if(h.bank>1 || (uintptr_t)&__flash_binary_end>XIP_BASE+STORE_OFFSET)return false;
    const capture_record *old=address(h.bank);
    if(old->magic!=CAPTURE_MAGIC || old->version!=1) {
        const uint32_t *p=(const uint32_t *)old;
        for(uint32_t i=0;i<SLOT_BYTES/4;++i)if(p[i]!=UINT32_MAX)return false;
    }
    const uint8_t *ring=(const uint8_t *)0x11040000;
    uint32_t start=h.reserved*h.stride,ring_bytes=h.capacity*h.stride;
    uint32_t crc=UINT32_MAX;
    for(uint32_t i=0;i<h.bytes;++i) {
        crc^=ring[(start+i)%ring_bytes];
        for(unsigned bit=0;bit<8;++bit)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1)));
    }
    h.crc=~crc;h.reserved=capture_settings.strobe|(capture_settings.edge<<1);
    uint32_t offset=STORE_OFFSET+h.bank*SLOT_BYTES;
    xip_cache_clean_all();
    uint8_t page[FLASH_PAGE_SIZE] __attribute__((aligned(4)));
    memset(page,255,sizeof page);memcpy(page,&h,sizeof h);
    uint32_t irq=save_and_disable_interrupts();
    // Erase just the new record extent. Any older trailing pages are ignored
    // by the committed header; unknown partitions are refused above.
    uint32_t erase=FLASH_SECTOR_SIZE+((h.bytes+FLASH_SECTOR_SIZE-1)&~(FLASH_SECTOR_SIZE-1));
    flash_range_erase(offset,erase);
    flash_range_program(offset,page,sizeof page);
    for(uint32_t at=0;at<h.bytes;at+=sizeof page) {
        memset(page,255,sizeof page);
        uint32_t count=h.bytes-at<sizeof page ? h.bytes-at : sizeof page;
        for(uint32_t i=0;i<count;++i)page[i]=ring[(start+at+i)%ring_bytes];
        flash_range_program(offset+FLASH_SECTOR_SIZE+at,page,sizeof page);
    }
    h.committed=0;memset(page,255,sizeof page);memcpy(page,&h,sizeof h);
    flash_range_program(offset,page,sizeof page);
    restore_interrupts(irq);
    capture_result=h;
    checked[h.bank]=false;
    return capture_saved(h.bank)!=NULL;
}
