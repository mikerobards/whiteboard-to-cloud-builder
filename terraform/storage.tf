resource "google_storage_bucket" "static_assets" {
  name                        = "${var.project_id}-static-assets-bucket"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
}
