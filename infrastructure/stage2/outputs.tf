output "api_endpoint" {
  description = "Base URL for the frontend — set VITE_API_URL to this value"
  value       = aws_apigatewayv2_api.weather_api.api_endpoint
}
