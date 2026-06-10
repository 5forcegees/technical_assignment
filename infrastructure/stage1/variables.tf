variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "mqtt_topic_filter" {
  description = "MQTT topic filter that triggers the ingest Lambda"
  type        = string
  default     = "weather-stations/+/data"
}

variable "dynamodb_billing_mode" {
  description = "DynamoDB billing mode"
  type        = string
  default     = "PAY_PER_REQUEST"
}

variable "lambda_memory_mb" {
  type    = number
  default = 128
}

variable "lambda_timeout_s" {
  type    = number
  default = 10
}
