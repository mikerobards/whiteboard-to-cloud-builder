resource "google_storage_bucket" "bucket_files_static_assets" {
  name                        = "${var.project_id}-files-static-assets"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
}

resource "google_storage_bucket_iam_member" "cloud_run_viewer" {
  bucket = google_storage_bucket.bucket_files_static_assets.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

resource "google_storage_bucket_iam_member" "vm_viewer" {
  bucket = google_storage_bucket.bucket_files_static_assets.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.backend_vm_sa.email}"
}
