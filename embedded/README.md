# embedded/

Firmware logic for the farm weather station. Reads temperature and humidity sensors, stores readings locally in flash, and transmits each reading to AWS IoT Core over MQTT.

This directory contains pure C logic with no hardware dependencies. Sensor I/O and MQTT are accessed through a HAL (hardware abstraction layer); the production drivers are swapped in at link time. All code here can be built and tested on a host machine without physical hardware.

> **Note:** The tests in this directory run on the host using mock sensor and MQTT implementations. Hardware testing and validation against the real LM92, HDC3020, and target MCU are required before any real-world deployment.

---

## Hardware Context

| Component | Part | Interface |
|---|---|---|
| MCU | Cortex-M3 based | — |
| Temperature sensor | LM92 | I2C |
| Humidity sensor | HDC3020 | I2C |
| Storage | External SPI NOR flash | Memory-mapped |

The firmware assumes the MCU, sensors, and flash are already provisioned. It does not include driver code for specific silicon — those are injected via the HAL interfaces defined in `include/`.

---

## Directory Layout

```
include/
  weather_types.h      Wire packet and flash record structs, macros
  weather_packet.h     Serialise / deserialise / create WeatherPacket
  circular_buffer.h    Circular buffer API and capacity constant
  crc.h                CRC-16/CCITT function declaration
  sensor.h             Sensor HAL interface (SensorReading struct)
  mqtt_client.h        MQTT HAL interface

src/
  weather_packet.c     Explicit little-endian serialiser and CRC embedding
  circular_buffer.c    O(1) circular buffer over a fixed backing array
  crc.c                Bit-by-bit CRC-16/CCITT (poly 0x1021, init 0xFFFF)
  main.c               Main loop: read → store → transmit every 60 seconds
  sensor_mock.c        HAL implementation for host-side builds
  mqtt_client_mock.c   HAL implementation for host-side builds

tests/
  test_weather_packet.c   Packet size, round-trip, CRC, negatives, boundaries
  test_circular_buffer.c  Init, write, fill, overwrite, wrap, order, partial read

CMakeLists.txt           Primary build definition
build/Makefile           GCC fallback (used by CI and pre-built binaries)
```

---

## Data Formats

### WeatherPacket — 11 bytes (MQTT payload)

```
Byte  0    : version     uint8    protocol version (currently 2)
Bytes 1–2  : device_id   uint16   unique station identifier (little-endian)
Bytes 3–6  : timestamp   uint32   unix epoch, UTC (little-endian)
Byte  7    : temperature int8     whole degrees C
Byte  8    : humidity    uint8    whole % RH
Bytes 9–10 : crc         uint16   CRC-16/CCITT over bytes 0–8 (little-endian)
```

The `version` field allows breaking format changes without ambiguity. `int8`/`uint8` are sufficient for the full agronomic range and the LM92/HDC3020 operating envelopes.

### StorageRecord — 6 bytes (flash)

```
Bytes 0–3 : timestamp    uint32   unix epoch, UTC
Byte  4   : temperature  int8     whole degrees C, range −128..+127
Byte  5   : humidity     uint8    whole % RH, range 0..100
```

`device_id` is omitted (implicit — the device knows who it is). CRC is omitted (flash controller ECC handles single-bit integrity). `int8`/`uint8` are sufficient for the LM92 operating range (−55..+150 °C) and HDC3020 full-scale range (0–100% RH). At 60-second intervals, 365 days = 525,600 records × 6 bytes = **~3.15 MB**.

Both formats use the same `int8_t`/`uint8_t` value types. The `TEMP_TO_FIXED()` and `HUM_TO_FIXED()` macros in `weather_types.h` make the cast from the wider `SensorReading` HAL types explicit.

### CRC

CRC-16/CCITT, polynomial `0x1021`, initial value `0xFFFF`, computed over the 11 payload bytes (excluding the CRC field itself). Chosen because it is a standard embedded protocol checksum (XMODEM, Bluetooth), detects all single and double bit errors, and has modest 2-byte overhead. The bit-by-bit implementation saves ~512 bytes of flash versus a table-driven approach; at one CRC per 60 seconds the speed difference is irrelevant.

---

## Main Loop

`src/main.c` runs the following sequence every 60 seconds:

1. Call `sensor_read()` — populates a `SensorReading` with temperature, humidity, and a validity flag
2. On sensor failure, log a warning and skip the cycle
3. Write a `StorageRecord` to the circular buffer — **data is persisted before any network attempt**
4. Serialise a `WeatherPacket` and call `mqtt_publish()` — transmit immediately, satisfying the ≤1 second cloud delivery requirement
5. On MQTT failure, log a warning — the reading is already in flash and will not be lost

The 60-second interval balances the 365-day storage budget against real-time fidelity. At 1-second intervals the same flash budget would last only 6 days.

---

## HAL Interfaces

**`sensor.h`** — `sensor_init()` and `sensor_read()`. On real hardware these perform I2C transactions to the LM92 and HDC3020. `sensor_mock.c` generates deterministic incrementing values for host builds.

**`mqtt_client.h`** — `mqtt_connect()`, `mqtt_publish()`, `mqtt_disconnect()`. On real hardware this drives a TLS socket to the AWS IoT Core broker on port 8883. `mqtt_client_mock.c` prints to stdout and always succeeds.

The mock implementations are linked in the `weather_station` simulator binary and during tests. Production builds link against the real drivers.

---

## Developer Guide

### Prerequisites

- GCC (any version supporting C11) or a Cortex-M3 cross-compiler

### Build

```bash
make -f build/Makefile all
```

Produces:
- `build/weather_station` — host simulator (mock sensor + mock MQTT)
- `build/test_weather_packet` — packet test binary
- `build/test_circular_buffer` — buffer test binary

### Run the simulator

```bash
./build/weather_station
```

Prints one line per reading to stdout and logs MQTT publishes. Press Ctrl-C to stop.

### Run the tests

```bash
make -f build/Makefile test
```

Expected output:

```
=== weather_packet tests ===
  PASS  packet is exactly 11 bytes
  ...
17 passed, 0 failed

=== circular_buffer tests ===
  PASS  init: buffer is empty
  ...
20 passed, 0 failed
```

### Check for warnings

The build is configured with `-Wall -Wextra -Wpedantic`. A clean build produces no warnings. To verify:

```bash
make -f build/Makefile all 2>&1 | grep -i warning
```

### Cross-compile for Cortex-M3

Override `CC` and `CFLAGS` to target Cortex-M3:

```bash
make -f build/Makefile all \
  CC=arm-none-eabi-gcc \
  CFLAGS="-std=c11 -Wall -Wextra -Wpedantic -Iinclude -mcpu=cortex-m3 -mthumb -Os"
```

The core library (`crc.c`, `weather_packet.c`, `circular_buffer.c`) has no OS or libc dependencies beyond `<stdint.h>`, `<stdbool.h>`, and `<string.h>`, and will cross-compile cleanly. `main.c` uses `<time.h>` and `nanosleep` which are POSIX — these would be replaced with RTOS equivalents in a production port.
