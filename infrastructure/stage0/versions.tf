terraform {
  required_version = ">= 1.15.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Stage0 state is intentionally local — this stage creates the S3 bucket,
  # so it cannot use that bucket as its own backend.
  # After stage0 apply, 
  #   copy the resulting tfstate file into the bucket
}
