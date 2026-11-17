// SPDX-License-Identifier: Apache-2.0
#include "generic_memory.h"
#include "cpu68008.h"
int generic_memory_access(const memory_image *image,uint8_t *ram,uint32_t address,uint32_t fc,bool write,uint8_t *value) {
    if(!image->ready || address>=TARGET_MEMORY_BYTES || (fc!=1 && fc!=2 && fc!=5 && fc!=6) ||
       (write && address<image->bytes))return CPU_BUS_BERR;
    if(write)ram[address]=*value;else *value=ram[address];
    return CPU_BUS_OK;
}
