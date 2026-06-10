data "archive_file" "ingest" {
  type        = "zip"
  output_path = "${path.module}/../../lambda/dist/ingest.zip"
  source {
    content  = file("${path.module}/../../lambda/src/ingest.py")
    filename = "ingest.py"
  }
}

# ---- IAM ----
resource "aws_iam_role" "lambda_exec" {
  name = "weather-lambda-exec-${var.environment}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "dynamodb_access" {
  name = "weather-dynamodb-${var.environment}"
  role = aws_iam_role.lambda_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:PutItem"]
      Resource = aws_dynamodb_table.weather_data.arn
    }]
  })
}

# ---- Ingest Lambda (IoT -> DynamoDB) ----
resource "aws_lambda_function" "ingest" {
  function_name    = "weather-ingest-${var.environment}"
  filename         = data.archive_file.ingest.output_path
  source_code_hash = data.archive_file.ingest.output_base64sha256
  handler          = "ingest.handler"
  runtime          = "python3.12"
  role             = aws_iam_role.lambda_exec.arn
  memory_size      = var.lambda_memory_mb
  timeout          = var.lambda_timeout_s

  environment {
    variables = {
      DYNAMODB_TABLE = aws_dynamodb_table.weather_data.name
    }
  }
}

resource "aws_lambda_permission" "iot_invoke_ingest" {
  statement_id  = "AllowIoTCoreInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "iot.amazonaws.com"
  source_arn    = aws_iot_topic_rule.ingest.arn
}

