# Filled in after stage0 apply — same bucket as stage1, different key.
# Replace <ACCOUNT_ID> with the value from: cd ../stage0 && terraform output state_bucket_name
bucket       = "weather-station-<ACCOUNT_ID>-tfstate"
key          = "dev/stage2/terraform.tfstate"
region       = "eu-central-1"
use_lockfile = true
encrypt      = true
