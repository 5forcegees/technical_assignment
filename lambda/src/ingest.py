"""
Ingest Lambda: decode binary WeatherPacket from IoT Core, write to DynamoDB.

Wire format (11 bytes, little-endian):
  [0]     version      uint8
  [1-2]   device_id    uint16 LE
  [3-6]   timestamp    uint32 LE
  [7]     temperature  int8       (whole degrees C)
  [8]     humidity     uint8      (whole % RH)
  [9-10]  crc          uint16 LE  (CRC-16/CCITT over bytes 0-8)
"""

import struct
import os
import json
import base64
import logging

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

PACKET_FORMAT = "<BHIbBH"
PACKET_SIZE   = struct.calcsize(PACKET_FORMAT)  # 11
CRC_POLY      = 0x1021
CRC_INIT      = 0xFFFF
TTL_OFFSET_S  = 7 * 24 * 3600  # 7 days

# Lazy singleton — avoids env var lookup at import time (needed for unit tests)
_dynamodb_table = None


def _get_table():
    global _dynamodb_table
    if _dynamodb_table is None:
        _dynamodb_table = boto3.resource("dynamodb").Table(
            os.environ["DYNAMODB_TABLE"]
        )
    return _dynamodb_table


def crc16_ccitt(data: bytes) -> int:
    crc = CRC_INIT
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ CRC_POLY) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return crc


def decode_packet(raw: bytes) -> dict:
    if len(raw) != PACKET_SIZE:
        raise ValueError(f"Expected {PACKET_SIZE} bytes, got {len(raw)}")

    version, device_id, timestamp, temperature, humidity, crc_received = \
        struct.unpack(PACKET_FORMAT, raw)

    crc_computed = crc16_ccitt(raw[:9])
    if crc_computed != crc_received:
        raise ValueError(
            f"CRC mismatch: computed 0x{crc_computed:04X}, "
            f"received 0x{crc_received:04X}"
        )

    return {
        "version":     version,
        "device_id":   device_id,
        "timestamp":   timestamp,
        "temperature": temperature,
        "humidity":    humidity,
        "ttl":         timestamp + TTL_OFFSET_S,
    }


def handler(event, context):
    logger.info("Event: %s", json.dumps(event))

    raw_payload = event.get("payload") or event.get("awsIotData")
    if raw_payload is None:
        logger.error("No payload in event")
        return {"statusCode": 400, "body": "Missing payload"}

    raw_bytes = base64.b64decode(raw_payload) if isinstance(raw_payload, str) \
        else bytes(raw_payload)

    try:
        record = decode_packet(raw_bytes)
    except ValueError as exc:
        logger.error("Decode error: %s", exc)
        return {"statusCode": 422, "body": str(exc)}

    _get_table().put_item(Item={
        "device_id":   record["device_id"],
        "timestamp":   record["timestamp"],
        "temperature": record["temperature"],
        "humidity":    record["humidity"],
        "version":     record["version"],
        "ttl":         record["ttl"],
    })

    logger.info(
        "Stored device=%d ts=%d temp=%dC hum=%d%%",
        record["device_id"],
        record["timestamp"],
        record["temperature"],
        record["humidity"],
    )
    return {"statusCode": 200}
