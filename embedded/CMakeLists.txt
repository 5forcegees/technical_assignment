cmake_minimum_required(VERSION 3.16)
project(weather_station C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

# Strict warnings — mirrors what an embedded cross-compiler enforces
add_compile_options(
    -Wall -Wextra -Wpedantic
    -Wno-unused-parameter
)

include_directories(include)

# ---- common library ----
add_library(weather_core STATIC
    src/crc.c
    src/weather_packet.c
    src/circular_buffer.c
)

# ---- simulator binary (uses mock sensor + mock MQTT) ----
add_executable(weather_station
    src/main.c
    src/sensor_mock.c
    src/mqtt_client_mock.c
)
target_link_libraries(weather_station weather_core m)

# ---- unit tests ----
enable_testing()

add_executable(test_weather_packet
    tests/test_weather_packet.c
)
target_link_libraries(test_weather_packet weather_core)
add_test(NAME test_weather_packet COMMAND test_weather_packet)

add_executable(test_circular_buffer
    tests/test_circular_buffer.c
)
target_link_libraries(test_circular_buffer weather_core)
add_test(NAME test_circular_buffer COMMAND test_circular_buffer)
