/*
 * Descriptor setup adapted from TinyUSB's cdc_msc example.
 * Copyright (c) 2019 Ha Thach (tinyusb.org)
 * SPDX-License-Identifier: MIT
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */
#include <string.h>
#include "pico/bootrom.h"
#include "pico/stdlib.h"
#include "tusb.h"
#include "trace_store.h"
#include "trace_usb.h"

extern char board_id[17];
#if CFG_TUD_MSC
static bool ejected;
#endif
static const tusb_desc_device_t device = {
    .bLength=sizeof(tusb_desc_device_t), .bDescriptorType=TUSB_DESC_DEVICE, .bcdUSB=0x0200,
    .bDeviceClass=TUSB_CLASS_MISC, .bDeviceSubClass=MISC_SUBCLASS_COMMON,
    .bDeviceProtocol=MISC_PROTOCOL_IAD, .bMaxPacketSize0=64,
    .idVendor=0xcafe,
#ifdef ICE_DISPATCHER
    .idProduct=0x4004,
#else
    .idProduct=0x4003,
#endif
#ifdef ICE_DISPATCHER
    .bcdDevice=0x0200,
#else
    .bcdDevice=0x0100,
#endif
    .iManufacturer=1, .iProduct=2, .iSerialNumber=3, .bNumConfigurations=1,
};
static const uint8_t config[] = {
    TUD_CONFIG_DESCRIPTOR(1,2+CFG_TUD_MSC,0,
        TUD_CONFIG_DESC_LEN+TUD_CDC_DESC_LEN+CFG_TUD_MSC*TUD_MSC_DESC_LEN,0,100),
    TUD_CDC_DESCRIPTOR(0,4,0x81,8,0x02,0x82,64),
#if CFG_TUD_MSC
    TUD_MSC_DESCRIPTOR(2,5,0x03,0x83,64),
#endif
};
uint8_t const *tud_descriptor_device_cb(void) {return (const uint8_t *)&device;}
uint8_t const *tud_descriptor_configuration_cb(uint8_t index) {(void)index;return config;}
uint16_t const *tud_descriptor_string_cb(uint8_t index,uint16_t langid) {
    (void)langid;
    static uint16_t result[33];
    static const char *const strings[]={"","68008ice bench",
#ifdef ICE_DISPATCHER
        "ICE Dispatcher",
#else
        "ICE PIO Receiver",
#endif
        NULL,"Command CDC","Capture files"};
    if (!index) {result[0]=0x0304;result[1]=0x0409;return result;}
    if (index>=6) return NULL;
    const char *text=index==3 ? board_id : strings[index];
    unsigned n=strlen(text);if(n>32)n=32;
    for(unsigned i=0;i<n;++i)result[i+1]=(uint8_t)text[i];
    result[0]=(TUSB_DESC_STRING<<8)|(2*n+2);return result;
}
void tud_cdc_line_coding_cb(uint8_t itf,const cdc_line_coding_t *coding) {
    (void)itf;
    if(coding->bit_rate==1200)reset_usb_boot(0,0);
}
void trace_usb_init(void) {
#if CFG_TUD_MSC
    trace_disk_refresh();
#endif
    tud_init(0);
}
void trace_usb_task(void) {tud_task_ext(0,false);}
void trace_usb_detach(void) {tud_disconnect();sleep_ms(100);}
void trace_usb_attach(void) {
#if CFG_TUD_MSC
    trace_disk_refresh();ejected=false;
#endif
    tud_connect();
}
#if CFG_TUD_MSC
void tud_msc_inquiry_cb(uint8_t lun,uint8_t vendor[8],uint8_t product[16],uint8_t rev[4]) {
    (void)lun;memcpy(vendor,"ICE     ",8);memcpy(product,"PIO CAPTURE     ",16);memcpy(rev,"0100",4);
}
bool tud_msc_test_unit_ready_cb(uint8_t lun) {
    if(ejected)tud_msc_set_sense(lun,SCSI_SENSE_NOT_READY,0x3a,0);
    return !ejected;
}
void tud_msc_capacity_cb(uint8_t lun,uint32_t *count,uint16_t *size) {(void)lun;*count=2048;*size=512;}
bool tud_msc_start_stop_cb(uint8_t lun,uint8_t power,bool start,bool eject) {
    (void)lun;(void)power;if(eject)ejected=!start;return true;
}
bool tud_msc_is_writable_cb(uint8_t lun) {(void)lun;return false;}
int32_t tud_msc_read10_cb(uint8_t lun,uint32_t lba,uint32_t offset,void *buffer,uint32_t bytes) {
    (void)lun;
    if((uint64_t)lba*512+offset+bytes>2048u*512u)return -1;
    uint8_t sector[512];uint8_t *out=buffer;unsigned copied=0;
    while(copied<bytes) {
        trace_disk_sector(lba+offset/512,sector);
        unsigned at=offset%512,n=512-at;if(n>bytes-copied)n=bytes-copied;
        memcpy(out+copied,sector+at,n);copied+=n;offset+=n;
    }
    return bytes;
}
int32_t tud_msc_write10_cb(uint8_t lun,uint32_t lba,uint32_t offset,uint8_t *buffer,uint32_t bytes) {
    (void)lba;(void)offset;(void)buffer;(void)bytes;
    tud_msc_set_sense(lun,SCSI_SENSE_DATA_PROTECT,0x27,0);return -1;
}
int32_t tud_msc_scsi_cb(uint8_t lun,const uint8_t command[16],void *buffer,uint16_t bytes) {
    (void)buffer;(void)bytes;
    if(command[0]==SCSI_CMD_PREVENT_ALLOW_MEDIUM_REMOVAL)return 0;
    tud_msc_set_sense(lun,SCSI_SENSE_ILLEGAL_REQUEST,0x20,0);return -1;
}
#endif
