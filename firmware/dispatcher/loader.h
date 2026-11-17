// SPDX-License-Identifier: Apache-2.0
#include "app_abi.h"
int loader_init_psram(void);
int loader_load(uint32_t app,uint32_t source);
const app_header *loader_builtin(uint32_t app);
int loader_upload_begin(uint32_t bytes);
int loader_upload_write(uint32_t offset,const void *,uint32_t bytes);
int loader_upload_commit(void);
extern uint32_t loader_app,loader_source,loader_crc,loader_bytes,loader_psram;
