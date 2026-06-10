# infrastructure/

Terraform configuration for the complete AWS cloud stack. Split into three independent stages with separate state files.

---

## Stage Overview

```
stage0/   S3 bucket for Terraform remote state (bootstraps stages 1 and 2)
stage1/   IoT Core rule + ingest Lambda + DynamoDB table
stage2/   Query Lambda + API Gateway HTTP API
```

Stages are deployed in order. Stage2 depends on Stage1's DynamoDB table existing, but references it by name via a `data` source rather than remote state — so Stage2 can be torn down and redeployed independently without touching Stage1's state.

---

## Stage0 — Remote State Bootstrap

Creates the S3 bucket used as the Terraform remote backend by stages 1 and 2. Because Stage0 creates the bucket, it cannot use the bucket as its own backend — its state is kept on the local filesystem.

This stage only needs to be applied once. The state file (`stage0/terraform.tfstate`) should be stored securely; it contains the bucket ARN and is needed to destroy or update the bucket.

**Resources:**
- `aws_s3_bucket.terraform_state` — versioned S3 bucket for remote state

---

## Stage1 — Data Ingestion Pipeline

Deploys everything required to receive and store device data.

**Resources:**

| Resource | Name pattern | Purpose |
|---|---|---|
| `aws_dynamodb_table` | `weather-data-${env}` | Stores decoded readings |
| `aws_iot_thing_type` | `WeatherStation` | Classifies IoT devices |
| `aws_iot_policy` | `weather-station-policy-${env}` | Grants devices `iot:Connect` and `iot:Publish` |
| `aws_iot_topic_rule` | `weather_ingest_${env}` | Routes `weather-stations/+/data` to Lambda |
| `aws_lambda_function` | `weather-ingest-${env}` | Decodes packets and writes to DynamoDB |
| `aws_iam_role` | `weather-lambda-exec-${env}` | Lambda execution role |
| `aws_iam_role_policy` | — | Grants Lambda `dynamodb:PutItem` only |
| `aws_lambda_permission` | — | Allows IoT Core to invoke the Lambda |

**DynamoDB table:**
- Hash key: `device_id` (Number)
- Range key: `timestamp` (Number)
- Billing: PAY_PER_REQUEST
- TTL attribute: `ttl` (records expire 7 days after ingestion)
- Point-in-time recovery: enabled

---

## Stage2 — Query API

Deploys the HTTP API used by the frontend.

**Resources:**

| Resource | Name pattern | Purpose |
|---|---|---|
| `aws_lambda_function` | `weather-query-${env}` | Handles `GET /readings` |
| `aws_apigatewayv2_api` | `weather-api-${env}` | HTTP API (v2) |
| `aws_apigatewayv2_route` | `GET /readings` | Routes requests to query Lambda |
| `aws_apigatewayv2_stage` | `$default` | Auto-deployed stage |
| `aws_iam_role_policy` | — | Grants Lambda `dynamodb:Query` only |
| `aws_lambda_permission` | — | Allows API Gateway to invoke Lambda |
| `data.aws_dynamodb_table` | — | Looks up Stage1 table by name |

**CORS:** configured with `allow_origins = ["*"]` for development. Lock this to the specific frontend domain before a production release.

**Output:** `api_endpoint` — the API Gateway base URL. Set this as `VITE_API_URL` in `frontend/.env`.

---

## Directory Layout

```
stage0/
  main.tf          S3 state bucket
  providers.tf     AWS provider
  versions.tf      Terraform and provider version constraints
  outputs.tf       Bucket name and ARN

stage1/
  providers.tf     AWS provider + S3 backend configuration
  versions.tf      Version constraints
  variables.tf     environment, region, mqtt_topic_filter, lambda sizing
  dynamodb.tf      DynamoDB table
  iot_core.tf      IoT thing type, policy, topic rule, IAM for error logging
  lambda.tf        IAM role + policy, ingest Lambda function + permission
  outputs.tf       Lambda ARN, DynamoDB table name

stage2/
  providers.tf     AWS provider + S3 backend configuration
  versions.tf      Version constraints
  variables.tf     environment, region
  data.tf          Looks up Stage1 DynamoDB table by name
  lambda.tf        IAM role + policy, query Lambda function + permission
  api_gateway.tf   HTTP API, route, integration, stage, CORS
  outputs.tf       api_endpoint (base URL for VITE_API_URL)
  backend.dev.hcl  Backend config for the dev environment
```

---

## Developer Guide

### Prerequisites

- Terraform ≥ 1.5
- AWS credentials configured (`aws configure` or environment variables)
- AWS CLI (optional, useful for validation)

### First-time setup (Stage0)

```bash
cd infrastructure/stage0
terraform init
terraform plan
terraform apply
```

Note the output bucket name — you will need it for the `-backend-config` flag in stages 1 and 2.

### Deploy Stage1

```bash
cd infrastructure/stage1
terraform init -backend-config=../stage0/backend.hcl
terraform plan -var="environment=dev"
terraform apply -var="environment=dev"
```

### Deploy Stage2

```bash
cd infrastructure/stage2
terraform init -backend-config=../stage0/backend.hcl
terraform plan -var="environment=dev"
terraform apply -var="environment=dev"
```

Copy the `api_endpoint` output value into `frontend/.env` as `VITE_API_URL`.

### Validate infrastructure without deploying

```bash
# Check syntax and configuration
terraform validate

# Preview changes without applying
terraform plan -var="environment=dev"

# Verify provider versions match the lock file
terraform providers lock
```

### Format check

```bash
terraform fmt -check -recursive
```

To auto-fix formatting:

```bash
terraform fmt -recursive
```

### Tear down

Stage2 can be destroyed without affecting Stage1 (and therefore without losing any data):

```bash
cd infrastructure/stage2
terraform destroy -var="environment=dev"
```

To destroy everything including data:

```bash
cd infrastructure/stage1
terraform destroy -var="environment=dev"
```

Stage0 (the state bucket) should only be destroyed after both Stage1 and Stage2 are torn down and their state files are no longer needed.

### Deploying to a second environment

All resources are namespaced by `var.environment`. To deploy a staging environment alongside dev:

```bash
# Stage1
terraform apply -var="environment=staging"

# Stage2
terraform apply -var="environment=staging"
```

The two environments will use separate DynamoDB tables (`weather-data-dev` and `weather-data-staging`), separate Lambda functions, and separate API endpoints with no cross-contamination.

### Checking deployed resource state

```bash
# List all resources managed by a stage
terraform state list

# Show details of a specific resource
terraform state show aws_lambda_function.ingest

# Verify the Lambda code hash matches the local source
terraform plan -var="environment=dev" | grep source_code_hash
```
