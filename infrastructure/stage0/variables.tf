variable "project_name" {
  description = "Project name used as a prefix for resource naming"
  type        = string
  default     = "weather-station"
}

variable "force_destroy_state_bucket" {
  description = "Allow Terraform to destroy the state bucket even if it contains objects. Set true only for full teardown."
  type        = bool
  default     = false
}
