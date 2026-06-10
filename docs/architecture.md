# Weather Station — System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHYSICAL DEVICE (existing IoT infrastructure — not delivered in this task) │
│                                                                             │
│  ┌─────────────┐    I2C    ┌──────────────────────────────────────────────┐│
│  │  LM92       │──────────▶│                                              ││
│  │  Temp sensor│           │  Cortex-M3 MCU                               ││
│  └─────────────┘           │                                              ││
│                            │  ┌──────────────────────────────────────┐   ││
│  ┌─────────────┐    I2C    │  │  ** DELIVERED: embedded/          ** │   ││
│  │  HDC3020    │──────────▶│  │                                      │   ││
│  │  Hum sensor │           │  │  sensor_read() → WeatherPacket       │   ││
│  └─────────────┘           │  │  weather_packet_serialize() → 11 B   │   ││
│                            │  │  cb_write() → CircularBuffer (flash) │   ││
│                            │  │  mqtt_publish() → radio              │   ││
│                            │  │  Sample interval: 60 s               │   ││
│                            │  │  Local storage:  365 days (~3.15 MB) │   ││
│                            │  └──────────────────────────────────────┘   ││
│                            └──────────────────────────────────────────────┘│
│                                            │ MQTT over TLS (port 8883)      │
└────────────────────────────────────────────┼────────────────────────────────┘
                                             │
                ─────────────────────────────▼─────────────────────────────
                                    AWS IoT Core
                             (MQTT broker — existing infra)
                ─────────────────────────────┬─────────────────────────────
                                             │
                          ┌──────────────────▼──────────────────┐
                          │  ** DELIVERED: infrastructure/    ** │
                          │                                      │
                          │  IoT Topic Rule                      │
                          │  Topic: weather-stations/+/data      │
                          │  SQL: SELECT * FROM topic            │
                          └──────────────────┬──────────────────┘
                                             │ invoke
                          ┌──────────────────▼──────────────────┐
                          │  ** DELIVERED: lambda/ingest.py   ** │
                          │                                      │
                          │  1. base64-decode MQTT payload       │
                          │  2. struct.unpack (11 bytes)         │
                          │  3. CRC-16/CCITT validate            │
                          │  4. DynamoDB PutItem                 │
                          └──────────────────┬──────────────────┘
                                             │
                          ┌──────────────────▼──────────────────┐
                          │  ** DELIVERED: DynamoDB table     ** │
                          │                                      │
                          │  PK: device_id (N)                   │
                          │  SK: timestamp  (N)                  │
                          │  TTL: 7 days                         │
                          └──────────────────┬──────────────────┘
                                             │ Query
                          ┌──────────────────▼──────────────────┐
                          │  ** DELIVERED: lambda/query.py    ** │
                          │  ** DELIVERED: API Gateway (HTTP) ** │
                          │                                      │
                          │  GET /readings?device_id=N&limit=N   │
                          └──────────────────┬──────────────────┘
                                             │ HTTPS
                          ┌──────────────────▼──────────────────┐
                          │  ** DELIVERED: frontend/          ** │
                          │                                      │
                          │  React + TypeScript (Vite)           │
                          │  - Device selector                   │
                          │  - Latest reading card               │
                          │  - Historical readings table         │
                          │  - Auto-refresh every 60 s           │
                          └─────────────────────────────────────┘
```

## Binary Packet Format (WeatherPacket — 11 bytes)

```
Byte  0    : version     (uint8)   — protocol version (currently 2)
Bytes 1-2  : device_id   (uint16 LE)
Bytes 3-6  : timestamp   (uint32 LE) — unix epoch UTC
Byte  7    : temperature (int8)    — whole degrees C  (e.g. 23 = 23 °C)
Byte  8    : humidity    (uint8)   — whole % RH       (e.g. 65 = 65 %)
Bytes 9-10 : crc         (uint16 LE) — CRC-16/CCITT over bytes 0–8
```

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Sampling interval | 60 s | Balances 365-day storage (~3.15 MB) vs. real-time fidelity |
| Encoding | Integer fixed-point | No FPU on Cortex-M3; simpler, deterministic |
| Storage | Circular buffer | O(1) read/write; no dynamic allocation; predictable flash wear |
| Transmission | Single record per MQTT message | Satisfies ≤1 s cloud delay requirement |
| Infrastructure | Terraform | Reproducible; preferred over CDK per project requirements |
| Lambda runtime | Python 3.12 | Standard for IoT data pipelines; `struct` module mirrors C layout exactly |

## What "IoT infrastructure" covers (not delivered)

- Physical weather station hardware
- Per-device IoT Core Things, X.509 certificates, and certificate-policy attachments
- Radio/connectivity hardware (cellular modem, WiFi module)
