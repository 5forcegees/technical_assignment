data "archive_file" "query" {
  type        = "zip"
  output_path = "${path.module}/../../lambda/dist/query.zip"
  source {
    content  = file("${path.module}/../../lambda/src/query.py")
    filename = "query.py"
  }
}

resource "aws_iam_role" "query_exec" {
  name = "weather-query-exec-${var.environment}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "query_basic" {
  role       = aws_iam_role.query_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "query_dynamodb" {
  name = "weather-query-dynamodb-${var.environment}"
  role = aws_iam_role.query_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:Query"]
      Resource = data.aws_dynamodb_table.weather_data.arn
    }]
  })
}

resource "aws_lambda_function" "query" {
  function_name    = "weather-query-${var.environment}"
  filename         = data.archive_file.query.output_path
  source_code_hash = data.archive_file.query.output_base64sha256
  handler          = "query.handler"
  runtime          = "python3.12"
  role             = aws_iam_role.query_exec.arn
  memory_size      = var.lambda_memory_mb
  timeout          = var.lambda_timeout_s

  environment {
    variables = {
      DYNAMODB_TABLE = data.aws_dynamodb_table.weather_data.name
    }
  }
}

resource "aws_lambda_permission" "apigw_invoke_query" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.query.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.weather_api.execution_arn}/*/*"
}
