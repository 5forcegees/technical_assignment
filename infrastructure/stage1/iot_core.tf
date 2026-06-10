# IoT Core Thing Type — defines the device class
resource "aws_iot_thing_type" "weather_station" {
  name = "WeatherStation"
  properties {
    description = "Farm weather station with temperature and humidity sensors"
  }
}

# IoT Policy — authorises devices to connect and publish
resource "aws_iot_policy" "device_policy" {
  name = "weather-station-policy-${var.environment}"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "iot:Connect"
        Resource = "arn:aws:iot:${data.aws_region.current.name}:*:client/$${iot:ClientId}"
      },
      {
        Effect   = "Allow"
        Action   = "iot:Publish"
        Resource = "arn:aws:iot:${data.aws_region.current.name}:*:topic/weather-stations/*"
      }
    ]
  })
}

# IoT Rule — routes MQTT payloads to the ingest Lambda
# NOTE: This is the integration boundary between the existing physical-device
# infrastructure (Things, certificates) and the cloud service delivered here.
# The rule expects binary payloads on topic: weather-stations/<device_id>/data
resource "aws_iot_topic_rule" "ingest" {
  name        = "weather_ingest_${var.environment}"
  enabled     = true
  description = "Route weather station MQTT payloads to ingest Lambda"

  # SELECT * captures the raw binary payload via the Lambda action
  sql         = "SELECT * FROM '${var.mqtt_topic_filter}'"
  sql_version = "2016-03-23"

  lambda {
    function_arn = aws_lambda_function.ingest.arn
  }

  error_action {
    cloudwatch_logs {
      log_group_name = "/aws/iot/weather-station-errors-${var.environment}"
      role_arn       = aws_iam_role.iot_rule_exec.arn
    }
  }
}

# IAM role for IoT rule error logging
resource "aws_iam_role" "iot_rule_exec" {
  name = "weather-iot-rule-${var.environment}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "iot.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "iot_cloudwatch" {
  name = "weather-iot-cw-${var.environment}"
  role = aws_iam_role.iot_rule_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "*"
    }]
  })
}
