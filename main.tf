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

resource "google_service_account" "vm_sa" {
  account_id   = "backend-vm-sa"
  display_name = "Backend VM service account"
}

resource "google_service_account" "cloud_run_sa" {
  account_id   = "cloud-run-sa"
  display_name = "Cloud Run service account"
}

resource "google_compute_network" "vpc_network" {
  name                    = "vpc-network"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "private_subnet" {
  name                     = "private-subnet"
  ip_cidr_range            = "10.10.0.0/24"
  region                   = var.region
  network                  = google_compute_network.vpc_network.id
  private_ip_google_access = true
}

resource "google_compute_firewall" "allow_tcp_8080" {
  name          = "allow-tcp-8080"
  network       = google_compute_network.vpc_network.id
  direction     = "INGRESS"
  source_ranges = [google_compute_subnetwork.private_subnet.ip_cidr_range]
  target_tags   = ["backend-vm"]

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }
}

resource "google_compute_instance" "vm" {
  name         = "backend-vm"
  machine_type = "e2-medium"
  zone         = "${var.region}-b"
  tags         = ["backend-vm"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.private_subnet.id
  }

  service_account {
    email  = google_service_account.vm_sa.email
    scopes = ["cloud-platform"]
  }
}

resource "google_storage_bucket" "bucket" {
  name                        = "${var.project_id}-assets-bucket"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
}

resource "google_cloud_run_v2_service" "frontend" {
  name     = "frontend-service"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.cloud_run_sa.email

    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"
      ports {
        container_port = 8080
      }
    }

    vpc_access {
      network_interfaces {
        network    = google_compute_network.vpc_network.id
        subnetwork = google_compute_subnetwork.private_subnet.id
      }
      egress = "ALL_TRAFFIC"
    }
  }
}

resource "google_storage_bucket_iam_member" "cloud_run_viewer" {
  bucket = google_storage_bucket.bucket.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

resource "google_storage_bucket_iam_member" "vm_viewer" {
  bucket = google_storage_bucket.bucket.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.vm_sa.email}"
}
