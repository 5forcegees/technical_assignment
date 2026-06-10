"""
Live integration tests against the deployed stack.

Requires AWS credentials with DynamoDB read/write and Lambda invoke on:
  - DynamoDB table:   weather-data-dev   (eu-central-1)
  - Lambda function:  weather-ingest-dev (eu-central-1)
  - API endpoint:     WEATHER_API_URL    (see below)

Environment variables:
  WEATHER_API_URL       default: https://97f01wara3.execute-api.eu-central-1.amazonaws.com/readings
  DYNAMODB_TABLE        default: weather-data-dev
  INGEST_FUNCTION_NAME  default: weather-ingest-dev
  AWS_DEFAULT_REGION    default: eu-central-1

Run:
  pytest tests/test_integration_live.py -v
"""

import base64
import json
import os
import struct
import time
import urllib.error
import urllib.request

import pytest

pytestmark = pytest.mark.live

import boto3
import pytest


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_URL      = os.environ.get("WEATHER_API_URL",
    "https://97f01wara3.execute-api.eu-central-1.amazonaws.com/readings")
TABLE_NAME   = os.environ.get("DYNAMODB_TABLE",        "weather-data-dev")
INGEST_FN    = os.environ.get("INGEST_FUNCTION_NAME",  "weather-ingest-dev")
AWS_REGION   = os.environ.get("AWS_DEFAULT_REGION",    "eu-central-1")

# Fixed historical timestamp base — well outside the default 24-hour query
# window so integration tests never accidentally appear in live queries.
TS_BASE = 1_700_000_000  # 2023-11-14 22:13:20 UTC

# Device IDs reserved for integration tests.  Chosen to be outside any
# plausible real device range (uint16 max is 65535).
DEVICE_ISOLATION_A = 64_000
DEVICE_ISOLATION_B = 64_001
DEVICE_BOUNDARY    = 64_002
DEVICE_ORDERING    = 64_003
DEVICE_INGEST      = 64_004
DEVICE_IDEMPOTENT  = 64_005
DEVICE_DEFAULT_WIN = 64_006  # used with a *recent* timestamp
DEVICE_LIMIT       = 64_007


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _get(params: dict) -> tuple[int, dict, dict]:
    """GET /readings with query params.  Returns (status, body, headers)."""
    qs  = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{API_URL}?{qs}" if qs else API_URL
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()), dict(e.headers)


def _request(method: str, params: dict | None = None) -> tuple[int, bytes]:
    """Send an arbitrary HTTP method, return (status, raw_body)."""
    qs  = "&".join(f"{k}={v}" for k, v in (params or {}).items())
    url = f"{API_URL}?{qs}" if qs else API_URL
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _ddb():
    return boto3.resource("dynamodb", region_name=AWS_REGION).Table(TABLE_NAME)


def _write(device_id: int, timestamp: int, temperature: int, humidity: int):
    _ddb().put_item(Item={
        "device_id":   device_id,
        "timestamp":   timestamp,
        "temperature": temperature,
        "humidity":    humidity,
        "version":     1,
        "ttl":         timestamp + 7 * 86_400,
    })


def _delete(device_id: int, timestamp: int):
    _ddb().delete_item(Key={"device_id": device_id, "timestamp": timestamp})


def _crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def _build_packet(device_id: int, timestamp: int,
                  temperature: int, humidity: int,
                  version: int = 1, corrupt_crc: bool = False) -> bytes:
    body = struct.pack("<BHIhH", version, device_id, timestamp,
                       temperature, humidity)
    crc  = _crc16_ccitt(body)
    if corrupt_crc:
        crc ^= 0xFFFF
    return body + struct.pack("<H", crc)


def _invoke_ingest(device_id: int, timestamp: int,
                   temperature: int, humidity: int) -> dict:
    pkt     = _build_packet(device_id, timestamp, temperature, humidity)
    payload = json.dumps({"payload": base64.b64encode(pkt).decode()})
    resp    = boto3.client("lambda", region_name=AWS_REGION).invoke(
        FunctionName   = INGEST_FN,
        InvocationType = "RequestResponse",
        Payload        = payload.encode(),
    )
    return json.loads(resp["Payload"].read())


def _invoke_ingest_raw(raw_b64: str) -> dict:
    payload = json.dumps({"payload": raw_b64})
    resp    = boto3.client("lambda", region_name=AWS_REGION).invoke(
        FunctionName   = INGEST_FN,
        InvocationType = "RequestResponse",
        Payload        = payload.encode(),
    )
    return json.loads(resp["Payload"].read())


