cmake_minimum_required(VERSION 3.13)

# This is a bench-board bring-up target, separate from the ICE pin assignment.
set(PICO_BOARD waveshare_core2350b CACHE STRING "Bench development board")
list(APPEND PICO_BOARD_HEADER_DIRS ${CMAKE_CURRENT_LIST_DIR}/boards)
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(ice_bringup C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
pico_sdk_init()

add_executable(blink blink.c)
target_link_libraries(blink pico_stdlib)
target_compile_options(blink PRIVATE -Wall -Wextra -Werror)
pico_enable_stdio_uart(blink 0)
pico_enable_stdio_usb(blink 1)
pico_set_program_name(blink "68008ice Core2350B bring-up")
pico_set_program_version(blink "0.1.0")
pico_add_extra_outputs(blink)
