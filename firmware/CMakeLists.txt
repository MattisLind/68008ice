cmake_minimum_required(VERSION 3.13)

# This is a bench-board bring-up target, separate from the ICE pin assignment.
set(PICO_BOARD waveshare_core2350b CACHE STRING "Bench development board")
list(APPEND PICO_BOARD_HEADER_DIRS ${CMAKE_CURRENT_LIST_DIR}/boards)
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(ice_bringup C CXX ASM)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
pico_sdk_init()

set(ICE_SWD_INSTANCE_ID 0 CACHE STRING "SWD multidrop instance ID (0..15)")
if(NOT ICE_SWD_INSTANCE_ID MATCHES "^([0-9]|1[0-5])$")
    message(FATAL_ERROR "ICE_SWD_INSTANCE_ID must be an integer from 0 to 15")
endif()

add_executable(blink blink.c)
target_link_libraries(blink pico_stdlib pico_unique_id)
target_compile_definitions(blink PRIVATE ICE_SWD_INSTANCE_ID=${ICE_SWD_INSTANCE_ID})
target_compile_options(blink PRIVATE -Wall -Wextra -Werror)
pico_enable_stdio_uart(blink 0)
pico_enable_stdio_usb(blink 1)
pico_set_program_name(blink "68008ice Core2350B bring-up")
pico_set_program_version(blink "0.2.0")
pico_add_extra_outputs(blink)