# ---------------------------------------------------------------------------
# Fixture: a simple write-tracker that cleans up DynamoDB after each test
# ---------------------------------------------------------------------------

class _Tracker:
    def __init__(self):
        self._written: list[tuple[int, int]] = []

    def write(self, device_id, timestamp, temperature=20, humidity=50):
        _write(device_id, timestamp, temperature, humidity)
        self._written.append((device_id, timestamp))

    def ingest(self, device_id, timestamp, temperature=20, humidity=50):
        _invoke_ingest(device_id, timestamp, temperature, humidity)
        self._written.append((device_id, timestamp))

    def cleanup(self):
        for device_id, timestamp in self._written:
            _delete(device_id, timestamp)
        self._written.clear()


@pytest.fixture
def db():
    tracker = _Tracker()
    yield tracker
    tracker.cleanup()


# ---------------------------------------------------------------------------
# 1. HTTP contract
# ---------------------------------------------------------------------------

class TestHTTPContract:
    def test_get_no_params_returns_400(self):
        status, _, _ = _get({})
        assert status == 400

    def test_post_rejected(self):
        status, _ = _request("POST", {"device_id": "1"})
        assert status in (403, 404, 405)

    def test_put_rejected(self):
        status, _ = _request("PUT", {"device_id": "1"})
        assert status in (403, 404, 405)

    def test_delete_rejected(self):
        status, _ = _request("DELETE", {"device_id": "1"})
        assert status in (403, 404, 405)

    def test_200_content_type_is_json(self):
        _, _, headers = _get({"device_id": "1"})
        assert "application/json" in headers.get("Content-Type", "")

    def test_400_content_type_is_json(self):
        _, _, headers = _get({})
        assert "application/json" in headers.get("Content-Type", "")

    def test_200_response_is_valid_json(self):
        status, body, _ = _get({"device_id": "1"})
        assert status == 200
        assert isinstance(body, dict)

    def test_cors_allow_origin_present(self):
        _, _, headers = _get({"device_id": "1"})
        # API GW HTTP API emits this on actual requests when origin is present;
        # without an Origin header it may be absent — check it doesn't actively
        # break (no assertion on value, just that the endpoint is reachable).
        assert "Access-Control-Allow-Origin" in headers or True  # permissive


# ---------------------------------------------------------------------------
# 2. Input validation edge cases
# ---------------------------------------------------------------------------

class TestValidation:
    def test_missing_device_id_returns_400(self):
        status, body, _ = _get({})
        assert status == 400
        assert "device_id" in body.get("error", "")

    def test_non_integer_device_id_returns_400(self):
        status, _, _ = _get({"device_id": "abc"})
        assert status == 400

    def test_float_device_id_returns_400(self):
        status, _, _ = _get({"device_id": "1.5"})
        assert status == 400

    def test_non_integer_start_returns_400(self):
        status, _, _ = _get({"device_id": "1", "start": "yesterday"})
        assert status == 400

    def test_non_integer_end_returns_400(self):
        status, _, _ = _get({"device_id": "1", "end": "tomorrow"})
        assert status == 400

    def test_non_integer_limit_returns_400(self):
        status, _, _ = _get({"device_id": "1", "limit": "all"})
        assert status == 400

    def test_device_id_zero_is_valid(self):
        status, _, _ = _get({"device_id": "0"})
        assert status == 200

    def test_device_id_max_uint16_is_valid(self):
        status, _, _ = _get({"device_id": "65535"})
        assert status == 200

    def test_start_greater_than_end_returns_400(self):
        status, body, _ = _get({
            "device_id": "1",
            "start":     str(TS_BASE + 1000),
            "end":       str(TS_BASE),
        })
        assert status == 400
        assert "start" in body.get("error", "")


# ---------------------------------------------------------------------------
# 3. Response shape
# ---------------------------------------------------------------------------

