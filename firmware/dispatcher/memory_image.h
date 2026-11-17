// SPDX-License-Identifier: Apache-2.0
#ifndef ICE_MEMORY_IMAGE_H
#define ICE_MEMORY_IMAGE_H
#include <stdint.h>
#define TARGET_MEMORY_BYTES 1048576u
#define TARGET_MEMORY ((uint8_t *)0x11200000u)
typedef struct {uint32_t version,capacity,bytes,crc,used,ready;} memory_image;
extern memory_image target_image;
int memory_image_begin(memory_image *,uint8_t *,uint32_t bytes,uint32_t crc);
int memory_image_write(memory_image *,uint8_t *,uint32_t offset,const void *,uint32_t bytes);
int memory_image_commit(memory_image *,const uint8_t *);
#endif