if(ICE_SWD_INSTANCE_ID STREQUAL "1" OR ICE_SWD_INSTANCE_ID STREQUAL "2")
    add_executable(gpio_link gpio_link.c)
    target_link_libraries(gpio_link pico_stdlib pico_unique_id)
    target_compile_definitions(gpio_link PRIVATE ICE_SWD_INSTANCE_ID=${ICE_SWD_INSTANCE_ID})
    target_compile_options(gpio_link PRIVATE -Wall -Wextra -Werror)
    pico_enable_stdio_uart(gpio_link 0)
    pico_enable_stdio_usb(gpio_link 1)
    pico_set_program_name(gpio_link "68008ice Core2350B GPIO link")
    pico_set_program_version(gpio_link "0.1.0")
    pico_add_extra_outputs(gpio_link)

    add_executable(gpio_connectivity gpio_connectivity.c)
    target_link_libraries(gpio_connectivity pico_stdlib pico_unique_id)
    target_compile_definitions(gpio_connectivity PRIVATE ICE_SWD_INSTANCE_ID=${ICE_SWD_INSTANCE_ID})
    target_compile_options(gpio_connectivity PRIVATE -Wall -Wextra -Werror)
    pico_enable_stdio_uart(gpio_connectivity 0)
    pico_enable_stdio_usb(gpio_connectivity 1)
    pico_set_program_name(gpio_connectivity "68008ice Core2350B GPIO connectivity")
    pico_set_program_version(gpio_connectivity "0.2.0")
    pico_add_extra_outputs(gpio_connectivity)

    add_executable(pio_trace pio_trace.c)
    target_link_libraries(pio_trace pico_stdlib pico_unique_id hardware_pio hardware_dma)
    target_compile_definitions(pio_trace PRIVATE ICE_SWD_INSTANCE_ID=${ICE_SWD_INSTANCE_ID}
        PARAM_ASSERTIONS_ENABLED_HARDWARE_PIO=1)
    target_compile_options(pio_trace PRIVATE -Wall -Wextra -Werror)
    pico_enable_stdio_uart(pio_trace 0)
    if(ICE_SWD_INSTANCE_ID STREQUAL "2")
        target_sources(pio_trace PRIVATE trace_store.c trace_disk.c trace_usb.c)
        target_include_directories(pio_trace PRIVATE ${CMAKE_CURRENT_LIST_DIR}/trace_usb)
        target_link_libraries(pio_trace hardware_flash tinyusb_device)
        pico_enable_stdio_usb(pio_trace 0)
    else()
        pico_enable_stdio_usb(pio_trace 1)
    endif()
    pico_set_program_name(pio_trace "68008ice PIO trace bench")
    pico_set_program_version(pio_trace "0.1.0")
    pico_add_extra_outputs(pio_trace)

    # Freestanding, fixed-address application images. Only the small versioned
    # HAL table binds a module to the resident dispatcher; no SDK relinking.
    foreach(APP IN ITEMS generator analyzer bus_generator bus_memory state_analyzer cpu_emulator)
        if(APP STREQUAL "generator")
            set(APP_ID 1)
        elseif(APP STREQUAL "analyzer")
            set(APP_ID 2)
        elseif(APP STREQUAL "bus_generator")
            set(APP_ID 3)
        elseif(APP STREQUAL "bus_memory")
            set(APP_ID 4)
        elseif(APP STREQUAL "state_analyzer")
            set(APP_ID 5)
        else()
            set(APP_ID 6)
        endif()
        set(APP_PREFIX ${CMAKE_CURRENT_BINARY_DIR}/app_${APP})
        add_custom_command(OUTPUT ${APP_PREFIX}.h ${APP_PREFIX}.app
            COMMAND ${CMAKE_C_COMPILER} -mcpu=cortex-m33 -mthumb -Os -ffreestanding
                -fno-builtin -fno-unwind-tables -fno-asynchronous-unwind-tables -nostdlib
                -Wall -Wextra -Werror -I${CMAKE_CURRENT_LIST_DIR}/dispatcher
                -Wl,-T,${CMAKE_CURRENT_LIST_DIR}/apps/app.ld
                ${CMAKE_CURRENT_LIST_DIR}/apps/${APP}.c -o ${APP_PREFIX}.elf
            COMMAND ${CMAKE_OBJCOPY} -O binary ${APP_PREFIX}.elf ${APP_PREFIX}.bin
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_LIST_DIR}/../tools/pack_app.py
                ${APP_PREFIX}.bin ${APP_PREFIX} ${APP_ID}
            DEPENDS apps/${APP}.c apps/app.ld dispatcher/app_abi.h ../tools/pack_app.py
            VERBATIM)
    endforeach()
    add_executable(dispatcher dispatcher/main.c dispatcher/protocol.c
        dispatcher/engine.c dispatcher/loader.c dispatcher/capture.c
        dispatcher/capture_window.c dispatcher/capture_store.c dispatcher/capture_fast.c
        dispatcher/bus_cycle.c dispatcher/cpu68008.c dispatcher/cpu_fixture.c dispatcher/memory_image.c trace_store.c trace_usb.c
        ${CMAKE_CURRENT_BINARY_DIR}/app_generator.h ${CMAKE_CURRENT_BINARY_DIR}/app_analyzer.h
        ${CMAKE_CURRENT_BINARY_DIR}/app_bus_generator.h ${CMAKE_CURRENT_BINARY_DIR}/app_bus_memory.h
        ${CMAKE_CURRENT_BINARY_DIR}/app_state_analyzer.h ${CMAKE_CURRENT_BINARY_DIR}/app_cpu_emulator.h)
    target_include_directories(dispatcher PRIVATE ${CMAKE_CURRENT_LIST_DIR}
        ${CMAKE_CURRENT_LIST_DIR}/dispatcher ${CMAKE_CURRENT_LIST_DIR}/trace_usb
        ${CMAKE_CURRENT_BINARY_DIR})
    target_compile_definitions(dispatcher PRIVATE ICE_DISPATCHER=1
        ICE_SWD_INSTANCE_ID=${ICE_SWD_INSTANCE_ID} PARAM_ASSERTIONS_ENABLED_HARDWARE_PIO=1
        PICO_RUNTIME_SKIP_INIT_PSRAM=1 PICO_AUTO_DETECT_PSRAM=0
        PICO_AUTO_DETECT_PSRAM_CS=0 PICO_AUTO_DETECT_PSRAM_SIZE=0)
    target_compile_options(dispatcher PRIVATE -Wall -Wextra -Werror)
    # Per-record trigger/ring processing has a measured throughput budget;
    # retain optimization even in the debugger-friendly overall Debug build.
    set_source_files_properties(dispatcher/capture.c dispatcher/capture_window.c dispatcher/capture_fast.c
        PROPERTIES COMPILE_OPTIONS -O2)
    target_link_libraries(dispatcher pico_stdlib pico_unique_id pico_multicore
        hardware_pio hardware_dma hardware_flash hardware_psram hardware_xip_cache tinyusb_device)
    pico_enable_stdio_uart(dispatcher 0)
    pico_enable_stdio_usb(dispatcher 0)
    # Dispatcher, module and worker stack fit in the first 256 KiB (the
    # interleaved banks 0..3). Reserve the module and stack addresses explicitly.
    # Banks 4..7 hold an aligned 32 KiB acquisition DMA ring. The larger
    # logical capture ring is in PSRAM (hardware DMA wraps at most 32 KiB).
    # Source pattern at 0x20050000 stays away from USB/core SRAM traffic.
    pico_set_linker_script_var(dispatcher RAM_LENGTH 192k)
    pico_set_linker_script_var(dispatcher SCRATCH_X_ORIGIN 0x2003f000)
    pico_set_program_name(dispatcher "68008ice core0 dispatcher")
    pico_set_program_version(dispatcher "0.6.0")
    pico_add_extra_outputs(dispatcher)
endif()
