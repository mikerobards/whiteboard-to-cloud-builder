resource "google_storage_bucket" "object_storage" {
  name                        = "${var.project_id}-object-storage-output"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
}

resource "google_storage_bucket_iam_member" "core_app_bucket_viewer" {
  bucket = google_storage_bucket.object_storage.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.core_app_sa.email}"
}

resource "google_storage_bucket_iam_member" "batch_processor_bucket" {
  bucket = google_storage_bucket.object_storage.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.batch_processor_sa.email}"
}

resource "google_storage_bucket_iam_member" "reporting_worker_bucket" {
  bucket = google_storage_bucket.object_storage.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.reporting_worker_sa.email}"
}
