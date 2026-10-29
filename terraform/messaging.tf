resource "google_pubsub_topic" "event_queue" {
  name = "event-queue"
}

resource "google_pubsub_topic" "status_events" {
  name = "status-events"
}

resource "google_pubsub_subscription" "event_queue_sub" {
  name  = "event-queue-sub"
  topic = google_pubsub_topic.event_queue.name

  ack_deadline_seconds = 60
}

resource "google_pubsub_subscription" "status_events_sub" {
  name  = "status-events-sub"
  topic = google_pubsub_topic.status_events.name

  ack_deadline_seconds = 20
}

resource "google_pubsub_topic_iam_member" "core_app_event_queue_publisher" {
  topic  = google_pubsub_topic.event_queue.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.core_app_sa.email}"
}

resource "google_pubsub_topic_iam_member" "core_app_status_publisher" {
  topic  = google_pubsub_topic.status_events.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.core_app_sa.email}"
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

resource "google_pubsub_subscription_iam_member" "batch_processor_event_subscriber" {
  subscription = google_pubsub_subscription.event_queue_sub.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${google_service_account.batch_processor_sa.email}"
}
