"""
Query Lambda: fetch weather readings from DynamoDB for a given device and time range.

Query parameters:
  device_id   required  station identifier (integer)
  start       optional  unix epoch, inclusive (default: 24 hours ago)
  end         optional  unix epoch, inclusive (default: now)
  limit       optional  max readings to return (default: 100)
"""

import os
import json
import time
import logging

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_dynamodb_table = None


def _get_table():
    global _dynamodb_table
    if _dynamodb_table is None:
        _dynamodb_table = boto3.resource("dynamodb").Table(
            os.environ["DYNAMODB_TABLE"]
        )
    return _dynamodb_table


def handler(event, context):
    params = event.get("queryStringParameters") or {}

    if "device_id" not in params:
        return _response(400, {"error": "device_id is required"})

    try:
        device_id = int(params["device_id"])
        end   = int(params["end"])   if "end"   in params else int(time.time())
        start = int(params["start"]) if "start" in params else end - 86400
        limit = int(params["limit"]) if "limit" in params else 100
    except ValueError:
        return _response(400, {"error": "device_id, start, end, and limit must be integers"})

    if start > end:
        return _response(400, {"error": "start must be <= end"})

    result = _get_table().query(
        KeyConditionExpression=Key("device_id").eq(device_id)
            & Key("timestamp").between(start, end)
    )

    readings = [
        {
            "device_id":     device_id,
            "timestamp":     int(item["timestamp"]),
            "temperature_c": int(item["temperature"]),
            "humidity_pct":  int(item["humidity"]),
        }
        for item in result.get("Items", [])
    ][-limit:]

    return _response(200, {"device_id": device_id, "readings": readings})


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
