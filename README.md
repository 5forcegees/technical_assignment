# Farm Weather Station

A full-stack IoT weather monitoring system for farm irrigation management. Temperature and humidity readings are collected by field devices, transmitted to AWS, and displayed on a web frontend.

## System Overview

```
[LM92 + HDC3020] ──I2C──▶ [Cortex-M3 MCU] ──MQTT/TLS──▶ [AWS IoT Core]
                                                                  │
                                                         [IoT Topic Rule]
                                                                  │
                                                       [Lambda: ingest.py]
                                                                  │
                                                         [DynamoDB Table]
                                                                  │
                                                        [Lambda: query.py]
                                                                  │
                                                       [API Gateway HTTP]
                                                                  │
                                                     [React Frontend (Vite)]
```

The IoT infrastructure (physical devices, certificates, MQTT broker) is assumed to already exist. This codebase delivers the firmware logic, the cloud data pipeline, and the frontend.

---

## Repository Layout

```
embedded/        C firmware — sensor HAL, binary packet format, on-device storage
lambda/          Python Lambda functions — ingest and query
infrastructure/  Terraform — DynamoDB, IoT rule, API Gateway (three staged deploys)
frontend/        React + TypeScript SPA
docs/            Architecture diagram, design decisions, requirements map
```

---

## embedded/

The firmware runs on a Cortex-M3 MCU paired with an LM92 temperature sensor and an HDC3020 humidity sensor, both over I2C.

**Main loop** (`src/main.c`): every 60 seconds, read both sensors, write the reading to local flash storage, then publish it over MQTT. Data is written to flash first so nothing is lost if the publish fails.

**Binary packet format** (`include/weather_types.h`, `src/weather_packet.c`): each MQTT message is a 13-byte packed struct.

```
Byte  0     : version    (uint8)
Bytes 1–2   : device_id  (uint16 LE)
Bytes 3–6   : timestamp  (uint32 LE)  unix epoch, UTC
Bytes 7–8   : temperature (int16 LE)  whole degrees C
Bytes 9–10  : humidity   (uint16 LE)  whole % RH
Bytes 11–12 : CRC-16/CCITT (uint16 LE) over bytes 0–10
```

Temperature and humidity are stored as whole integers. The LM92 has ±0.33 °C typical accuracy and the HDC3020 has ±1.5% RH — sub-degree encoding would imply more precision than the hardware delivers.

**On-device storage** (`src/circular_buffer.c`): a fixed-capacity circular buffer backed by external flash. At 60-second intervals, 365 days requires 525,600 records. Each `StorageRecord` is 6 bytes (`uint32_t` timestamp + `int8_t` temperature + `uint8_t` humidity), giving a total flash footprint of ~3.15 MB. The buffer overwrites the oldest record when full.

**Hardware abstraction**: `sensor.h` and `mqtt_client.h` define the HAL interfaces. `sensor_mock.c` and `mqtt_client_mock.c` provide host-side implementations used by the simulator and tests — no physical hardware is required to build or test the firmware logic.

**Building**

```bash
cd embedded
cmake -S . -B build && cmake --build build
ctest --test-dir build
```

Or with the Makefile directly:

```bash
make -C build test
```

---

## lambda/

Two Python 3.12 Lambda functions share no code but agree on the DynamoDB schema.

**ingest.py** — triggered by the IoT Core topic rule whenever a device publishes a reading. Decodes the binary payload, independently re-validates the CRC-16/CCITT checksum, and writes the decoded record to DynamoDB. Returns 400 for a missing payload and 422 for a CRC failure or malformed packet.

**query.py** — serves `GET /readings` from API Gateway. Accepts `device_id` (required), `start`, `end` (unix epoch, optional — defaults to the last 24 hours), and `limit` (optional, default 100). Queries DynamoDB and returns a JSON array of readings sorted oldest-to-newest.

**Running tests**

```bash
cd lambda
python3 -m pytest tests/test_ingest.py tests/test_query.py -v
```

The `tests/test_integration_live.py` file contains end-to-end tests against the deployed stack. These are gated behind `pytest -m live` and require the stack to be deployed and `API_ENDPOINT` set in the environment.

---

## infrastructure/

Terraform, split into three independent stages with separate state files to avoid circular dependencies and to allow the API layer to be torn down independently of the data pipeline.

**stage0** — bootstraps the S3 bucket used as the Terraform remote backend for stages 1 and 2. State is kept locally. Only needs to be applied once.

```bash
cd infrastructure/stage0
terraform init && terraform apply
```

**stage1** — deploys the data ingestion pipeline: DynamoDB table, IoT Core thing type and device policy, IoT topic rule routing `weather-stations/+/data` to the ingest Lambda, and the ingest Lambda itself.

```bash
cd infrastructure/stage1
terraform init -backend-config=../stage0/backend.hcl
terraform apply
```

**stage2** — deploys the query API: query Lambda, API Gateway HTTP API with a `GET /readings` route, and the IAM wiring between them.

```bash
cd infrastructure/stage2
terraform init -backend-config=../stage0/backend.hcl
terraform apply
```

After stage2 applies, set `VITE_API_URL` in `frontend/.env` to the value of the `api_endpoint` output.

**DynamoDB schema**

| Attribute | Type | Role |
|---|---|---|
| `device_id` | Number | Hash key |
| `timestamp` | Number | Range key |
| `temperature` | Number | Whole degrees C |
| `humidity` | Number | Whole % RH |
| `ttl` | Number | Epoch; records expire after 7 days |

---

## frontend/

A React + TypeScript single-page app built with Vite.

The main view shows a device ID input, a "latest reading" summary card, and a scrollable table of historical readings. On load and every 60 seconds it polls `GET /readings?device_id=<n>&limit=100` and updates the display. The 60-second poll interval matches the device sample rate.

**Configuration**

Copy `.env.example` to `.env` and set `VITE_API_URL` to the API Gateway base URL from the stage2 Terraform output:

```bash
cp frontend/.env.example frontend/.env
# edit .env: VITE_API_URL=https://<id>.execute-api.<region>.amazonaws.com
```

**Development**

```bash
cd frontend
npm install
npm run dev
```

**Tests**

```bash
npm test
```

Tests use Vitest and Mock Service Worker (MSW). MSW intercepts fetch calls at the network layer so tests are agnostic to the HTTP client and match the same handler definitions used in development mocking.

---

## Testing Summary

| Layer | Tool | Count | Coverage |
|---|---|---|---|
| Embedded | C test runner (custom) | 37 | Packet round-trip, CRC, struct sizes, buffer fill/overwrite/wrap/order |
| Lambda | pytest + moto | 33 | Decode, CRC validation, DynamoDB write, query parameters, ingest→query round-trip |
| Frontend | Vitest + MSW | 12 | API client, component render, error states, polling, device switching |

---

## Further Reading

- `docs/architecture.md` — end-to-end system diagram with component boundaries
- `docs/decisions.md` — rationale behind encoding choices, infrastructure structure, and testing approach
- `docs/requirements_map.md` — each spec requirement traced to the file and line that satisfies it