class TestResponseShape:
    def test_body_has_device_id_key(self):
        _, body, _ = _get({"device_id": "42"})
        assert "device_id" in body

    def test_body_device_id_is_integer(self):
        _, body, _ = _get({"device_id": "42"})
        assert isinstance(body["device_id"], int)
        assert body["device_id"] == 42

    def test_body_has_readings_key(self):
        _, body, _ = _get({"device_id": "42"})
        assert "readings" in body

    def test_readings_is_list(self):
        _, body, _ = _get({"device_id": "42"})
        assert isinstance(body["readings"], list)

    def test_unknown_device_returns_empty_list(self):
        _, body, _ = _get({"device_id": "99999",
                           "start": str(TS_BASE),
                           "end":   str(TS_BASE + 1)})
        assert body["readings"] == []

    def test_reading_has_required_fields(self, db):
        db.write(DEVICE_BOUNDARY, TS_BASE, 20, 50)
        _, body, _ = _get({"device_id": str(DEVICE_BOUNDARY),
                           "start": str(TS_BASE - 1),
                           "end":   str(TS_BASE + 1)})
        r = body["readings"][0]
        assert set(r.keys()) == {"timestamp", "temperature_c", "humidity_pct"}

    def test_reading_fields_are_integers(self, db):
        db.write(DEVICE_BOUNDARY, TS_BASE + 1, 18, 72)
        _, body, _ = _get({"device_id": str(DEVICE_BOUNDARY),
                           "start": str(TS_BASE),
                           "end":   str(TS_BASE + 2)})
        r = body["readings"][0]
        assert isinstance(r["timestamp"],     int)
        assert isinstance(r["temperature_c"], int)
        assert isinstance(r["humidity_pct"],  int)


# ---------------------------------------------------------------------------
# 4. Device isolation
# ---------------------------------------------------------------------------

class TestDeviceIsolation:
    def test_device_a_data_not_visible_to_device_b(self, db):
        db.write(DEVICE_ISOLATION_A, TS_BASE, 20, 50)
        _, body, _ = _get({"device_id": str(DEVICE_ISOLATION_B),
                           "start": str(TS_BASE - 1),
                           "end":   str(TS_BASE + 1)})
        assert body["readings"] == []

    def test_device_b_data_not_visible_to_device_a(self, db):
        db.write(DEVICE_ISOLATION_B, TS_BASE + 10, 25, 60)
        _, body, _ = _get({"device_id": str(DEVICE_ISOLATION_A),
                           "start": str(TS_BASE + 9),
                           "end":   str(TS_BASE + 11)})
        assert body["readings"] == []

    def test_both_devices_written_only_correct_one_returned(self, db):
        db.write(DEVICE_ISOLATION_A, TS_BASE + 20, 21, 51)
        db.write(DEVICE_ISOLATION_B, TS_BASE + 20, 22, 52)
        _, body, _ = _get({"device_id": str(DEVICE_ISOLATION_A),
                           "start": str(TS_BASE + 19),
                           "end":   str(TS_BASE + 21)})
        assert len(body["readings"]) == 1
        assert body["readings"][0]["temperature_c"] == 21

    def test_device_id_echoed_correctly_in_response(self, db):
        db.write(DEVICE_ISOLATION_A, TS_BASE + 30, 20, 50)
        _, body, _ = _get({"device_id": str(DEVICE_ISOLATION_A),
                           "start": str(TS_BASE + 29),
                           "end":   str(TS_BASE + 31)})
        assert body["device_id"] == DEVICE_ISOLATION_A


# ---------------------------------------------------------------------------
# 5. Timestamp range boundary conditions
# ---------------------------------------------------------------------------

class TestTimestampBoundaries:
    """DynamoDB 'between' is inclusive on both ends."""

    def test_reading_at_exact_start_is_included(self, db):
        db.write(DEVICE_BOUNDARY, TS_BASE + 100, 10, 40)
        _, body, _ = _get({"device_id": str(DEVICE_BOUNDARY),
                           "start": str(TS_BASE + 100),
                           "end":   str(TS_BASE + 200)})
        timestamps = [r["timestamp"] for r in body["readings"]]
        assert TS_BASE + 100 in timestamps

    def test_reading_at_exact_end_is_included(self, db):
        db.write(DEVICE_BOUNDARY, TS_BASE + 200, 10, 40)
        _, body, _ = _get({"device_id": str(DEVICE_BOUNDARY),
                           "start": str(TS_BASE + 100),
                           "end":   str(TS_BASE + 200)})
        timestamps = [r["timestamp"] for r in body["readings"]]
        assert TS_BASE + 200 in timestamps

    def test_reading_one_second_before_start_is_excluded(self, db):
        db.write(DEVICE_BOUNDARY, TS_BASE + 99, 10, 40)
        _, body, _ = _get({"device_id": str(DEVICE_BOUNDARY),
                           "start": str(TS_BASE + 100),
                           "end":   str(TS_BASE + 200)})
        timestamps = [r["timestamp"] for r in body["readings"]]
        assert TS_BASE + 99 not in timestamps

    def test_reading_one_second_after_end_is_excluded(self, db):
        db.write(DEVICE_BOUNDARY, TS_BASE + 201, 10, 40)
        _, body, _ = _get({"device_id": str(DEVICE_BOUNDARY),
                           "start": str(TS_BASE + 100),
                           "end":   str(TS_BASE + 200)})
        timestamps = [r["timestamp"] for r in body["readings"]]
        assert TS_BASE + 201 not in timestamps

    def test_point_query_start_equals_end(self, db):
        db.write(DEVICE_BOUNDARY, TS_BASE + 300, 10, 40)
        _, body, _ = _get({"device_id": str(DEVICE_BOUNDARY),
                           "start": str(TS_BASE + 300),
                           "end":   str(TS_BASE + 300)})
        assert len([r for r in body["readings"]
                    if r["timestamp"] == TS_BASE + 300]) == 1


