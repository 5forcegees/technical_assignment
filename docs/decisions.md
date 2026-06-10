# Design Decisions and Tradeoffs

## Embedded Firmware

### Sampling interval: 60 seconds
**Decision:** Sample and transmit every 60 seconds.  
**Why:** The spec requires ≤1 second transmission delay and 365-day local storage. At 60 s intervals, 365 days = 525,600 records × 6 bytes = ~3.15 MB — within typical embedded flash budgets. Shorter intervals (e.g. 1 s) would require 315 MB, which is not viable. For irrigation purposes, 60-second resolution is more than sufficient; soil moisture and evapotranspiration change over hours, not seconds.  
**Tradeoff:** Sub-minute anomalies (a sudden frost, sensor spike) are not captured. Acceptable for the stated use case.

### Integer encoding — whole degrees, not fixed-point
**Decision:** Store and transmit temperature as `int8_t` whole degrees C (range −128..+127), humidity as `uint8_t` whole percent RH (range 0..100). Both `WeatherPacket` (wire) and `StorageRecord` (flash) use the same narrow types.  
**Why:** The LM92 temperature sensor has ±0.33 °C typical accuracy; the HDC3020 humidity sensor has ±1.5% RH typical accuracy. Encoding to 0.01-degree resolution would imply precision the hardware cannot deliver. Whole integers are honest about the measurement quality, require no scaling constants, and simplify both firmware and cloud decoding. `int8_t` covers the full agronomically relevant range (−40..+60 °C) and the full LM92 operating range (−55..+150 °C) with room to spare. `uint8_t` covers the full 0–100% RH range.  
**Tradeoff:** Cannot represent fractional degrees if a higher-accuracy sensor is substituted in future. A protocol version bump (the `version` field exists for this) would handle that upgrade path. `int8_t` covers the LM92 operating range up to +127 °C; the upper portion of the rated range (+128..+150 °C) is unrepresentable, but is unreachable in any agricultural deployment.

### Binary MQTT payload, not JSON
**Decision:** 11-byte packed binary struct over MQTT, not a JSON document.  
**Why:** JSON encoding of the same data would be ~80–100 bytes — 7–9× larger. At 60-second intervals this is modest, but binary keeps the payload within a single MQTT message segment, reduces radio-on time on battery-powered devices, and is trivially parseable with `struct.unpack` on the server side. The fixed layout also makes the CRC meaningful — it covers exactly the bytes that matter.  
**Tradeoff:** Not human-readable in transit. Debugging requires a decode tool. Mitigated by the `weather_packet.c` serializer and documented wire format.

### CRC-16/CCITT
**Decision:** CRC-16/CCITT (polynomial 0x1021, init 0xFFFF) over the 9 payload bytes (packet minus CRC field).  
**Why:** Standard choice for embedded serial protocols (XMODEM, Bluetooth). Detects all single and double bit errors, all odd-length error bursts, and all burst errors ≤16 bits. The 16-bit check value adds 2 bytes to an 11-byte packet — modest overhead. Bit-by-bit implementation chosen over table-driven to save ~512 bytes of flash; at one invocation per 60 seconds the speed difference is irrelevant.  
**Tradeoff:** CRC-32 would give stronger protection but adds 2 more bytes. At 11-byte payload over a reliable TLS transport, CRC-16 is sufficient.

### WeatherPacket vs StorageRecord — two separate structs
**Decision:** Network packet (11 bytes) includes `device_id` and CRC. Storage record (6 bytes) omits both.  
**Why:** On-device flash records don't need `device_id` (it's implicit) or CRC (flash controller ECC covers single-bit integrity). Both formats use `int8_t`/`uint8_t`. Stripping `device_id` and CRC reduces the 365-day flash footprint from ~5.77 MB (full packet layout) to ~3.15 MB.  
**Tradeoff:** If flash records are ever read off-device (e.g. via USB for diagnostics), the consumer must know the device ID out-of-band.

### Circular buffer for local storage
**Decision:** Fixed-capacity circular buffer overwriting the oldest record when full.  
**Why:** O(1) read and write with no dynamic memory allocation. Predictable flash wear — writes rotate evenly across all slots. No fragmentation. The oldest data being overwritten is an acceptable policy: if the device has been offline for more than 365 days, that data is unlikely to be useful for irrigation decisions anyway.  
**Tradeoff:** No way to recover data older than the buffer capacity. An append-only log with compaction would preserve more history but requires significantly more complexity.

