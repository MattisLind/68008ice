// SPDX-License-Identifier: Apache-2.0
// Standalone Core2350B wiring fixture, NOT the 68008 ICE adapter.
// GPIO0..44 (45 pins) are tested; GPIO45..47, QSPI, USB and SWD are excluded.
// The debugger commands one output at a time, LOW then HIGH; all other test
// pins remain inputs. GPIO39 includes the bench board's passive LED load.
#include <stddef.h>
#include <stdint.h>
#include "hardware/structs/powman.h"
#include "hardware/sync.h"
#include "pico/stdlib.h"
#include "pico/unique_id.h"

#if ICE_SWD_INSTANCE_ID != 1 && ICE_SWD_INSTANCE_ID != 2
#error Connectivity fixture requires SWD instance 1 or 2
#endif

#define PIN_COUNT 45u
#define NO_PIN UINT32_MAX
#define TEST_MASK ((UINT64_C(1) << PIN_COUNT) - 1)
#define DRIVE_LEASE_MS 1000u

// Versioned debugger mailbox, all fields uint32_t so host offsets are explicit.
// Write pin/pull fields first, request_seq last; wait for completed_seq before
// reading GPIOs. No application USB protocol is involved in this bench test.
typedef struct {
    uint32_t magic;
    uint32_t version;
    uint32_t request_seq;
    uint32_t completed_seq;
    uint32_t requested_pin;
    uint32_t pull_up;
    uint32_t applied_pin;
    uint32_t error;       // 0=OK, 1=invalid command, 2=drive lease expired
    uint32_t heartbeat;
    uint32_t pin_count;
    uint32_t drive_high;
    uint32_t applied_high;
} connectivity_mailbox;

_Static_assert(offsetof(connectivity_mailbox, request_seq) == 8, "mailbox ABI");
_Static_assert(offsetof(connectivity_mailbox, error) == 28, "mailbox ABI");
_Static_assert(offsetof(connectivity_mailbox, pin_count) == 36, "mailbox ABI");
_Static_assert(sizeof(connectivity_mailbox) == 48, "mailbox ABI");
volatile connectivity_mailbox connectivity = {
    .magic = 0x47434e31,
    .version = 2,
    .requested_pin = NO_PIN,
    .pull_up = 0,
    .applied_pin = NO_PIN,
    .pin_count = PIN_COUNT,
};
char board_id[PICO_UNIQUE_BOARD_ID_SIZE_BYTES * 2 + 1];

static void release_test_pins(void) {
    gpio_set_dir_in_masked64(TEST_MASK);
    connectivity.applied_pin = NO_PIN;
}

int main(void) {
    powman_hw->dbgconfig = POWMAN_PASSWORD_BITS | ICE_SWD_INSTANCE_ID;
    pico_get_unique_board_id_string(board_id, sizeof board_id);
    for (uint pin = 0; pin < PIN_COUNT; ++pin) {
        gpio_init(pin);
        gpio_put(pin, 0);
        gpio_set_dir(pin, GPIO_IN);
        gpio_pull_down(pin);
        // GPIO39 must also source the fitted LED loads on both boards.
        gpio_set_drive_strength(pin, pin == 39 ? GPIO_DRIVE_STRENGTH_8MA : GPIO_DRIVE_STRENGTH_2MA);
    }
    stdio_init_all(); // Retain independent USB BOOTSEL recovery; no USB logging.

    absolute_time_t deadline = nil_time;
    while (true) {
        uint32_t request = connectivity.request_seq;
        if (request != connectivity.completed_seq) {
            // Always release the previous pin before applying a new command.
            release_test_pins();
            uint32_t pin = connectivity.requested_pin;
            uint32_t up = connectivity.pull_up;
            uint32_t high = connectivity.drive_high;
            connectivity.error = 0;
            if ((pin != NO_PIN && pin >= PIN_COUNT) || up > 1 || high > 1) {
                connectivity.error = 1;
            } else {
                for (uint i = 0; i < PIN_COUNT; ++i) {
                    gpio_set_pulls(i, up != 0, up == 0);
                }
                if (pin != NO_PIN) {
                    gpio_put(pin, high != 0); // Set latch while output is disabled.
                    gpio_set_dir(pin, GPIO_OUT);
                    connectivity.applied_pin = pin;
                    deadline = make_timeout_time_ms(DRIVE_LEASE_MS);
                }
                connectivity.applied_high = high;
            }
            __dmb();
            connectivity.completed_seq = request;
        }
        if (connectivity.applied_pin != NO_PIN && time_reached(deadline)) {
            release_test_pins();
            connectivity.error = 2;
        }
        ++connectivity.heartbeat;
        sleep_ms(1);
    }
}
