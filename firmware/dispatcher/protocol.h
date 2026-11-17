// SPDX-License-Identifier: Apache-2.0
#ifndef ICE_PROTOCOL_H
#define ICE_PROTOCOL_H
#include <stddef.h>
#include <stdint.h>
#define PROTOCOL_PAYLOAD 256u
typedef struct {uint8_t bytes[268];uint16_t used;uint8_t active,escape;} protocol_rx;
typedef void (*protocol_command)(uint8_t,uint16_t,const uint8_t *,uint16_t,uint32_t);
uint32_t protocol_crc(const void *,size_t);
void protocol_byte(protocol_rx *,uint8_t,protocol_command);
size_t protocol_encode(uint8_t,uint16_t,uint16_t,const void *,uint16_t,uint8_t *);
#endif
