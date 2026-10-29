resource "google_compute_network" "cloud_vpc" {
  name                    = "cloud-environment-vpc"
  auto_create_subnetworks = false
  description             = "Cloud Environment (VPC)"
}

resource "google_compute_subnetwork" "application_subnet" {
  name                     = "application-subnet"
  ip_cidr_range            = "10.0.1.0/24"
  region                   = var.region
  network                  = google_compute_network.cloud_vpc.id
  private_ip_google_access = true
  description              = "Application Subnet"
}

resource "google_compute_firewall" "allow_internal_8080" {
  name    = "allow-app-8080"
  network = google_compute_network.cloud_vpc.name

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }

  source_ranges = [google_compute_subnetwork.application_subnet.ip_cidr_range]
  target_tags   = ["app-server"]
  description   = "Allow TCP 8080 within Application Subnet"
}

resource "google_compute_firewall" "allow_health_checks" {
  name    = "allow-hc-and-proxy"
  network = google_compute_network.cloud_vpc.name

  allow {
    protocol = "tcp"
    ports    = ["8080", "80", "443"]
  }

  source_ranges = ["130.211.0.0/22", "35.191.0.0/16"]
  target_tags   = ["app-server", "load-balanced"]
  description   = "Allow GCP health checks and load balancer"
}

# Private Service Connection for Managed Data Services (Redis and Core App edge)
resource "google_compute_global_address" "private_service_range" {
  name          = "private-service-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.cloud_vpc.id
}

resource "google_service_networking_connection" "private_service_connection" {
  network                 = google_compute_network.cloud_vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_service_range.name]
}