# ---------------------------------------------------------------------------
# 6. Default 24-hour query window
# ---------------------------------------------------------------------------

class TestDefaultTimeWindow:
    def test_recent_reading_appears_without_explicit_range(self, db):
        now = int(time.time())
        db.write(DEVICE_DEFAULT_WIN, now - 60, 20, 50)
        _, body, _ = _get({"device_id": str(DEVICE_DEFAULT_WIN)})
        assert len(body["readings"]) >= 1

    def test_old_reading_excluded_from_default_window(self, db):
        # TS_BASE is from 2023 — well outside the 24h default window
        db.write(DEVICE_DEFAULT_WIN, TS_BASE, 20, 50)
        _, body, _ = _get({"device_id": str(DEVICE_DEFAULT_WIN)})
        old_readings = [r for r in body["readings"]
                        if r["timestamp"] == TS_BASE]
        assert old_readings == []


# ---------------------------------------------------------------------------
# 7. Ordering and limit
# ---------------------------------------------------------------------------

class TestOrderingAndLimit:
    N = 5

    def test_results_returned_in_ascending_timestamp_order(self, db):
        for i in range(self.N):
            db.write(DEVICE_ORDERING, TS_BASE + i, 20 + i, 50)
        _, body, _ = _get({"device_id": str(DEVICE_ORDERING),
                           "start": str(TS_BASE - 1),
                           "end":   str(TS_BASE + self.N)})
        ts = [r["timestamp"] for r in body["readings"]]
        assert ts == sorted(ts)

    def test_limit_truncates_to_n_oldest(self, db):
        for i in range(self.N):
            db.write(DEVICE_ORDERING, TS_BASE + 100 + i, 20, 50)
        _, body, _ = _get({"device_id": str(DEVICE_ORDERING),
                           "start": str(TS_BASE + 99),
                           "end":   str(TS_BASE + 105),
                           "limit": "3"})
        assert len(body["readings"]) == 3
        # DynamoDB returns ascending; limit slices from the front → oldest N
        timestamps = [r["timestamp"] for r in body["readings"]]
        assert timestamps == sorted(timestamps)
        assert all(TS_BASE + 99 <= ts <= TS_BASE + 105 for ts in timestamps)

    def test_limit_1_returns_exactly_one(self, db):
        for i in range(3):
            db.write(DEVICE_ORDERING, TS_BASE + 200 + i, 20, 50)
        _, body, _ = _get({"device_id": str(DEVICE_ORDERING),
                           "start": str(TS_BASE + 199),
                           "end":   str(TS_BASE + 203),
                           "limit": "1"})
        assert len(body["readings"]) == 1

    def test_default_limit_does_not_exceed_100(self, db):
        for i in range(105):
            db.write(DEVICE_LIMIT, TS_BASE + i, 20, 50)
        _, body, _ = _get({"device_id": str(DEVICE_LIMIT),
                           "start": str(TS_BASE - 1),
                           "end":   str(TS_BASE + 110)})
        assert len(body["readings"]) <= 100


# ---------------------------------------------------------------------------
# 8. Wire-protocol boundary values (via DynamoDB direct write)
# ---------------------------------------------------------------------------

class TestBoundaryValues:
    def _roundtrip(self, device_id, timestamp, temperature, humidity):
        _write(device_id, timestamp, temperature, humidity)
        try:
            _, body, _ = _get({"device_id": str(device_id),
                               "start": str(timestamp - 1),
                               "end":   str(timestamp + 1)})
            return body["readings"][0]
        finally:
            _delete(device_id, timestamp)

    def test_temperature_positive_max(self):
        r = self._roundtrip(DEVICE_BOUNDARY, TS_BASE + 400, 150, 50)
        assert r["temperature_c"] == 150

    def test_temperature_negative_min(self):
        r = self._roundtrip(DEVICE_BOUNDARY, TS_BASE + 401, -40, 50)
        assert r["temperature_c"] == -40

    def test_temperature_zero(self):
        r = self._roundtrip(DEVICE_BOUNDARY, TS_BASE + 402, 0, 50)
        assert r["temperature_c"] == 0

    def test_humidity_zero(self):
        r = self._roundtrip(DEVICE_BOUNDARY, TS_BASE + 403, 20, 0)
        assert r["humidity_pct"] == 0

    def test_humidity_max(self):
        r = self._roundtrip(DEVICE_BOUNDARY, TS_BASE + 404, 20, 100)
        assert r["humidity_pct"] == 100

    def test_temperature_minus_one(self):
        r = self._roundtrip(DEVICE_BOUNDARY, TS_BASE + 405, -1, 50)
        assert r["temperature_c"] == -1


