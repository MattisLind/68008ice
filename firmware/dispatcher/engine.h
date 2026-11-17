// SPDX-License-Identifier: Apache-2.0
#include "app_abi.h"
#include <stdbool.h>
extern const app_api engine_api;
void engine_init(void);
void engine_set_bus_mode(bool enabled);
