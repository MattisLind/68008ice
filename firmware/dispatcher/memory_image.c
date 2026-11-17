// SPDX-License-Identifier: Apache-2.0
#include <string.h>
#include "memory_image.h"
#include "protocol.h"
memory_image target_image;
int memory_image_begin(memory_image *m,uint8_t *ram,uint32_t bytes,uint32_t crc) {
    if(bytes<8 || bytes>TARGET_MEMORY_BYTES)return 1;
    *m=(memory_image){.version=1,.capacity=TARGET_MEMORY_BYTES,.bytes=bytes,.crc=crc};
    memset(ram,0,TARGET_MEMORY_BYTES);return 0;
}
int memory_image_write(memory_image *m,uint8_t *ram,uint32_t offset,const void *data,uint32_t bytes) {
    if(!m->version || m->ready || !bytes || bytes>252 || offset!=m->used || bytes>m->bytes-m->used)return 1;
    memcpy(ram+offset,data,bytes);m->used+=bytes;return 0;
}
int memory_image_commit(memory_image *m,const uint8_t *ram) {
    if(!m->version || m->used!=m->bytes || protocol_crc(ram,m->bytes)!=m->crc)return 3;
    m->ready=1;return 0;
}
