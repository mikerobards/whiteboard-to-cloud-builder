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

resource "google_compute_network" "cloud_environment_vpc" {
  name                    = "cloud-environment-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "application_subnet" {
  name                     = "application-subnet"
  ip_cidr_range            = "10.0.1.0/24"
  region                   = var.region
  network                  = google_compute_network.cloud_environment_vpc.id
  private_ip_google_access = true
}

resource "google_compute_subnetwork" "asynchronous_processing_subnet" {
  name                     = "asynchronous-processing-subnet"
  ip_cidr_range            = "10.0.2.0/24"
  region                   = var.region
  network                  = google_compute_network.cloud_environment_vpc.id
  private_ip_google_access = true
}

resource "google_service_account" "api_gateway_sa" {
  account_id   = "api-gateway-sa"
  display_name = "API Gateway / Access Proxy SA"
}

resource "google_service_account" "core_app_sa" {
  account_id   = "core-app-sa"
  display_name = "Core Application Service SA"
}

resource "google_service_account" "batch_processor_sa" {
  account_id   = "batch-processor-sa"
  display_name = "Batch Processor SA"
}

resource "google_service_account" "reporting_worker_sa" {
  account_id   = "reporting-worker-sa"
  display_name = "Reporting Worker SA"
}

resource "google_service_account" "notification_sa" {
  account_id   = "notification-sa"
  display_name = "Notification Service SA"
}

resource "google_service_account" "scheduler_sa" {
  account_id   = "scheduler-sa"
  display_name = "Scheduler SA"
}

resource "google_redis_instance" "distributed_cache" {
  name               = "distributed-cache"
  tier               = "BASIC"
  memory_size_gb     = 1
  region             = var.region
  redis_version      = "REDIS_7_0"
  authorized_network = google_compute_network.cloud_environment_vpc.id
  display_name       = "Distributed Cache / Key-Value Store"
}

resource "google_storage_bucket" "object_storage" {
  name     = "${var.project_id}-object-storage-output"
  location = var.region
  uniform_bucket_level_access = true
  force_destroy = true
}

resource "google_pubsub_topic" "event_queue" {
  name = "event-queue"
}

resource "google_pubsub_topic" "status_events" {
  name = "status-events"
}

resource "google_cloud_run_v2_service" "api_gateway_proxy" {
  name     = "api-gateway-proxy"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  deletion_protection = false
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
        network    = google_compute_network.cloud_environment_vpc.name
        subnetwork = google_compute_subnetwork.application_subnet.name
      }
      egress = "ALL_TRAFFIC"
    }
  }
}

resource "google_cloud_run_v2_service" "core_application_service" {
  name     = "core-application-service"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  deletion_protection = false
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
        name  = "REDIS_PORT"
        value = tostring(google_redis_instance.distributed_cache.port)
      }
      env {
        name  = "EVENT_QUEUE_TOPIC"
        value = google_pubsub_topic.event_queue.name
      }
    }
    vpc_access {
      network_interfaces {
        network    = google_compute_network.cloud_environment_vpc.name
        subnetwork = google_compute_subnetwork.application_subnet.name
      }
      egress = "ALL_TRAFFIC"
    }
  }
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
          value = google_pubsub_topic.event_queue.id
        }
        env {
          name  = "STATUS_EVENTS_TOPIC"
          value = google_pubsub_topic.status_events.id
        }
        env {
          name  = "OBJECT_STORAGE_BUCKET"
          value = google_storage_bucket.object_storage.name
        }
      }
      vpc_access {
        network_interfaces {
          network    = google_compute_network.cloud_environment_vpc.name
          subnetwork = google_compute_subnetwork.asynchronous_processing_subnet.name
        }
        egress = "ALL_TRAFFIC"
      }
    }
  }
}

resource "google_cloud_scheduler_job" "scheduler" {
  name        = "scheduler-job"
  description = "Triggers Jobs Runs on Schedule"
  region      = var.region
  schedule    = "*/5 * * * *"
  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.core_application_service.uri}/trigger-batch"
    oidc_token {
      service_account_email = google_service_account.scheduler_sa.email
    }
  }
}

