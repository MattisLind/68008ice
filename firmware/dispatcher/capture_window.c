// SPDX-License-Identifier: Apache-2.0
#include "capture_window.h"
bool capture_window_init(capture_window *w,uint32_t capacity,uint32_t percent) {
    if(!capacity || capacity>CAPTURE_MAX || (percent!=10 && percent!=50 && percent!=90))return false;
    *w=(capture_window){.capacity=capacity,.pre=capacity*percent/100,.trigger=CAPTURE_NO_TRIGGER};
    return true;
}
uint32_t capture_window_push(capture_window *w,bool match) {
    uint32_t slot=w->next;
    if(w->done)return CAPTURE_NO_TRIGGER;
    // Arm the comparator after collecting the requested history. This gives
    // the selected ratio even when a matching level was present at RUN.
    if(!w->triggered && match && w->count>=w->pre) {
        w->triggered=true;w->trigger=w->total;
        w->count=w->pre;
        w->post_left=w->capacity-w->pre;
    }
    w->next=(slot+1)%w->capacity;
    if(w->count<w->capacity)++w->count;
    ++w->total;
    if(w->triggered && !--w->post_left)w->done=true;
    return slot;
}
uint32_t capture_window_start(const capture_window *w) {
    return (w->next+w->capacity-w->count)%w->capacity;
}
uint32_t capture_window_trigger(const capture_window *w) {
    return w->triggered ? w->trigger-(w->total-w->count) : CAPTURE_NO_TRIGGER;
}
bool capture_timing_window(const uint32_t *ring,uint32_t words,uint32_t snapshot,
    uint32_t end,uint32_t capacity,uint32_t pre,uint32_t pin,uint32_t level,uint32_t *start) {
    if(words<512 || (words&(words-1)) || !capacity || capacity>words/2 || pre>=capacity ||
       pin>31 || level>1 || snapshot>=words || end>=words)return false;
    uint32_t mask=words-1,found=CAPTURE_NO_TRIGGER;
    for(uint32_t i=0;i<144;++i) {
        uint32_t at=(snapshot+words-128+i)&mask;
        if(((ring[at]>>pin)&1)==level && ((ring[(at-1)&mask]>>pin)&1)!=level) {
            if(found!=CAPTURE_NO_TRIGGER)return false; // ambiguous edge, never guess
            found=at;
        }
    }
    if(found==CAPTURE_NO_TRIGGER)return false;
    uint32_t after=(end+words-found)&mask;
    if(after<capacity-pre || after+pre>words)return false;
    *start=(found+words-pre)&mask;
    return true;
}
