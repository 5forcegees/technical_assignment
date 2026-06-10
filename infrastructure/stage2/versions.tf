terraform {
  required_version = ">= 1.15.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }

  # Populated at init time via: terraform init -backend-config=backend.dev.hcl
  # Run stage0 and stage1 first.
  backend "s3" {
    bucket       = "weather-station-392833766849-tfstate"
    key          = "dev/stage2/terraform.tfstate"
    region       = "eu-central-1"
    use_lockfile = true
    encrypt      = true
  }
}
