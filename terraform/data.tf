resource "google_sql_database_instance" "postgres" {
  name                = "postgres-instance"
  region              = var.region
  database_version    = "POSTGRES_15"
  deletion_protection = false

  depends_on = [google_service_networking_connection.private_vpc_connection]

  settings {
    tier = "db-f1-micro"
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
    }
  }
}

resource "google_sql_database" "default_db" {
  name     = "appdb"
  instance = google_sql_database_instance.postgres.name
}
