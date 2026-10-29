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

resource "google_compute_subnetwork" "vpc_subnetwork" {
  name          = "vpc-subnet-private"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.vpc_network.id
  private_ip_google_access = true
}

resource "google_compute_global_address" "private_ip_range" {
  name          = "private-ip-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc_network.id
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc_network.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_range.name]
}

resource "google_service_account" "backend_vm_sa" {
  account_id   = "backend-vm-sa"
  display_name = "Backend VM Service Account"
}

resource "google_service_account" "cloud_run_sa" {
  account_id   = "cloud-run-sa"
  display_name = "Cloud Run Service Account"
}

resource "google_compute_firewall" "allow_tcp_8080" {
  name    = "allow-tcp-8080"
  network = google_compute_network.vpc_network.id
  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }
  source_ranges = [google_compute_subnetwork.vpc_subnetwork.ip_cidr_range]
  target_tags   = ["backend-vm"]
}

resource "google_compute_instance" "compute_engine_vm" {
  name         = "backend-vm"
  machine_type = "e2-medium"
  zone         = "${var.region}-b"
  tags         = ["backend-vm"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.vpc_subnetwork.id
  }

  service_account {
    email  = google_service_account.backend_vm_sa.email
    scopes = ["cloud-platform"]
  }
}

resource "google_sql_database_instance" "cloud_sql" {
  name               = "postgres-instance"
  region             = var.region
  database_version   = "POSTGRES_15"
  deletion_protection = false

  depends_on = [google_service_networking_connection.private_vpc_connection]

  settings {
    tier = "db-f1-micro"
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc_network.id
    }
  }
}

resource "google_storage_bucket" "cloud_storage" {
  name     = "${var.project_id}-assets-bucket"
  location = var.region
  uniform_bucket_level_access = true
  force_destroy = true
}

resource "google_cloud_run_v2_service" "cloud_run_service" {
  name     = "frontend-service"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  deletion_protection = false

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
        subnetwork = google_compute_subnetwork.vpc_subnetwork.id
      }
      egress = "ALL_TRAFFIC"
    }
  }
}

resource "google_storage_bucket_iam_member" "cloud_run_storage_viewer" {
  bucket = google_storage_bucket.cloud_storage.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

resource "google_storage_bucket_iam_member" "vm_storage_viewer" {
  bucket = google_storage_bucket.cloud_storage.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.backend_vm_sa.email}"
}

resource "google_compute_region_network_endpoint_group" "cloud_run_neg" {
  name                  = "cloud-run-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.cloud_run_service.name
  }
}

resource "google_compute_backend_service" "cloud_run_backend" {
  name                  = "cloud-run-backend"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  backend {
    group = google_compute_region_network_endpoint_group.cloud_run_neg.id
  }
}

resource "google_compute_url_map" "url_map" {
  name            = "cloud-lb-url-map"
  default_service = google_compute_backend_service.cloud_run_backend.id
}

resource "google_compute_target_http_proxy" "http_proxy" {
  name    = "cloud-lb-http-proxy"
  url_map = google_compute_url_map.url_map.id
}

resource "google_compute_global_forwarding_rule" "http_forwarding_rule" {
  name                  = "cloud-lb-forwarding-rule"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  port_range            = "80"
  target                = google_compute_target_http_proxy.http_proxy.id
}