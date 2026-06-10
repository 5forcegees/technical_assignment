output "dynamodb_table_name" {
  value = aws_dynamodb_table.weather_data.name
}


output "ingest_lambda_arn" {
  value = aws_lambda_function.ingest.arn
}
