#!/usr/bin/env python3
"""
Remove seeded weather readings from DynamoDB.

Deletes all items for the seeded device within a configurable time window
(default: last 80 hours — slightly wider than the 72-hour seed window so
it catches any re-seeded data regardless of when the script runs).

Usage:
  python tests/clear_seed_data.py
  python tests/clear_seed_data.py --device 1 --hours 80
  DYNAMODB_TABLE=weather-data-dev python tests/clear_seed_data.py

Environment variables:
  DYNAMODB_TABLE        default: weather-data-dev
  AWS_DEFAULT_REGION    default: eu-central-1
"""

import argparse
import os
import sys
import time

import boto3
from boto3.dynamodb.conditions import Key


TABLE_NAME = os.environ.get("DYNAMODB_TABLE",     "weather-data-dev")
AWS_REGION  = os.environ.get("AWS_DEFAULT_REGION", "eu-central-1")


def query_all(table, device_id: int, start_ts: int, end_ts: int) -> list[dict]:
    """Page through all items for the device in the given timestamp range."""
    items      = []
    kwargs     = {
        "KeyConditionExpression": Key("device_id").eq(device_id)
            & Key("timestamp").between(start_ts, end_ts),
        "ProjectionExpression": "device_id, #ts",
        "ExpressionAttributeNames": {"#ts": "timestamp"},
    }
    while True:
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return items


def batch_delete(table, items: list[dict]) -> int:
    deleted = 0
    for offset in range(0, len(items), 25):
        chunk = items[offset:offset + 25]
        with table.batch_writer() as batch:
            for item in chunk:
                batch.delete_item(Key={
                    "device_id": item["device_id"],
                    "timestamp": item["timestamp"],
                })
        deleted += len(chunk)
        print(f"  {deleted}/{len(items)} deleted…", end="\r", flush=True)
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--device", type=int, default=1,
                        help="device_id to clear (default: 1)")
    parser.add_argument("--hours", type=int, default=80,
                        help="how many hours back to scan for items to delete (default: 80)")
    parser.add_argument("--table", default=TABLE_NAME,
                        help=f"DynamoDB table name (default: {TABLE_NAME})")
    parser.add_argument("--region", default=AWS_REGION,
                        help=f"AWS region (default: {AWS_REGION})")
    parser.add_argument("--yes", action="store_true",
                        help="skip confirmation prompt")
    args = parser.parse_args()

    now      = int(time.time())
    start_ts = now - args.hours * 3600

    print(f"Scanning device {args.device} in [{start_ts}, {now}] "
          f"({args.hours}h window)")
    print(f"Table: {args.table}  Region: {args.region}")

    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
    items = query_all(table, args.device, start_ts, now)

    if not items:
        print("No items found — nothing to delete.")
        return 0

    print(f"Found {len(items)} items.")

    if not args.yes:
        answer = input(f"Delete all {len(items)} items for device {args.device}? [y/N] ")
        if answer.strip().lower() != "y":
            print("Aborted.")
            return 1

    deleted = batch_delete(table, items)
    print(f"\nDone — {deleted} items deleted for device {args.device}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
