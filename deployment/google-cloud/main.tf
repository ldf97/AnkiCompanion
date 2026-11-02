terraform {
  required_version = ">= 1.6.0"
  required_providers {
    google = { source = "hashicorp/google", version = ">= 6.0, < 8.0" }
  }
  # This stores Terraform RESOURCE metadata, not live SQLite study history.
  backend "gcs" {}
}
provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

resource "google_compute_network" "net" {
  name = "ankicompanion-net"
  auto_create_subnetworks = false
}
resource "google_compute_subnetwork" "subnet" {
  name = "ankicompanion-subnet"
  ip_cidr_range = "10.117.0.0/24"
  network = google_compute_network.net.id
  region = var.region
}
resource "google_compute_firewall" "https" {
  name = "ankicompanion-https"
  network = google_compute_network.net.name
  target_tags = ["ankicompanion"]
  source_ranges = ["0.0.0.0/0"]
  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }
  allow {
    protocol = "udp"
    ports    = ["443"]
  }
  # Never expose internal application port 8765.
}
resource "google_compute_firewall" "iap_ssh" {
  name = "ankicompanion-iap-ssh"
  network = google_compute_network.net.name
  target_tags = ["ankicompanion"]
  source_ranges = ["35.235.240.0/20"]
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}
resource "google_compute_address" "ip" {
  name = "ankicompanion-static-ip"
  region = var.region
}
locals {
  domain = var.domain != "" ? var.domain : "${replace(google_compute_address.ip.address, ".", "-")}.sslip.io"
}
resource "google_compute_disk" "data" {
  name = "ankicompanion-data"
  type = "pd-standard"
  zone = var.zone
  size = 15
  lifecycle { prevent_destroy = true }
}
resource "google_compute_disk" "backups" {
  name = "ankicompanion-backups"
  type = "pd-standard"
  zone = var.zone
  size = 5
  lifecycle { prevent_destroy = true }
}
resource "google_compute_resource_policy" "snapshots" {
  name = "ankicompanion-daily"
  region = var.region
  snapshot_schedule_policy {
    schedule {
      daily_schedule {
        days_in_cycle = 1
        start_time    = "04:00"
      }
    }
    retention_policy {
      max_retention_days    = 14
      on_source_disk_delete = "KEEP_AUTO_SNAPSHOTS"
    }
    snapshot_properties { labels = { application = "ankicompanion" } }
  }
}
resource "google_compute_disk_resource_policy_attachment" "policy" {
  name = google_compute_resource_policy.snapshots.name
  disk = google_compute_disk.data.name
  zone = var.zone
}
resource "google_service_account" "host" {
  account_id = "ankicompanion-host"
  display_name = "AnkiCompanion VM (no project API roles)"
}
resource "google_compute_instance" "server" {
  name = "ankicompanion-server"
  machine_type = "e2-micro"
  zone = var.zone
  tags = ["ankicompanion"]
  desired_status = "RUNNING"
  allow_stopping_for_update = true
  boot_disk {
    auto_delete = true
    initialize_params {
      image = "debian-cloud/debian-12"
      type  = "pd-standard"
      size  = 10
    }
  }
  attached_disk {
    source      = google_compute_disk.data.self_link
    device_name = "ankicompanion-data"
    mode        = "READ_WRITE"
  }
  attached_disk {
    source      = google_compute_disk.backups.self_link
    device_name = "ankicompanion-backups"
    mode        = "READ_WRITE"
  }
  network_interface {
    subnetwork = google_compute_subnetwork.subnet.id
    access_config { nat_ip = google_compute_address.ip.address }
  }
  scheduling {
    automatic_restart = true
    on_host_maintenance = "MIGRATE"
    provisioning_model = "STANDARD"
  }
  metadata = { enable-oslogin = "TRUE" }
  metadata_startup_script = templatefile("${path.module}/startup.sh.tftpl", {
    source_ref = var.source_ref
    domain = local.domain
    email = var.email
    require_migration = var.require_migration
  })
  service_account {
    email = google_service_account.host.email
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }
  depends_on = [google_compute_disk_resource_policy_attachment.policy]
}
output "https_url" { value = "https://${local.domain}" }
output "static_ip" { value = google_compute_address.ip.address }
