// SPDX-License-Identifier: Apache-2.0
// Read-only FAT12 superfloppy generated from the flash-resident VCD records.
#include <string.h>
#include "pico/stdlib.h"
#include "trace_store.h"

enum { SECTORS=2048, FAT_SECTORS=6, ROOT_SECTOR=13, DATA_SECTOR=15 };
static const char readme[] =
    "RP2350 PIO capture retrieval disk\r\n"
    "LOW32.VCD: GPIO0..31, 1024 samples.\r\n"
    "HIGH13.VCD: GPIO32..44, 1024 samples.\r\n"
    "The files are separate runs, not a simultaneous 45-bit capture.\r\n"
    "Captures are stored in flash and survive a reboot.\r\n"
#ifdef ICE_DISPATCHER
    "Use the USB CDC 'disk on' command for file retrieval.\r\n"
    "Return to 'disk off' before loading or starting an application.\r\n"
#else
    "This read-only disk disconnects during acquisition.\r\n"
#endif
    "ROM BOOTSEL has its own UF2 disk and cannot show these files.\r\n";
typedef struct {const uint8_t *data; uint32_t bytes; uint16_t first, clusters; const char *name;} disk_file;
static disk_file files[3];
static unsigned file_count;
static uint8_t fat[FAT_SECTORS * 512];
static void put16(uint8_t *p, uint16_t n) {p[0]=n; p[1]=n>>8;}
static void put32(uint8_t *p, uint32_t n) {put16(p,n); put16(p+2,n>>16);}
static void fat_entry(unsigned cluster, unsigned value) {
    unsigned offset = cluster + cluster/2;
    if (cluster & 1) {fat[offset]=(fat[offset]&15)|(value<<4); fat[offset+1]=value>>4;}
    else {fat[offset]=value; fat[offset+1]=(fat[offset+1]&0xf0)|((value>>8)&15);}
}

void trace_disk_refresh(void) {
    memset(fat,0,sizeof fat);
    fat_entry(0,0xff8); fat_entry(1,0xfff);
    file_count=1;
    files[0]=(disk_file){(const uint8_t *)readme,sizeof readme-1,2,1,"README  TXT"};
    unsigned next=3;
    for (unsigned bank=0;bank<2;++bank) {
        const trace_record *r=trace_record_get(bank);
        if (!r) continue;
        unsigned clusters=(r->bytes+511)/512;
        files[file_count++]=(disk_file){trace_record_data(bank),r->bytes,next,clusters,
                                      bank ? "HIGH13  VCD" : "LOW32   VCD"};
        next+=clusters;
    }
    for (unsigned f=0;f<file_count;++f)
        for (unsigned i=0;i<files[f].clusters;++i)
            fat_entry(files[f].first+i,i+1==files[f].clusters ? 0xfff : files[f].first+i+1);
}

void trace_disk_sector(uint32_t sector,uint8_t data[512]) {
    memset(data,0,512);
    if (sector==0) {
        data[0]=0xeb;data[1]=0x3c;data[2]=0x90;memcpy(data+3,"ICEPIO  ",8);
        put16(data+11,512);data[13]=1;put16(data+14,1);data[16]=2;put16(data+17,32);
        put16(data+19,SECTORS);data[21]=0xf8;put16(data+22,FAT_SECTORS);
        put16(data+24,1);put16(data+26,1);data[36]=0x80;data[38]=0x29;
        put32(data+39,0x50494f31);memcpy(data+43,"ICECAP     ",11);memcpy(data+54,"FAT12   ",8);
        data[510]=0x55;data[511]=0xaa;
    } else if (sector>=1 && sector<ROOT_SECTOR) {
        memcpy(data,fat+((sector-1)%FAT_SECTORS)*512,512);
    } else if (sector==ROOT_SECTOR) {
        memcpy(data,"ICECAP     ",11);data[11]=8;
        for (unsigned f=0;f<file_count;++f) {
            uint8_t *entry=data+32*(f+1);
            memcpy(entry,files[f].name,11);entry[11]=0x21; // archive, read-only
            put16(entry+24,0x21); // no RTC: 1980-01-01
            put16(entry+26,files[f].first);put32(entry+28,files[f].bytes);
        }
    } else if (sector>=DATA_SECTOR && sector<SECTORS) {
        unsigned cluster=sector-DATA_SECTOR+2;
        for (unsigned f=0;f<file_count;++f) {
            if (cluster<files[f].first || cluster>=files[f].first+files[f].clusters) continue;
            unsigned offset=(cluster-files[f].first)*512;
            unsigned bytes=files[f].bytes-offset;
            if (bytes>512) bytes=512;
            memcpy(data,files[f].data+offset,bytes);
        }
    }
}
