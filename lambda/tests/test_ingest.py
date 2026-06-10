"""Unit tests for ingest Lambda — no AWS credentials required."""

import base64
import struct
import sys
import os
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
import ingest
from ingest import decode_packet, crc16_ccitt, PACKET_SIZE

PACKET_FORMAT = "<BHIbBH"


def build_packet(version=2, device_id=42, timestamp=1700000000,
                 temperature=23, humidity=65, corrupt_crc=False):
    data = struct.pack("<BHIbB", version, device_id, timestamp,
                      temperature, humidity)
    crc = crc16_ccitt(data)
    if corrupt_crc:
        crc ^= 0xFFFF
    return data + struct.pack("<H", crc)


class TestCrc:
    def test_known_value(self):
        # CRC of empty sequence with init 0xFFFF is 0xFFFF
        assert crc16_ccitt(b"") == 0xFFFF

    def test_known_nonzero_value(self):
        # Standard CRC-16/CCITT check value for b"123456789" is 0x29B1
        assert crc16_ccitt(b"123456789") == 0x29B1

    def test_self_consistent(self):
        data = b"\x01\x2A\x00\x00\x19\x46\xA8\x65\x2E\x09\x7B"
        crc1 = crc16_ccitt(data)
        crc2 = crc16_ccitt(data)
        assert crc1 == crc2

    def test_detects_bit_flip(self):
        data = b"\x01\x2A\x00\x00\x19\x46\xA8\x65\x2E\x09\x7B"
        crc_orig  = crc16_ccitt(data)
        flipped   = bytes([data[0] ^ 0x01]) + data[1:]
        crc_flipped = crc16_ccitt(flipped)
        assert crc_orig != crc_flipped


class TestDecodePacket:
    def test_round_trip(self):
        pkt = build_packet(device_id=7, timestamp=1700000001,
                           temperature=15, humidity=50)
        rec = decode_packet(pkt)
        assert rec["device_id"]   == 7
        assert rec["timestamp"]   == 1700000001
        assert rec["temperature"] == 15
        assert rec["humidity"]    == 50
        assert rec["version"]     == 2

    def test_negative_temperature(self):
        pkt = build_packet(temperature=-12)  # -12 C
        rec = decode_packet(pkt)
        assert rec["temperature"] == -12

    def test_crc_mismatch_raises(self):
        pkt = build_packet(corrupt_crc=True)
        with pytest.raises(ValueError, match="CRC mismatch"):
            decode_packet(pkt)

    def test_wrong_length_raises(self):
        with pytest.raises(ValueError, match="Expected 11 bytes"):
            decode_packet(b"\x00" * 5)

    def test_ttl_set(self):
        ts = 1700000000
        pkt = build_packet(timestamp=ts)
        rec = decode_packet(pkt)
        assert rec["ttl"] == ts + 7 * 24 * 3600

    def test_packet_size_constant(self):
        assert PACKET_SIZE == 11


# ---------------------------------------------------------------------------
# Handler unit tests — DynamoDB mocked with unittest.mock
# ---------------------------------------------------------------------------

class TestHandler:
    def _b64_packet(self, **kwargs):
        import base64
        return base64.b64encode(build_packet(**kwargs)).decode()

    def test_valid_base64_payload_returns_200(self):
        mock_table = MagicMock()
        with patch.object(ingest, "_get_table", return_value=mock_table):
            resp = ingest.handler({"payload": self._b64_packet()}, None)
        assert resp["statusCode"] == 200
        mock_table.put_item.assert_called_once()

    def test_put_item_receives_correct_fields(self):
        mock_table = MagicMock()
        with patch.object(ingest, "_get_table", return_value=mock_table):
            ingest.handler({"payload": self._b64_packet(
                device_id=7, timestamp=1700000000, temperature=-5, humidity=80
            )}, None)
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["device_id"]   == 7
        assert item["timestamp"]   == 1700000000
        assert item["temperature"] == -5
        assert item["humidity"]    == 80
        assert "ttl" in item

    def test_missing_payload_returns_400(self):
        resp = ingest.handler({}, None)
        assert resp["statusCode"] == 400

    def test_aws_iot_data_key_accepted(self):
        mock_table = MagicMock()
        with patch.object(ingest, "_get_table", return_value=mock_table):
            resp = ingest.handler({"awsIotData": self._b64_packet()}, None)
        assert resp["statusCode"] == 200

    def test_corrupt_crc_returns_422(self):
        resp = ingest.handler(
            {"payload": self._b64_packet(corrupt_crc=True)}, None
        )
        assert resp["statusCode"] == 422
        assert "body" in resp

    def test_wrong_length_returns_422(self):
        import base64
        resp = ingest.handler({"payload": base64.b64encode(b"\x00" * 5).decode()}, None)
        assert resp["statusCode"] == 422


# ---------------------------------------------------------------------------
# Integration test — ingest handler → real moto DynamoDB
# ---------------------------------------------------------------------------

class TestIngestIntegration:
    def setup_method(self):
        self._mock = mock_aws()
        self._mock.start()
        os.environ["DYNAMODB_TABLE"] = "weather-test"
        ingest._dynamodb_table = None
        dynamodb = boto3.resource("dynamodb", region_name="eu-central-1")
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

    def teardown_method(self):
        ingest._dynamodb_table = None
        self._mock.stop()

    def test_item_written_to_dynamodb(self):
        import base64
        pkt = build_packet(device_id=3, timestamp=1700000000,
                           temperature=18, humidity=72)
        ingest.handler({"payload": base64.b64encode(pkt).decode()}, None)

        table = boto3.resource("dynamodb", region_name="eu-central-1").Table("weather-test")
        item = table.get_item(
            Key={"device_id": 3, "timestamp": 1700000000}
        )["Item"]
        assert int(item["temperature"]) == 18
        assert int(item["humidity"])    == 72
