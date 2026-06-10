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
- Python 3.9+ with `boto3` (`pip install boto3`)
- AWS credentials configured (`aws configure` or environment variables)

All Terraform lifecycle operations are managed through `deploy.py` at the repo root. The script resolves your AWS account ID, generates the correct backend config for each stage, and handles the stage-0 bootstrap chicken-and-egg.

### First-time deploy (all stages)

```bash
python3 deploy.py --env dev --stage 0   --action apply   # creates S3 state bucket
python3 deploy.py --env dev --stage 1   --action apply   # IoT Core, Lambda, DynamoDB
python3 deploy.py --env dev --stage 2   --action apply   # query Lambda, API Gateway
```

Or in one command:

```bash
python3 deploy.py --env dev --stage all --action apply --auto-approve
```

Copy the `api_endpoint` output value into `frontend/.env` as `VITE_API_URL`.

### Plan before applying

```bash
python3 deploy.py --env dev --stage 1 --action plan
python3 deploy.py --env dev --stage 2 --action plan
```

### Validate Terraform syntax

```bash
python3 deploy.py --env dev --stage 1 --action validate
python3 deploy.py --env dev --stage 2 --action validate
```

### Format check

```bash
terraform fmt -check -recursive infrastructure/
```

To auto-fix:

```bash
terraform fmt -recursive infrastructure/
```

### Tear down

Stage2 can be destroyed without affecting Stage1 (no data loss):

```bash
python3 deploy.py --env dev --stage 2 --action destroy
```

To destroy everything:

```bash
python3 deploy.py --env dev --stage all --action destroy --auto-approve
```

Stage0 (the state bucket) should only be destroyed after both Stage1 and Stage2 are gone and their state files are no longer needed.

### Deploying to a second environment

All resources are namespaced by `--env`. To deploy staging alongside dev:

```bash
python3 deploy.py --env staging --stage all --action apply
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
