variable "project_id" {
  type = string
  description = "Google Cloud project with billing enabled"
}
variable "region" {
  type = string
  default = "us-east1"
  validation {
    condition = contains(["us-east1", "us-central1", "us-west1"], var.region)
    error_message = "Choose a region eligible for the Compute Engine e2-micro Always Free tier."
  }
}
variable "zone" {
  type = string
  default = "us-east1-b"
  validation {
    condition = startswith(var.zone, "${var.region}-")
    error_message = "Zone must belong to region."
  }
}
variable "source_ref" {
  type = string
  description = "Pinned, tested 40-character commit SHA; never latest/main"
  validation {
    condition = can(regex("^[0-9a-f]{40}$",var.source_ref))
    error_message = "source_ref must be a lowercase 40-character git commit."
  }
}
variable "email" {
  type = string
  description = "TLS certificate contact (not a login or API key)"
}
variable "domain" {
  type = string
  default = ""
  description = "Owned hostname, or blank for third-party sslip.io IP-based DNS"
}
variable "require_migration" {
  type = bool
  default = true
  description = "Do not create blank replacement server before old data and token are migrated"
}