---

## Cloud Infrastructure

### Terraform over CDK
**Decision:** Terraform (HCL) for all infrastructure.  
**Why:** Reproducible, language-agnostic, and widely understood across teams. Terraform's plan/apply workflow makes infrastructure changes reviewable as diffs before execution. CDK is powerful but adds a compilation step and couples infrastructure to a specific language runtime.  
**Tradeoff:** HCL is less expressive than a general-purpose language for complex conditional logic. Not a concern for this stack's complexity level.

### Stage0 / Stage1 / Stage2 deployment structure
**Decision:** Three independent Terraform stages with separate state files.  
**Why:** Stage0 bootstraps the S3 state bucket — it cannot use that bucket as its own backend (chicken-and-egg). Stage1 (IoT + ingest) and Stage2 (API + frontend serving) are separated because the spec defines them as distinct deliverables, and Stage2 can be torn down without affecting the data pipeline. Separate state files mean a Stage2 apply failure cannot corrupt Stage1 state.  
**Tradeoff:** Three stages to deploy from scratch. Mitigated by `deploy.py --stage all --action apply`, which handles the bootstrap sequence and all three stages in one command.

### Stage0 state is local, then migrated to S3
**Decision:** Stage0's initial apply uses a local backend; `deploy.py` automatically migrates the state into the newly created S3 bucket before returning.  
**Why:** Stage0 creates the S3 bucket. There is no remote backend to store its own state in until after it has run. `deploy.py` handles the chicken-and-egg by applying with a temporary local backend override, then running `terraform init -migrate-state` to move the state into S3. Subsequent stage0 applies use the S3 backend normally.  
**Tradeoff:** The local state file exists briefly during bootstrap and must not be deleted before migration completes. `deploy.py` manages this automatically; manual intervention is only needed if the process is interrupted mid-migration.

### DynamoDB PAY_PER_REQUEST billing
**Decision:** On-demand billing rather than provisioned capacity.  
**Why:** IoT write traffic at 60-second intervals is predictable but sparse. At 10 stations, that's ~432,000 writes/month — far below the threshold where provisioned capacity would be cheaper. PAY_PER_REQUEST requires no capacity planning and handles traffic spikes without throttling.  
**Tradeoff:** At ~1,000+ stations with predictable uniform load, provisioned capacity with auto-scaling would be 20–30% cheaper. Worth revisiting at that scale.

### DynamoDB TTL: 7 days
**Decision:** Records expire automatically after 7 days.  
**Why:** 7 days is sufficient for this exercise — the goal is to demonstrate the pipeline, not long-term data retention. Storage cost scales linearly with retention; at 7-day retention, steady-state storage per station is ~12 MB and negligible in cost. For irrigation decisions, week-old weather data has limited operational value anyway.  
**Tradeoff:** A production system would retain data for months or years to support trend analysis, seasonal comparisons, and audit requirements. The `TTL_OFFSET_S` constant in `ingest.py` is the only place to change the retention period. At longer retention, a tiered approach (hot DynamoDB + cold S3 archive via DynamoDB Streams) would be the production-scale solution.

### Single ingest Lambda, not fan-out
**Decision:** One Lambda handles all incoming MQTT messages.  
**Why:** At 60-second intervals across a farm-scale deployment (10–100 stations), a single Lambda with concurrency handles the load trivially. The IoT Core topic rule invokes it per-message; AWS Lambda scales horizontally automatically.  
**Tradeoff:** At very high station counts (10,000+), DynamoDB write throughput and Lambda concurrency limits would need attention. The architecture is correct for the stated scale; the fix at scale is provisioned concurrency and DynamoDB provisioned capacity, not an architectural change.

### API Gateway HTTP API v2, not REST API
**Decision:** API Gateway v2 (HTTP API) for the query endpoint.  
**Why:** ~70% cheaper than REST API, lower latency, and simpler configuration. The query endpoint is a single GET route — none of the advanced features of REST API (usage plans, request validation, caching) are needed.  
**Tradeoff:** HTTP APIs lack built-in API key management and request validation. For a public production API these would matter; for an internal frontend-only endpoint they don't.

