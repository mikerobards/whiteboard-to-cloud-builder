resource "google_compute_instance" "backend_vm" {
  name         = "backend-vm"
  machine_type = "e2-medium"
  zone         = "${var.region}-b"

  tags = ["backend-vm"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.private_subnet.id
  }

  service_account {
    email  = google_service_account.backend_vm_sa.email
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }

  depends_on = [google_service_networking_connection.private_vpc_connection]
}

resource "google_cloud_run_v2_service" "frontend" {
  name     = "serverless-fe"
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
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.private_subnet.id
      }
      egress = "ALL_TRAFFIC"
    }
  }
}
