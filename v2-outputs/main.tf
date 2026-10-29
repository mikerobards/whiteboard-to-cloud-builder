variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-east1"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_compute_network" "vpc_network" {
  name                    = "vpc-network"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "vpc_network_subnet" {
  name                     = "vpc-network-subnet"
  ip_cidr_range            = "10.0.0.0/24"
  region                   = var.region
  network                  = google_compute_network.vpc_network.id
  private_ip_google_access = true
}

resource "google_service_account" "vm_sa" {
  account_id   = "backend-vm-sa"
  display_name = "VM service account"
}

resource "google_compute_instance" "compute_engine_vm" {
  name         = "compute-engine-vm"
  machine_type = "e2-medium"
  zone         = "${var.region}-b"
  tags         = ["compute-engine-vm"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.vpc_network_subnet.id
  }

  service_account {
    email  = google_service_account.vm_sa.email
    scopes = ["cloud-platform"]
  }
}

resource "google_compute_firewall" "firewall_rule_allow_tcp_8080" {
  name    = "allow-tcp-8080"
  network = google_compute_network.vpc_network.id

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }

  source_ranges = [google_compute_subnetwork.vpc_network_subnet.ip_cidr_range]
  target_tags   = ["compute-engine-vm"]
}

resource "google_service_account" "cloud_run_sa" {
  account_id   = "cloud-run-sa"
  display_name = "Cloud Run service account"
}

resource "google_cloud_run_v2_service" "cloud_run_service" {
  deletion_protection = false
  name     = "cloud-run-service"
  location = var.region

  template {
    service_account = google_service_account.cloud_run_sa.email

    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"
    }

    vpc_access {
      network_interfaces {
        network    = google_compute_network.vpc_network.id
        subnetwork = google_compute_subnetwork.vpc_network_subnet.id
      }
      egress = "ALL_TRAFFIC"
    }
  }
}

resource "google_storage_bucket" "cloud_storage_bucket" {
  name                        = "${var.project_id}-files-static-assets"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
}

resource "google_storage_bucket_iam_member" "cloud_run_viewer" {
  bucket = google_storage_bucket.cloud_storage_bucket.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

resource "google_storage_bucket_iam_member" "vm_viewer" {
  bucket = google_storage_bucket.cloud_storage_bucket.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.vm_sa.email}"
}
