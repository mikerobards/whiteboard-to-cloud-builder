resource "google_logging_project_sink" "centralized_logs" {
  name        = "centralized-logs-sink"
  destination = "storage.googleapis.com/${google_storage_bucket.object_storage.name}"
  filter      = "resource.type=\"cloud_run_revision\" OR resource.type=\"cloud_run_job\""

  unique_writer_identity = true
}

resource "google_storage_bucket_iam_member" "logging_sink_writer" {
  bucket = google_storage_bucket.object_storage.name
  role   = "roles/storage.objectCreator"
  member = google_logging_project_sink.centralized_logs.writer_identity
}

resource "google_monitoring_notification_channel" "email_channel" {
  display_name = "Notification Channels - Email"
  type         = "email"
  labels = {
    email_address = "alerts@example.com"
  }
}

resource "google_monitoring_notification_channel" "chat_channel" {
  display_name = "Messaging Platform - Chat Alerts"
  type         = "slack"
  labels = {
    channel_name = "#alerts"
    url          = "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"
  }
}

resource "google_monitoring_notification_channel" "sms_channel" {
  display_name = "Notification Channels - SMS"
  type         = "sms"
  labels = {
    number = "+15551234567"
  }
}

resource "google_monitoring_alert_policy" "monitoring_logging_policy" {
  display_name = "Monitoring & Logging - Centralized Logs Metrics Alerting"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Run error rate"
    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND severity >= \"ERROR\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_COUNT"
      }
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.email_channel.name,
    google_monitoring_notification_channel.chat_channel.name,
    google_monitoring_notification_channel.sms_channel.name
  ]
}
