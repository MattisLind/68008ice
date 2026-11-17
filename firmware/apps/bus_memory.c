// SPDX-License-Identifier: Apache-2.0
#include "app_abi.h"
void __attribute__((section(".entry"))) app_main(app_job *job, const app_api *api) {
    if (api->abi != APP_ABI) {job->error=1;return;}
    api->extended(job,APP_BUS_MEMORY);
}
