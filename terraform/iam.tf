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

resource "google_project_iam_member" "core_app_redis_viewer" {
  project = var.project_id
  role    = "roles/redis.viewer"
  member  = "serviceAccount:${google_service_account.core_app_sa.email}"
}

resource "google_project_iam_member" "scheduler_run_invoker" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.scheduler_sa.email}"
}

resource "google_project_iam_member" "batch_processor_job_runner" {
  project = var.project_id
  role    = "roles/run.jobsExecutor"
  member  = "serviceAccount:${google_service_account.batch_processor_sa.email}"
}

resource "google_cloud_run_v2_service_iam_member" "api_gateway_invoker" {
  name     = google_cloud_run_v2_service.api_gateway.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "core_app_invoker" {
  name     = google_cloud_run_v2_service.core_app.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.api_gateway_sa.email}"
}
