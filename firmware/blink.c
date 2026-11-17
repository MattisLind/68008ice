// SPDX-License-Identifier: Apache-2.0
#include <inttypes.h>
#include <stdio.h>
#include "hardware/structs/powman.h"
#include "pico/stdlib.h"
#include "pico/unique_id.h"

// Visible and editable through SWD/GDB, including while USB is disconnected.
volatile uint32_t blink_count = 0;
volatile uint32_t led_state = 0;
volatile uint32_t blink_period_ms = 500;
const uint32_t swd_instance_id = ICE_SWD_INSTANCE_ID;
char board_id[PICO_UNIQUE_BOARD_ID_SIZE_BYTES * 2 + 1];

// A stable source breakpoint for the hardware debug smoke test.
__attribute__((noinline)) void blink_tick(void) {
    led_state ^= 1u;
    gpio_put(PICO_DEFAULT_LED_PIN, led_state);
    ++blink_count;
    printf("swd_id=%u board=%s blink=%" PRIu32 " gpio=%u state=%" PRIu32
           " period_ms=%" PRIu32 "\n", ICE_SWD_INSTANCE_ID, board_id,
           blink_count, PICO_DEFAULT_LED_PIN, led_state, blink_period_ms);
}

int main(void) {
    // Each bench board stores its SWD address in its firmware image, not OTP.
    // POWMAN writes require the password. Assign before USB initialization;
    // both chips start at instance zero after a power-on reset. Do not attach
    // a shared debugger until both applications have booted. BOOTSEL recovery
    // remains available over each board's independent USB connection.
    powman_hw->dbgconfig = POWMAN_PASSWORD_BITS | ICE_SWD_INSTANCE_ID;
    pico_get_unique_board_id_string(board_id, sizeof board_id);

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
