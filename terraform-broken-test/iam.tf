resource "google_service_account" "backend_vm_sa" {
  account_id   = "backend-vm-sa"
  display_name = "Backend VM service account"
}

resource "google_service_account" "cloud_run_sa" {
  account_id   = "cloud-run-sa"
  display_name = "Cloud Run service account"
}
