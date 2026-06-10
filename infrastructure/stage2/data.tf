# Look up the DynamoDB table created by stage1
data "aws_dynamodb_table" "weather_data" {
  name = "weather-data-${var.environment}"
}
