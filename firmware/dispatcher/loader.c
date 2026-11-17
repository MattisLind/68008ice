// SPDX-License-Identifier: Apache-2.0
#include <string.h>
#include "loader.h"
#include "protocol.h"
#include "hardware/flash.h"
#include "hardware/gpio.h"
#include "hardware/psram.h"
#include "hardware/sync.h"
#include "hardware/xip_cache.h"
#include "pico/stdlib.h"
#include "app_generator.h"
#include "app_analyzer.h"
#include "app_bus_generator.h"
#include "app_bus_memory.h"
#include "app_state_analyzer.h"
#include "app_cpu_emulator.h"
#define PSRAM_IMAGE ((uint8_t *)0x11000000u)
uint32_t loader_app,loader_source,loader_crc,loader_bytes,loader_psram;
static uint32_t upload_bytes,upload_used;
static bool uploaded;
const app_header *loader_builtin(uint32_t app) {
    if(app==APP_GENERATOR)return (const app_header *)app_image_1;
    if(app==APP_ANALYZER)return (const app_header *)app_image_2;
    if(app==APP_BUS_GENERATOR)return (const app_header *)app_image_3;
    if(app==APP_BUS_MEMORY)return (const app_header *)app_image_4;
    if(app==APP_STATE_ANALYZER)return (const app_header *)app_image_5;
    if(app==APP_CPU_EMULATOR)return (const app_header *)app_image_6;
    return NULL;
}
static bool valid(const app_header *h,uint32_t total) {
    return total>=sizeof *h && h->magic==APP_MAGIC && h->abi==APP_ABI &&
        (h->app>=APP_GENERATOR && h->app<=APP_CPU_EMULATOR) && h->address==APP_ADDRESS &&
        h->bytes && h->bytes<=APP_CAPACITY && h->bytes==total-sizeof *h &&
        (h->entry&1) && h->entry<h->bytes && h->entry==1 &&
        h->crc==protocol_crc(h+1,h->bytes);
}
int loader_init_psram(void) {
    // Exact board wiring/size only: no probing GPIO0/8/19.
    gpio_pull_up(47);gpio_set_function(47,GPIO_FUNC_XIP_CS1);sleep_ms(1);
    uint32_t irq=save_and_disable_interrupts();
    flash_devinfo_set_cs_gpio(1,47);
    flash_devinfo_set_cs_size(1,flash_devinfo_bytes_to_size(8388608));
    // The bootrom XIP exit sequence resets SPI/QPI state before issuing commands.
    int ok=psram_configure_params(75000000,8000,50)==PICO_OK && psram_reinitialize()==PICO_OK;
    restore_interrupts(irq);
    if(!ok)return 0;
    // Uncached accesses prove the module staging area and the far end, not
    // merely cache contents. These locations belong to this dispatcher.
    volatile uint32_t *p=(volatile uint32_t *)0x15000000u;
    for(unsigned i=0;i<1024;++i)p[i]=0x9365a700u^i;
    for(unsigned i=0;i<8;++i)p[(i*1048576u+16384u)/4]=0x154c8000u^i;
    p[8388608/4-1]=0x5a81c37e;
    __dmb();
    for(unsigned i=0;i<1024;++i)if(p[i]!=(0x9365a700u^i))return 0;
    for(unsigned i=0;i<8;++i)if(p[(i*1048576u+16384u)/4]!=(0x154c8000u^i))return 0;
    if(p[8388608/4-1]!=0x5a81c37e)return 0;
    loader_psram=8388608;return 1;
}
int loader_load(uint32_t app,uint32_t source) {
    const app_header *h=loader_builtin(app);
    if(!h || source>2)return 1;
    uint32_t total=sizeof *h+h->bytes;
    if(source) {
        if(!loader_psram)return 4;
        if(source==1) {memcpy(PSRAM_IMAGE,h,total);uploaded=false;}
        else {if(!uploaded)return 3;total=upload_bytes;}
        __dmb();xip_cache_clean_all();
        h=(const app_header *)PSRAM_IMAGE;
    }
    if(!valid(h,total) || h->app!=app)return 3;
    memcpy((void *)APP_ADDRESS,h+1,h->bytes);__dmb();__isb();
    if(protocol_crc((void *)APP_ADDRESS,h->bytes)!=h->crc)return 3;
    loader_app=app;loader_source=source;loader_crc=h->crc;loader_bytes=h->bytes;
    return 0;
}
int loader_upload_begin(uint32_t bytes) {
    if(!loader_psram)return 4;
    if(bytes<sizeof(app_header)+2 || bytes>sizeof(app_header)+APP_CAPACITY)return 1;
    upload_bytes=bytes;upload_used=0;uploaded=false;return 0;
}
int loader_upload_write(uint32_t offset,const void *data,uint32_t bytes) {
    if(!loader_psram)return 4;
    if(!upload_bytes || offset!=upload_used || bytes>upload_bytes-upload_used)return 1;
    memcpy(PSRAM_IMAGE+offset,data,bytes);upload_used+=bytes;return 0;
}
int loader_upload_commit(void) {
    if(!loader_psram)return 4;
    __dmb();xip_cache_clean_all();
    if(upload_used!=upload_bytes || !valid((const app_header *)PSRAM_IMAGE,upload_bytes))return 3;
    uploaded=true;return 0;
}
