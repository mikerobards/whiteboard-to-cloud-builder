resource "google_cloud_run_v2_service" "api_gateway" {
  name     = "api-gateway-proxy"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.api_gateway_sa.email
    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"
      ports {
        container_port = 8080
      }
    }
    vpc_access {
      network_interfaces {
        network    = google_compute_network.cloud_vpc.name
        subnetwork = google_compute_subnetwork.application_subnet.name
      }
      egress = "ALL_TRAFFIC"
    }
  }

  deletion_protection = false
  depends_on          = [google_service_networking_connection.private_service_connection]
}

resource "google_cloud_run_v2_service" "core_app" {
  name     = "core-application-service"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.core_app_sa.email
    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"
      ports {
        container_port = 8080
      }
      env {
        name  = "REDIS_HOST"
        value = google_redis_instance.distributed_cache.host
      }
      env {
        name  = "EVENT_QUEUE_TOPIC"
        value = google_pubsub_topic.event_queue.name
      }
      env {
        name  = "STATUS_EVENTS_TOPIC"
        value = google_pubsub_topic.status_events.name
      }
    }
    vpc_access {
      network_interfaces {
        network    = google_compute_network.cloud_vpc.name
        subnetwork = google_compute_subnetwork.application_subnet.name
      }
      egress = "ALL_TRAFFIC"
    }
  }

  deletion_protection = false
}

resource "google_cloud_run_v2_job" "batch_processor" {
  name     = "batch-processor"
  location = var.region

  template {
    template {
      service_account = google_service_account.batch_processor_sa.email
      containers {
        image = "us-docker.pkg.dev/cloudrun/container/hello"
        env {
          name  = "EVENT_QUEUE_TOPIC"
          value = google_pubsub_topic.event_queue.name
        }
        env {
          name  = "STATUS_EVENTS_TOPIC"
          value = google_pubsub_topic.status_events.name
        }
        env {
          name  = "BUCKET_NAME"
          value = google_storage_bucket.object_storage.name
        }
      }
      vpc_access {
        network_interfaces {
          network    = google_compute_network.cloud_vpc.name
          subnetwork = google_compute_subnetwork.application_subnet.name
        }
        egress = "ALL_TRAFFIC"
      }
    }
  }

  deletion_protection = false
}

resource "google_cloud_run_v2_job" "reporting_worker" {
  name     = "reporting-worker"
  location = var.region

  template {
    template {
      service_account = google_service_account.reporting_worker_sa.email
      containers {
        image = "us-docker.pkg.dev/cloudrun/container/hello"
        env {
          name  = "BUCKET_NAME"
          value = google_storage_bucket.object_storage.name
        }
        env {
          name  = "NOTIFICATION_SERVICE_URL"
          value = google_cloud_run_v2_service.notification_service.uri
        }
      }
      vpc_access {
        network_interfaces {
          network    = google_compute_network.cloud_vpc.name
          subnetwork = google_compute_subnetwork.application_subnet.name
        }
        egress = "ALL_TRAFFIC"
      }
    }
  }

  deletion_protection = false
}

resource "google_cloud_run_v2_service" "notification_service" {
  name     = "notification-service"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.notification_sa.email
    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"
      ports {
        container_port = 8080
      }
    }
    vpc_access {
      network_interfaces {
        network    = google_compute_network.cloud_vpc.name
        subnetwork = google_compute_subnetwork.application_subnet.name
      }
      egress = "ALL_TRAFFIC"
    }
  }

  deletion_protection = false
}

resource "google_cloud_scheduler_job" "scheduler" {
  name             = "batch-trigger-scheduler"
  description      = "Scheduler - Triggers Jobs Runs on Schedule"
  schedule         = "*/15 * * * *"
  time_zone        = "Etc/UTC"
  region           = var.region
  attempt_deadline = "320s"

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.batch_processor.name}:run"
    oauth_token {
      service_account_email = google_service_account.scheduler_sa.email
    }
  }
}
