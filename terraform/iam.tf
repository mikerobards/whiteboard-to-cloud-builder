resource "google_service_account" "cloud_run_sa" {
  account_id   = "cloud-run-sa"
  display_name = "Cloud Run Service Account"
}

resource "google_service_account" "backend_vm_sa" {
  account_id   = "backend-vm-sa"
  display_name = "Backend VM Service Account"
}

resource "google_storage_bucket_iam_member" "cloud_run_viewer" {
  bucket = google_storage_bucket.static_assets.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

resource "google_storage_bucket_iam_member" "vm_viewer" {
  bucket = google_storage_bucket.static_assets.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.backend_vm_sa.email}"
}
