// SPDX-License-Identifier: Apache-2.0
// Standalone Core2350B fixture only. GPIO0 is an address signal on the ICE.
// Board 1 GPIO0 --- user-fitted 470 ohm resistor --- board 2 GPIO0.
// Shared SWD already provides the common ground. Only board 1 drives GPIO0.
#include <inttypes.h>
#include <stdio.h>
#include "hardware/structs/powman.h"
#include "hardware/sync.h"
#include "pico/stdlib.h"
#include "pico/unique_id.h"

#if ICE_SWD_INSTANCE_ID != 1 && ICE_SWD_INSTANCE_ID != 2
#error GPIO link demo requires SWD instance 1 (source) or 2 (receiver)
#endif

#define LINK_PIN 0
#define LINK_SOURCE (ICE_SWD_INSTANCE_ID == 1)

volatile uint32_t blink_count = 0;
volatile uint32_t blink_period_ms = 500;
volatile uint32_t led_state = 0;
volatile uint32_t link_state = 0;
char board_id[PICO_UNIQUE_BOARD_ID_SIZE_BYTES * 2 + 1];

static void receiver_sample(void) {
    link_state = gpio_get(LINK_PIN);
    led_state = !link_state;
    gpio_put(PICO_DEFAULT_LED_PIN, led_state);
}

static void link_edge(uint gpio, uint32_t events) {
    (void)gpio;
    (void)events;
    // No USB output in the interrupt: host logging must not delay inversion.
    receiver_sample();
    ++blink_count;
}

__attribute__((noinline)) void gpio_link_tick(void) {
    led_state ^= 1u;
    link_state = led_state;
    // GPIO0 and GPIO39 span the two SIO banks; these writes occur together
    // here, with no logging or sleep between them. No cycle-skew claim.
    gpio_put(LINK_PIN, link_state);
    gpio_put(PICO_DEFAULT_LED_PIN, led_state);
    ++blink_count;
}

static void log_status(void) {
    uint32_t irq_state = save_and_disable_interrupts();
    uint32_t count = blink_count;
    uint32_t input = link_state;
    uint32_t led = led_state;
    restore_interrupts(irq_state);
    printf("swd_id=%u board=%s role=%s edges=%" PRIu32 " gpio0=%" PRIu32
           " led=%" PRIu32 "\n", ICE_SWD_INSTANCE_ID, board_id,
           LINK_SOURCE ? "source" : "receiver", count, input, led);
}

int main(void) {
    powman_hw->dbgconfig = POWMAN_PASSWORD_BITS | ICE_SWD_INSTANCE_ID;
    pico_get_unique_board_id_string(board_id, sizeof board_id);

    // Set the output latches before enabling outputs. Every other GPIO stays
    // at its reset setting; no UART, PSRAM, PIO or target bus is initialized.
    gpio_init(LINK_PIN);
    gpio_disable_pulls(LINK_PIN);
    gpio_set_dir(LINK_PIN, GPIO_IN);
    gpio_init(PICO_DEFAULT_LED_PIN);
    gpio_put(PICO_DEFAULT_LED_PIN, 0);
    gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);

    if (LINK_SOURCE) {
        gpio_put(LINK_PIN, 0);
        gpio_set_dir(LINK_PIN, GPIO_OUT);
    } else {
        uint32_t irq_state = save_and_disable_interrupts();
        gpio_set_irq_enabled_with_callback(LINK_PIN,
                GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL, true, link_edge);
        receiver_sample();
        restore_interrupts(irq_state);
    }
    stdio_init_all();

    if (LINK_SOURCE) {
        while (true) {
            gpio_link_tick();
            log_status();
            sleep_ms(blink_period_ms);
        }
    } else {
        uint32_t logged = UINT32_MAX;
        while (true) {
            if (blink_count != logged) {
                logged = blink_count;
                log_status();
            }
            sleep_ms(10);
        }
    }
}
