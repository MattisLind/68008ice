// SPDX-License-Identifier: Apache-2.0
#include "app_abi.h"
void __attribute__((section(".entry"))) app_main(app_job *job, const app_api *api) {
    if (api->abi != APP_ABI) {job->error=1;return;}
    if (api->extended(job,APP_ANALYZER)) return;
    if (!api->prepare(job,0)) return;
    job->state=JOB_ARMED;
    api->transfer(job,0);
    api->release();
}
