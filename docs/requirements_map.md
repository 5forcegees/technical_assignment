# Requirements → Implementation Map

Traces each requirement from the technical specification to the specific file(s) and line(s) that satisfy it.

---

## Embedded (C)

| # | Requirement | Implementation |
|---|---|---|
| 1 | Collect temperature from LM92 | `embedded/include/sensor.h:15-19` — `SensorReading.temperature` field; `embedded/src/sensor_mock.c` simulates values; `embedded/src/main.c:45` calls `sensor_read()` |
| 2 | Collect humidity from HDC3020 | Same HAL — `SensorReading.humidity` field; both sensors read atomically in one `sensor_read()` call |
| 3 | Cortex-M3 MCU target | `embedded/include/weather_types.h:13` — sub-degree precision not justified by sensor accuracy; `embedded/src/main.c:19` — flash buffer declared static to avoid stack overflow on Cortex-M3; `sensor.h` / `mqtt_client.h` define a HAL layer intended for cross-compilation |
| 4 | Transmit via MQTT to AWS IoT Core | `embedded/include/mqtt_client.h` — HAL interface; `embedded/src/mqtt_client_mock.c` — host-side implementation; `embedded/src/main.c:39,66` — `mqtt_connect()` and `mqtt_publish()` to topic `weather-stations/42/data` |
| 5 | ≤1 second cloud delivery delay | `embedded/src/main.c:59-68` — each reading is published immediately as a single MQTT message, not buffered or batched; one publish per sample |
| 6 | On-device storage for up to 365 days | `embedded/include/circular_buffer.h:17` — capacity 525,600 records (365 days × 1440 min/day ÷ 1 sample/min); `embedded/src/main.c:27` — `flash_store[CIRCULAR_BUFFER_CAPACITY]` backing array; `embedded/src/main.c:57` — every reading written to buffer before transmit |
| 7 | Optimized binary MQTT payload | `embedded/include/weather_types.h:15-22` — 11-byte `__attribute__((packed))` struct with `int8_t`/`uint8_t` values; `embedded/src/weather_packet.c:17-37` — explicit little-endian serializer; `StorageRecord` at 6 bytes for flash (no CRC, no device_id) |
| 8 | Safe binary format (integrity) | `embedded/include/crc.h` / `embedded/src/crc.c` — CRC-16/CCITT (poly `0x1021`, init `0xFFFF`); `embedded/src/weather_packet.c:35` — CRC appended to every packet; `lambda/src/ingest.py:53-60` — independently re-validated on arrival |

---

## Cloud (IaC)

| # | Requirement | Implementation |
|---|---|---|
| 9 | AWS IoT Core receives device data | `infrastructure/stage1/iot_core.tf:33-52` — `aws_iot_topic_rule.ingest` subscribes to `weather-stations/+/data`, routes to ingest Lambda; `iot_core.tf:10-27` — IoT policy grants `iot:Connect` and `iot:Publish` |
| 10 | Lambda processes incoming IoT data | `lambda/src/ingest.py:77` — `handler(event, context)`; `infrastructure/stage1/lambda.tf:42-57` — deployed as `weather-ingest-${env}`, Python 3.12 |
| 11 | Lambda decodes binary payload | `lambda/src/ingest.py:24` — `PACKET_FORMAT = "<BHIbBH"`; `ingest.py:35-60` — `decode_packet()` unpacks struct, re-validates CRC, returns named fields |
| 12 | Store decoded data in DynamoDB | `lambda/src/ingest.py:63-74` — `_build_record()` maps decoded fields to item; `ingest.py:93-101` — `put_item()` write; `infrastructure/stage1/dynamodb.tf:1-20` — table `weather-data-${env}`, hash `device_id` (N), range `timestamp` (N), TTL enabled |
| 13 | IaC as Terraform | `infrastructure/stage0/` — remote state bootstrap; `infrastructure/stage1/` — IoT Core, ingest Lambda, DynamoDB; `infrastructure/stage2/` — query Lambda, API Gateway |

---

## Frontend (React + TypeScript)

| # | Requirement | Implementation |
|---|---|---|
| 14 | Web-based UI | `frontend/src/App.tsx` — React SPA; `frontend/index.html` — entry point; served via Vite |
| 15 | Display decoded weather data | `frontend/src/App.tsx:69-73` — latest card shows `temperature_c`, `humidity_pct`, formatted timestamp; `App.tsx:88-98` — history table with all readings |
| 16 | Connect to DynamoDB and fetch data | `frontend/src/api.ts:10-19` — `fetchReadings()` hits `GET /readings`; `infrastructure/stage2/api_gateway.tf` — HTTP API Gateway; `lambda/src/query.py` — queries DynamoDB and returns JSON; `frontend/src/App.tsx:30-34` — 60s polling loop |
| 17 | Visual appearance not required | Inline styles only, monospace font, no design framework — `frontend/src/App.tsx:39` |

---

## Deliverables

| # | Requirement | Implementation |
|---|---|---|
| 18 | Codebase in GitHub | Git repository; all four subsystems committed |
| 19 | Architecture diagram | `docs/architecture.md` — ASCII end-to-end system diagram |
| 20 | Diagram shows all components and interconnections | `docs/architecture.md:5-71` — covers device → MQTT → IoT Core → Lambda → DynamoDB → API Gateway → frontend, with data flow annotations |
| 21 | Diagram highlights areas changed in this exercise | `docs/architecture.md:95-99` — explicit `** DELIVERED **` markers per subsystem; existing IoT infrastructure boundary clearly drawn |
| 22 | Build scripts | `embedded/CMakeLists.txt` — CMake build for firmware and tests; `embedded/build/Makefile` — GCC fallback; `infrastructure/stage1/lambda.tf:1-8` and `infrastructure/stage2/lambda.tf:1-8` — `archive_file` data sources package Lambda ZIPs on `terraform apply` |
| 23 | Tests for critical parts | Embedded: `embedded/tests/test_weather_packet.c` (17 tests — packing, round-trip, CRC, negatives, boundaries), `embedded/tests/test_circular_buffer.c` (20 tests — fill, overwrite, wrap, order); Lambda: `lambda/tests/test_ingest.py`, `lambda/tests/test_query.py` (33 tests — unit + moto integration), `lambda/tests/test_integration_live.py` (live stack); Frontend: `frontend/src/api.test.ts` (4 tests), `frontend/src/App.test.tsx` (8 tests) |
