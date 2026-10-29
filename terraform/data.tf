resource "google_redis_instance" "distributed_cache" {
  name               = "distributed-cache-kv"
  tier               = "STANDARD_HA"
  memory_size_gb     = 1
  region             = var.region
  authorized_network = google_compute_network.cloud_vpc.id
  display_name       = "Distributed Cache / Key-Value Store - Idempotency Locking"

  depends_on = [google_service_networking_connection.private_service_connection]
}
