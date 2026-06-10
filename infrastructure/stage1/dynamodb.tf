resource "aws_dynamodb_table" "weather_data" {
  name         = "weather-data-${var.environment}"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "device_id"
  range_key    = "timestamp"

  attribute {
    name = "device_id"
    type = "N"
  }
  attribute {
    name = "timestamp"
    type = "N"
  }

  # TTL: automatically expire records older than 7 days.
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }
}
