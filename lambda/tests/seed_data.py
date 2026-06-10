#!/usr/bin/env python3
"""
Seed DynamoDB with realistic weather readings for the last 72 hours.

Writes one reading every 15 minutes with a sinusoidal day/night temperature
and humidity cycle so the frontend has data to display.

Usage:
  python tests/seed_data.py
  python tests/seed_data.py --device 1 --hours 72 --step 900
  DYNAMODB_TABLE=weather-data-dev python tests/seed_data.py

Environment variables:
  DYNAMODB_TABLE        default: weather-data-dev
  AWS_DEFAULT_REGION    default: eu-central-1
"""

import argparse
import math
import os
import random
import sys
import time

import boto3


TABLE_NAME = os.environ.get("DYNAMODB_TABLE",     "weather-data-dev")
AWS_REGION  = os.environ.get("AWS_DEFAULT_REGION", "eu-central-1")
TTL_OFFSET  = 7 * 24 * 3600


def temperature_at(utc_hour: float, noise_seed: int) -> int:
    """
    Sinusoidal day/night cycle.
    Peak ~14:00 UTC (26 °C), trough ~02:00 UTC (10 °C), ±1 °C noise.
    """
    rng   = random.Random(noise_seed)
    phase = 2 * math.pi * (utc_hour - 14) / 24
    return round(18 + 8 * math.cos(phase) + rng.gauss(0, 1))


def humidity_at(utc_hour: float, noise_seed: int) -> int:
    """
    Inversely correlated with temperature.
    Peak ~02:00 UTC (85 %), trough ~14:00 UTC (55 %), ±3 % noise.
    """
    rng   = random.Random(noise_seed + 1)
    phase = 2 * math.pi * (utc_hour - 14) / 24
    raw   = round(70 - 15 * math.cos(phase) + rng.gauss(0, 3))
    return max(0, min(100, raw))


def generate_readings(device_id: int, hours: int, step: int) -> list[dict]:
    now      = int(time.time())
    start_ts = now - hours * 3600
    readings = []

    ts = start_ts
    while ts <= now:
        utc_hour = (ts % 86400) / 3600
        temp     = temperature_at(utc_hour, ts)
        hum      = humidity_at(utc_hour, ts)
        readings.append({
            "device_id":   device_id,
            "timestamp":   ts,
            "temperature": temp,
            "humidity":    hum,
            "version":     1,
            "ttl":         ts + TTL_OFFSET,
        })
        ts += step

    return readings


def batch_write(table, readings: list[dict]) -> int:
    written = 0
    for offset in range(0, len(readings), 25):
        chunk = readings[offset:offset + 25]
        with table.batch_writer() as batch:
            for item in chunk:
                batch.put_item(Item=item)
        written += len(chunk)
        print(f"  {written}/{len(readings)} written…", end="\r", flush=True)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--device", type=int, default=1,
                        help="device_id to seed (default: 1)")
    parser.add_argument("--hours", type=int, default=72,
                        help="how many hours of history to generate (default: 72)")
    parser.add_argument("--step", type=int, default=900,
                        help="interval between readings in seconds (default: 900 = 15 min)")
    parser.add_argument("--table", default=TABLE_NAME,
                        help=f"DynamoDB table name (default: {TABLE_NAME})")
    parser.add_argument("--region", default=AWS_REGION,
                        help=f"AWS region (default: {AWS_REGION})")
    args = parser.parse_args()

    print(f"Seeding device {args.device}: "
          f"{args.hours}h of history, {args.step}s intervals")
    print(f"Table: {args.table}  Region: {args.region}")

    readings = generate_readings(args.device, args.hours, args.step)
    print(f"Generated {len(readings)} readings "
          f"({readings[0]['timestamp']} → {readings[-1]['timestamp']})")

    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
    written = batch_write(table, readings)
    print(f"\nDone — {written} readings written for device {args.device}.")
    print(f"Temperature range: "
          f"{min(r['temperature'] for r in readings)}–"
          f"{max(r['temperature'] for r in readings)} °C")
    print(f"Humidity range:    "
          f"{min(r['humidity'] for r in readings)}–"
          f"{max(r['humidity'] for r in readings)} %")
    return 0


if __name__ == "__main__":
    sys.exit(main())
