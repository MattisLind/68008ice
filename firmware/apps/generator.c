// SPDX-License-Identifier: Apache-2.0
#include "app_abi.h"
void __attribute__((section(".entry"))) app_main(app_job *job, const app_api *api) {
    if (api->abi != APP_ABI || !(job->flags & FLAG_DRIVE)) {job->error=1; return;}
    unsigned width=job->bank ? 13 : 32;
    uint32_t value=(job->flags & FLAG_INITIAL_HIGH) ? (job->bank ? 0x1fffu : UINT32_MAX) : 0;
    unsigned bit=0;
    for (unsigned i=0;i<2048;++i) {
        value^=1u<<bit;api->pattern[i]=value;
        if (++bit==width)bit=0;
    }
    if (!api->prepare(job,1)) return;
    job->state=JOB_ARMED;
    if (api->wait_start(job)) {job->state=JOB_RUNNING;api->transfer(job,1);}
    api->release();
}
