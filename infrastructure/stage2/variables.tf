variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "lambda_memory_mb" {
  type    = number
  default = 128
}

variable "lambda_timeout_s" {
  type    = number
  default = 10
}
