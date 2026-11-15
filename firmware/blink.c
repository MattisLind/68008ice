// SPDX-License-Identifier: Apache-2.0
#include <inttypes.h>
#include <stdio.h>
#include "pico/stdlib.h"

// Visible and editable through SWD/GDB, including while USB is disconnected.
volatile uint32_t blink_count = 0;
volatile uint32_t led_state = 0;
volatile uint32_t blink_period_ms = 500;

// A stable source breakpoint for the hardware debug smoke test.
__attribute__((noinline)) void blink_tick(void) {
    led_state ^= 1u;
    gpio_put(PICO_DEFAULT_LED_PIN, led_state);
    ++blink_count;
    printf("blink=%" PRIu32 " gpio=%u state=%" PRIu32 " period_ms=%" PRIu32 "\n",
           blink_count, PICO_DEFAULT_LED_PIN, led_state, blink_period_ms);
}

int main(void) {
    // Only the user-selected bench LED is driven. No UART, PSRAM, bus or PIO
    // initialization. GPIO39 is RESET_N on the proposed ICE, so this firmware
    // must only be used on the standalone Waveshare development board.
    gpio_init(PICO_DEFAULT_LED_PIN);
    gpio_put(PICO_DEFAULT_LED_PIN, 0);
    gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);
    stdio_init_all();

    while (true) {
        blink_tick();
        sleep_ms(blink_period_ms);
    }
}
