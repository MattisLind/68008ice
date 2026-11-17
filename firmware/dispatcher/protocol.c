// SPDX-License-Identifier: Apache-2.0
#include "protocol.h"
#include <string.h>
static uint16_t get16(const uint8_t *p) {return p[0]|((uint16_t)p[1]<<8);}
static void put16(uint8_t *p,uint16_t n) {p[0]=n;p[1]=n>>8;}
uint32_t protocol_crc(const void *data,size_t length) {
    const uint8_t *p=data;uint32_t crc=UINT32_MAX;
    while(length--) {crc^=*p++;for(unsigned b=0;b<8;++b)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1)));}
    return ~crc;
}
static void finish(protocol_rx *r,protocol_command command) {
    if (r->used<12 || r->bytes[0]!=1 || r->bytes[1]&0x80 || get16(r->bytes+6))return;
    uint16_t length=get16(r->bytes+4);
    if(length>PROTOCOL_PAYLOAD || r->used!=length+12)return;
    uint32_t crc;memcpy(&crc,r->bytes+8+length,4);
    if(crc!=protocol_crc(r->bytes,length+8))return;
    command(r->bytes[1],get16(r->bytes+2),r->bytes+8,length,crc);
}
void protocol_byte(protocol_rx *r,uint8_t b,protocol_command command) {
    if(r->escape) {
        r->escape=0;
        if(b==0) {r->active=1;r->used=0;return;}
        if(b==1) {if(r->active)finish(r,command);r->active=0;return;}
        if(b!=255) {r->active=0;r->used=0;return;}
    } else if(b==255) {r->escape=1;return;}
    if(!r->active)return;
    if(r->used==sizeof r->bytes) {r->active=0;r->used=0;return;}
    r->bytes[r->used++]=b;
}
size_t protocol_encode(uint8_t command,uint16_t seq,uint16_t status,const void *payload,uint16_t length,uint8_t *out) {
    uint8_t raw[268];raw[0]=1;raw[1]=command;put16(raw+2,seq);put16(raw+4,length);put16(raw+6,status);
    if(length)memcpy(raw+8,payload,length);
    uint32_t crc=protocol_crc(raw,length+8);memcpy(raw+length+8,&crc,4);
    size_t n=0;out[n++]=255;out[n++]=0;
    for(unsigned i=0;i<length+12u;++i) {out[n++]=raw[i];if(raw[i]==255)out[n++]=255;}
    out[n++]=255;out[n++]=1;return n;
}
