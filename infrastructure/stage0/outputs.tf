output "state_bucket_name" {
  description = "Name of the S3 bucket storing Terraform state"
  value       = aws_s3_bucket.tfstate.bucket
}

output "state_bucket_arn" {
  description = "ARN of the S3 bucket storing Terraform state"
  value       = aws_s3_bucket.tfstate.arn
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB table used for state locking"
  value       = aws_dynamodb_table.tfstate_lock.name
}

output "backend_config" {
  description = "Copy this into stage1/backend.dev.hcl, then run: cd ../stage1 && terraform init -backend-config=backend.dev.hcl"
  value       = <<-EOT
    bucket       = "${aws_s3_bucket.tfstate.bucket}"
    key          = "dev/stage1/terraform.tfstate"
    region       = "eu-central-1"
    use_lockfile = true
    encrypt      = true
  EOT
}
