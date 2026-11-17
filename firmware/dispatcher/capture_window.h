// SPDX-License-Identifier: Apache-2.0
#ifndef ICE_CAPTURE_WINDOW_H
#define ICE_CAPTURE_WINDOW_H
#include <stdbool.h>
#include <stdint.h>
#define CAPTURE_MAX 65536u
#define CAPTURE_NO_TRIGGER UINT32_MAX
// The trigger record is the first post-trigger record. Integer percentages
// round down; capacity 1 therefore contains just the trigger record.
typedef struct {
    uint32_t capacity, pre, next, count, trigger, post_left, total;
    bool triggered, done;
} capture_window;
bool capture_window_init(capture_window *, uint32_t capacity, uint32_t percent);
// Call before writing the record; returns its physical ring slot.
uint32_t capture_window_push(capture_window *, bool match);
uint32_t capture_window_start(const capture_window *);
uint32_t capture_window_trigger(const capture_window *);
// Recover the sampled edge near the stop-pointer/timer estimate, then select
// an exact pre/post window from the stopped circular timing buffer.
bool capture_timing_window(const uint32_t *ring,uint32_t words,uint32_t snapshot,
    uint32_t end,uint32_t capacity,uint32_t pre,uint32_t pin,uint32_t level,uint32_t *start);
#endif