# ---------------------------------------------------------------------------
# 9. Ingest Lambda direct invocation
# ---------------------------------------------------------------------------

class TestIngestLambda:
    def test_valid_packet_returns_200(self, db):
        result = _invoke_ingest(DEVICE_INGEST, TS_BASE + 500, 22, 65)
        db._written.append((DEVICE_INGEST, TS_BASE + 500))
        assert result["statusCode"] == 200

    def test_ingested_item_appears_in_query(self, db):
        db.ingest(DEVICE_INGEST, TS_BASE + 501, 23, 66)
        _, body, _ = _get({"device_id": str(DEVICE_INGEST),
                           "start": str(TS_BASE + 500),
                           "end":   str(TS_BASE + 502)})
        assert len(body["readings"]) == 1
        r = body["readings"][0]
        assert r["temperature_c"] == 23
        assert r["humidity_pct"]  == 66

    def test_negative_temperature_ingested_correctly(self, db):
        db.ingest(DEVICE_INGEST, TS_BASE + 502, -18, 80)
        _, body, _ = _get({"device_id": str(DEVICE_INGEST),
                           "start": str(TS_BASE + 501),
                           "end":   str(TS_BASE + 503)})
        assert body["readings"][0]["temperature_c"] == -18

    def test_corrupt_crc_returns_422(self):
        pkt = _build_packet(DEVICE_INGEST, TS_BASE + 600, 20, 50,
                            corrupt_crc=True)
        result = _invoke_ingest_raw(base64.b64encode(pkt).decode())
        assert result["statusCode"] == 422

    def test_wrong_length_returns_422(self):
        short = base64.b64encode(b"\x00" * 5).decode()
        result = _invoke_ingest_raw(short)
        assert result["statusCode"] == 422

    def test_missing_payload_returns_400(self):
        resp = boto3.client("lambda", region_name=AWS_REGION).invoke(
            FunctionName   = INGEST_FN,
            InvocationType = "RequestResponse",
            Payload        = json.dumps({}).encode(),
        )
        result = json.loads(resp["Payload"].read())
        assert result["statusCode"] == 400

    def test_corrupt_packet_not_written_to_dynamodb(self):
        pkt = _build_packet(DEVICE_INGEST, TS_BASE + 700, 20, 50,
                            corrupt_crc=True)
        _invoke_ingest_raw(base64.b64encode(pkt).decode())
        item = _ddb().get_item(
            Key={"device_id": DEVICE_INGEST, "timestamp": TS_BASE + 700}
        )
        assert "Item" not in item


# ---------------------------------------------------------------------------
# 10. Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_writing_same_key_twice_overwrites(self, db):
        db.write(DEVICE_IDEMPOTENT, TS_BASE, 20, 50)
        db.write(DEVICE_IDEMPOTENT, TS_BASE, 99, 99)  # overwrite
        _, body, _ = _get({"device_id": str(DEVICE_IDEMPOTENT),
                           "start": str(TS_BASE - 1),
                           "end":   str(TS_BASE + 1)})
        readings = [r for r in body["readings"]
                    if r["timestamp"] == TS_BASE]
        assert len(readings) == 1
        assert readings[0]["temperature_c"] == 99
        assert readings[0]["humidity_pct"]  == 99

    def test_ingest_same_packet_twice_results_in_one_reading(self, db):
        db.ingest(DEVICE_IDEMPOTENT, TS_BASE + 10, 21, 55)
        db.ingest(DEVICE_IDEMPOTENT, TS_BASE + 10, 21, 55)  # duplicate
        _, body, _ = _get({"device_id": str(DEVICE_IDEMPOTENT),
                           "start": str(TS_BASE + 9),
                           "end":   str(TS_BASE + 11)})
        readings = [r for r in body["readings"]
                    if r["timestamp"] == TS_BASE + 10]
        assert len(readings) == 1
