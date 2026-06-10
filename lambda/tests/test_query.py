"""Unit and integration tests for query Lambda."""

import json
import sys
import os
from unittest.mock import patch, MagicMock

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
import query
import ingest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(params: dict) -> dict:
    return {"queryStringParameters": params}


def _make_table(dynamodb):
    table = dynamodb.create_table(
        TableName="weather-test",
        KeySchema=[
            {"AttributeName": "device_id", "KeyType": "HASH"},
            {"AttributeName": "timestamp",  "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "device_id", "AttributeType": "N"},
            {"AttributeName": "timestamp",  "AttributeType": "N"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table.meta.client.get_waiter("table_exists").wait(TableName="weather-test")
    return table


# ---------------------------------------------------------------------------
# Unit tests — parameter validation
# ---------------------------------------------------------------------------

class TestQueryValidation:
    def test_missing_device_id_returns_400(self):
        resp = query.handler(_make_event({}), None)
        assert resp["statusCode"] == 400
        assert "device_id" in json.loads(resp["body"])["error"]

    def test_non_integer_device_id_returns_400(self):
        resp = query.handler(_make_event({"device_id": "abc"}), None)
        assert resp["statusCode"] == 400

    def test_non_integer_start_returns_400(self):
        resp = query.handler(_make_event({"device_id": "1", "start": "bad"}), None)
        assert resp["statusCode"] == 400

    def test_non_integer_end_returns_400(self):
        resp = query.handler(_make_event({"device_id": "1", "end": "bad"}), None)
        assert resp["statusCode"] == 400

    def test_non_integer_limit_returns_400(self):
        resp = query.handler(_make_event({"device_id": "1", "limit": "bad"}), None)
        assert resp["statusCode"] == 400

    def test_none_query_params_treated_as_missing(self):
        resp = query.handler({"queryStringParameters": None}, None)
        assert resp["statusCode"] == 400

    def test_start_greater_than_end_returns_400(self):
        resp = query.handler(
            _make_event({"device_id": "1", "start": "1000", "end": "500"}), None
        )
        assert resp["statusCode"] == 400
        assert "start" in json.loads(resp["body"])["error"]

    def test_start_equal_to_end_is_valid(self):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        with patch.object(query, "_get_table", return_value=mock_table):
            resp = query.handler(
                _make_event({"device_id": "1", "start": "1000", "end": "1000"}), None
            )
        assert resp["statusCode"] == 200


class TestQueryDefaultTimeRange:
    def test_default_range_is_24_hours(self):
        """When start/end are omitted the handler still calls query with a KeyConditionExpression."""
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}

        with patch.object(query, "_get_table", return_value=mock_table):
            resp = query.handler(_make_event({"device_id": "1"}), None)

        assert resp["statusCode"] == 200
        mock_table.query.assert_called_once()
        call_kwargs = mock_table.query.call_args[1]
        assert "KeyConditionExpression" in call_kwargs


# ---------------------------------------------------------------------------
# Unit tests — response shape
# ---------------------------------------------------------------------------

class TestQueryResponseShape:
    def _make_item(self, ts=1700000000, temp=22, hum=60):
        return {"device_id": 1, "timestamp": ts,
                "temperature": temp, "humidity": hum}

    def test_success_returns_200(self):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": [self._make_item()]}
        with patch.object(query, "_get_table", return_value=mock_table):
            resp = query.handler(_make_event({"device_id": "1"}), None)
        assert resp["statusCode"] == 200

    def test_empty_results_returns_200_with_empty_array(self):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        with patch.object(query, "_get_table", return_value=mock_table):
            resp = query.handler(_make_event({"device_id": "1"}), None)
        body = json.loads(resp["body"])
        assert resp["statusCode"] == 200
        assert body["readings"] == []

    def test_response_contains_device_id(self):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": [self._make_item()]}
        with patch.object(query, "_get_table", return_value=mock_table):
            resp = query.handler(_make_event({"device_id": "7"}), None)
        body = json.loads(resp["body"])
        assert body["device_id"] == 7

    def test_reading_fields_are_integers(self):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": [self._make_item()]}
        with patch.object(query, "_get_table", return_value=mock_table):
            resp = query.handler(_make_event({"device_id": "1"}), None)
        reading = json.loads(resp["body"])["readings"][0]
        assert isinstance(reading["timestamp"],     int)
        assert isinstance(reading["temperature_c"], int)
        assert isinstance(reading["humidity_pct"],  int)

    def test_limit_truncates_results(self):
        items = [self._make_item(ts=1700000000 + i) for i in range(5)]
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": items}
        with patch.object(query, "_get_table", return_value=mock_table):
            resp = query.handler(_make_event({"device_id": "1", "limit": "3"}), None)
        assert len(json.loads(resp["body"])["readings"]) == 3

    def test_content_type_header(self):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        with patch.object(query, "_get_table", return_value=mock_table):
            resp = query.handler(_make_event({"device_id": "1"}), None)
        assert resp["headers"]["Content-Type"] == "application/json"


# ---------------------------------------------------------------------------
# Integration tests — ingest → DynamoDB → query round-trip (moto)
# ---------------------------------------------------------------------------

import struct

PACKET_FORMAT = "<BHIbBH"


def _build_packet(device_id, timestamp, temperature, humidity):
    data = struct.pack("<BHIbB", 2, device_id, timestamp, temperature, humidity)
    crc = ingest.crc16_ccitt(data)
    return data + struct.pack("<H", crc)


class TestRoundTrip:
    def setup_method(self):
        self._mock = mock_aws()
        self._mock.start()
        os.environ["DYNAMODB_TABLE"] = "weather-test"
        ingest._dynamodb_table = None
        query._dynamodb_table  = None
        dynamodb = boto3.resource("dynamodb", region_name="eu-central-1")
        _make_table(dynamodb)

    def teardown_method(self):
        ingest._dynamodb_table = None
        query._dynamodb_table  = None
        self._mock.stop()

    def test_ingest_then_query_returns_same_values(self):
        import base64
        pkt = _build_packet(device_id=42, timestamp=1700000000,
                            temperature=23, humidity=65)
        ingest.handler({"payload": base64.b64encode(pkt).decode()}, None)

        resp = query.handler(
            _make_event({"device_id": "42",
                         "start": "1699999900",
                         "end":   "1700000100"}),
            None,
        )
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert len(body["readings"]) == 1
        r = body["readings"][0]
        assert r["timestamp"]     == 1700000000
        assert r["temperature_c"] == 23
        assert r["humidity_pct"]  == 65

    def test_negative_temperature_survives_round_trip(self):
        import base64
        pkt = _build_packet(device_id=1, timestamp=1700000000,
                            temperature=-15, humidity=80)
        ingest.handler({"payload": base64.b64encode(pkt).decode()}, None)

        resp = query.handler(
            _make_event({"device_id": "1",
                         "start": "1699999900",
                         "end":   "1700000100"}),
            None,
        )
        r = json.loads(resp["body"])["readings"][0]
        assert r["temperature_c"] == -15

    def test_query_outside_time_range_returns_empty(self):
        import base64
        pkt = _build_packet(device_id=1, timestamp=1700000000,
                            temperature=20, humidity=50)
        ingest.handler({"payload": base64.b64encode(pkt).decode()}, None)

        resp = query.handler(
            _make_event({"device_id": "1",
                         "start": "1700001000",
                         "end":   "1700002000"}),
            None,
        )
        assert json.loads(resp["body"])["readings"] == []
