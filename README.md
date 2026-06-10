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
deploy.py        Terraform lifecycle wrapper (init/plan/apply/destroy for all stages)
```

---

## Components

**`embedded/`** — Cortex-M3 firmware that reads the LM92 (temperature) and HDC3020 (humidity) sensors every 60 seconds, stores each reading to a circular buffer in external flash, and publishes an 11-byte binary MQTT packet to AWS IoT Core. All firmware logic is covered by a HAL abstraction so it builds and tests on a host machine without physical hardware. See [`embedded/README.md`](embedded/README.md).

**`lambda/`** — Two Python 3.12 Lambda functions. `ingest.py` is triggered by the IoT Core topic rule: it decodes the binary packet, validates the CRC-16/CCITT checksum, and writes the record to DynamoDB. `query.py` serves `GET /readings` from API Gateway, querying DynamoDB by device ID with optional time range and limit parameters. See [`lambda/README.md`](lambda/README.md).

**`infrastructure/`** — Terraform split into three independent stages: stage0 bootstraps the S3 remote state bucket, stage1 deploys the ingest pipeline (IoT Core rule, ingest Lambda, DynamoDB), and stage2 deploys the query API (query Lambda, API Gateway). All deployments are managed through `deploy.py`. See [`infrastructure/README.md`](infrastructure/README.md).

**`frontend/`** — React + TypeScript SPA built with Vite. Shows a device ID input, a latest-reading card, and a historical readings table. Polls `GET /readings` every 60 seconds to match the device sample rate. See [`frontend/README.md`](frontend/README.md).

---

## Testing Summary

| Layer | Tool | Count | Coverage |
|---|---|---|---|
| Embedded | C test runner | 37 | Packet round-trip, CRC, struct sizes, buffer fill/overwrite/wrap/order |
| Lambda | pytest + moto | 37 | Decode, CRC validation, DynamoDB write, query parameters, ingest→query round-trip |
| Lambda | mutmut | — | Mutation testing — logic faults in CRC, packet decode, query range, TTL |
| Frontend | Vitest + MSW | 14 | API client, component render, error states, polling, device switching |
| Frontend | Stryker | — | Mutation testing — logic faults in timestamp conversion, latest-reading selection |

---

## Further Reading

- [`docs/architecture.md`](docs/architecture.md) — end-to-end system diagram with component boundaries
- [`docs/decisions.md`](docs/decisions.md) — rationale behind encoding choices, infrastructure structure, and testing approach
- [`docs/requirements_map.md`](docs/requirements_map.md) — each spec requirement traced to the file and line that satisfies it