### CORS allow_origins = "*"
**Decision:** Allow all origins on the API Gateway.  
**Why:** Simplifies local development and demo deployment — the frontend URL isn't known at infrastructure-plan time.  
**Tradeoff:** In production, this should be locked to the specific CloudFront or S3 website domain. A variable for `allowed_origins` would be the right fix.

### Stage2 references Stage1 table via data source, not remote state
**Decision:** `data "aws_dynamodb_table"` lookup by name rather than `terraform_remote_state`.  
**Why:** Remote state creates a hard coupling between stages — Stage2's plan fails if Stage1's state file is inaccessible. A data source lookup is a runtime check: if the table exists, the plan succeeds; if not, the error message is clear. The table name follows a deterministic convention (`weather-data-${var.environment}`) that both stages share.  
**Tradeoff:** No compile-time guarantee that Stage1 has been applied before Stage2. The convention must be documented (it is, in `stage2/data.tf`).

---

## Lambda

### Python 3.12, not TypeScript/Node.js
**Decision:** Lambda functions written in Python.  
**Why:** Python's `struct` module maps directly onto C's packed struct layout, making the binary decoding code a near-literal translation of the C wire format. `moto` (the AWS mocking library) is the most mature integration testing tool for AWS services in any language — the round-trip tests in `test_query.py` would be harder to write with equal confidence in Node.js.  
**Tradeoff:** Two languages in the stack (Python + TypeScript). The `Reading` interface field names (`temperature_c`, `humidity_pct`) must be kept in sync manually across `query.py` and `api.ts`. A Node.js Lambda would enable a shared types package in a monorepo, eliminating that risk.

---

## Frontend

### Polling every 60 seconds, not WebSocket
**Decision:** Frontend polls `GET /readings` every 60 seconds.  
**Why:** Matches the device sample rate — there is no new data to show more frequently. Polling is stateless, requires no persistent connection management, and works through all proxies and load balancers without configuration.  
**Tradeoff:** Up to 60 seconds of latency between a new reading arriving in DynamoDB and appearing in the UI. For irrigation monitoring this is acceptable. WebSocket or Server-Sent Events would reduce this to near-zero at the cost of a persistent connection per browser tab and infrastructure to support it (API Gateway WebSocket API or a long-running server).

### Default query window: 24 hours
**Decision:** When no `start`/`end` params are supplied, the query returns the last 24 hours of data.  
**Why:** Gives enough context for daily irrigation decisions without returning the full 7-day retention window on every page load.  
**Tradeoff:** A user who wants to compare yesterday vs today must supply explicit timestamps. Acceptable for the current simple UI; a date-range picker would be the natural next step.

---

## Testing

### moto for Lambda integration tests, not localstack
**Decision:** Use `moto` to mock DynamoDB in Python integration tests.  
**Why:** `moto` runs in-process, requires no Docker, and starts in milliseconds. The round-trip tests (`test_ingest_then_query_returns_same_values`) give high confidence that the ingest and query Lambdas agree on field names, types, and key schema.  
**Tradeoff:** `moto` is not a real DynamoDB — it won't catch IAM permission errors, throughput throttling, or DynamoDB-specific edge cases in condition expressions. `localstack` would catch more, but adds Docker as a test dependency and significant test latency.

### MSW for frontend API mocking, not jest fetch mocks
**Decision:** Use Mock Service Worker (MSW) to intercept fetch calls in frontend tests.  
**Why:** MSW intercepts at the network layer, not at the `fetch` call site. Tests are agnostic to whether `api.ts` uses `fetch`, `axios`, or any other HTTP client. Handler definitions are reusable between test and (future) development mocking.  
**Tradeoff:** MSW adds ~30ms to test startup for server setup. Negligible at this test count.

### No embedded integration tests
**Decision:** Embedded C is tested at unit level only (CRC vectors, packet round-trips, buffer edge cases). No hardware-in-loop tests delivered.  
**Why:** Hardware-in-loop testing requires physical silicon or a cycle-accurate simulator (QEMU for Cortex-M3). Neither is available in the development environment for this exercise.  
**Tradeoff:** The most critical cross-language seam — C serializer agreeing with Python deserializer on the wire format — is tested indirectly by the Python round-trip tests using the same bit patterns. A proper HIL test would also validate timing, flash wear, and sensor driver correctness.
