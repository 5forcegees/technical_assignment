provider "aws" {
  default_tags {
    tags = {
      Project     = "weather-station"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

data "aws_region" "current" {}
