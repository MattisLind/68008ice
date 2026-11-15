#ifndef ICE_WAVESHARE_CORE2350B_H
#define ICE_WAVESHARE_CORE2350B_H

// Header is consumed by the SDK's CMake parser and assembler too.
pico_board_cmake_set(PICO_PLATFORM, rp2350)
#define PICO_RP2350A 0
#define PICO_XOSC_STARTUP_DELAY_MULTIPLIER 64
#define PICO_FLASH_SIZE_BYTES (16 * 1024 * 1024)
pico_board_cmake_set_default(PICO_FLASH_SIZE_BYTES, (16 * 1024 * 1024))
#define PICO_BOOT_STAGE2_CHOOSE_W25Q080 1
#define PICO_FLASH_SPI_CLKDIV 4
#define PICO_DEFAULT_LED_PIN 39
#define PICO_DEFAULT_LED_PIN_INVERTED 0

// PSRAM is fitted on this bench board but is deliberately unused by blink.
// Never scan CS candidates: GPIO0/8/19 are target address pins on the ICE.
// Waveshare's supplied schematic connects CS to GPIO47. Memory capacity and
// PSRAM power-up/QMI initialization remain a separate bring-up milestone.

#endif
