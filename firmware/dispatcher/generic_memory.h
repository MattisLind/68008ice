// SPDX-License-Identifier: Apache-2.0
#ifndef ICE_GENERIC_MEMORY_H
#define ICE_GENERIC_MEMORY_H
#include <stdbool.h>
#include "memory_image.h"
int generic_memory_access(const memory_image *,uint8_t *,uint32_t address,uint32_t fc,bool write,uint8_t *);
#endif