resource "google_cloud_run_v2_service" "reporting_worker" {
  name     = "reporting-worker"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  deletion_protection = false
  template {
    service_account = google_service_account.reporting_worker_sa.email
    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"
      env {
        name  = "OBJECT_STORAGE_BUCKET"
        value = google_storage_bucket.object_storage.name
      }
      env {
        name  = "STATUS_EVENTS_TOPIC"
        value = google_pubsub_topic.status_events.name
      }
    }
    vpc_access {
      network_interfaces {
        network    = google_compute_network.cloud_environment_vpc.name
        subnetwork = google_compute_subnetwork.asynchronous_processing_subnet.name
      }
      egress = "ALL_TRAFFIC"
    }
  }
}

resource "google_cloud_run_v2_service" "notification_service" {
  name     = "notification-service"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  deletion_protection = false
  template {
    service_account = google_service_account.notification_sa.email
    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"
      env {
        name  = "STATUS_EVENTS_TOPIC"
        value = google_pubsub_topic.status_events.name
      }
    }
    vpc_access {
      network_interfaces {
        network    = google_compute_network.cloud_environment_vpc.name
        subnetwork = google_compute_subnetwork.asynchronous_processing_subnet.name
      }
      egress = "ALL_TRAFFIC"
    }
  }
}

resource "google_compute_security_policy" "security_layer" {
  name        = "security-layer-policy"
  description = "Web Application Firewall Traffic Filtering Rate Limiting Threat Protection"
  rule {
    action   = "allow"
    priority = 1000
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "default allow"
  }
  rule {
    action   = "throttle"
    priority = 900
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      rate_limit_threshold {
        count        = 500
        interval_sec = 60
      }
    }
    description = "Rate Limiting"
  }
}

resource "google_compute_global_address" "lb_address" {
  name = "external-lb-address"
}

resource "google_compute_region_network_endpoint_group" "api_gateway_neg" {
  name                  = "api-gateway-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.api_gateway_proxy.name
  }
}

resource "google_compute_backend_service" "external_lb_backend" {
  name                  = "external-lb-backend"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTP"
  security_policy       = google_compute_security_policy.security_layer.id
  backend {
    group = google_compute_region_network_endpoint_group.api_gateway_neg.id
  }
}

resource "google_compute_url_map" "external_lb_url_map" {
  name            = "external-lb-url-map"
  default_service = google_compute_backend_service.external_lb_backend.id
}

resource "google_compute_target_http_proxy" "external_lb_proxy" {
  name    = "external-lb-http-proxy"
  url_map = google_compute_url_map.external_lb_url_map.id
}

resource "google_compute_global_forwarding_rule" "external_lb_forwarding_rule" {
  name                  = "external-lb-forwarding-rule"
  target                = google_compute_target_http_proxy.external_lb_proxy.id
  port_range            = "80"
  ip_address            = google_compute_global_address.lb_address.address
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

resource "google_storage_bucket_iam_member" "batch_processor_storage_viewer" {
  bucket = google_storage_bucket.object_storage.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.batch_processor_sa.email}"
}

resource "google_storage_bucket_iam_member" "reporting_worker_storage_viewer" {
  bucket = google_storage_bucket.object_storage.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.reporting_worker_sa.email}"
}

resource "google_storage_bucket_iam_member" "core_app_storage_viewer" {
  bucket = google_storage_bucket.object_storage.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.core_app_sa.email}"
}

resource "google_storage_bucket_iam_member" "batch_processor_storage_admin" {
  bucket = google_storage_bucket.object_storage.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.batch_processor_sa.email}"
}

resource "google_pubsub_topic_iam_member" "batch_processor_event_publisher" {
  topic  = google_pubsub_topic.event_queue.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.batch_processor_sa.email}"
}

resource "google_pubsub_topic_iam_member" "batch_processor_status_publisher" {
  topic  = google_pubsub_topic.status_events.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.batch_processor_sa.email}"
}

resource "google_pubsub_topic_iam_member" "reporting_worker_status_subscriber" {
  topic  = google_pubsub_topic.status_events.name
  role   = "roles/pubsub.subscriber"
  member = "serviceAccount:${google_service_account.reporting_worker_sa.email}"
}

resource "google_cloud_run_v2_service_iam_member" "core_app_invoker_from_gateway" {
  name     = google_cloud_run_v2_service.core_application_service.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.api_gateway_sa.email}"
}

resource "google_cloud_run_v2_job_iam_member" "batch_processor_job_invoker" {
  name     = google_cloud_run_v2_job.batch_processor.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.core_app_sa.email}"
}

resource "google_cloud_run_v2_job_iam_member" "batch_processor_scheduler_invoker" {
  name     = google_cloud_run_v2_job.batch_processor.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler_sa.email}"
}
