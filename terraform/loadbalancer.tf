resource "google_compute_global_address" "lb_ip" {
  name = "external-lb-ip"
}

resource "google_compute_security_policy" "security_layer" {
  name        = "security-layer-policy"
  description = "Web Application Firewall Traffic Filtering Rate Limiting Threat Protection"

  rule {
    action   = "deny(403)"
    priority = 1000
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('sqli-v33-stable')"
      }
    }
    description = "SQL injection protection"
  }

  rule {
    action   = "deny(403)"
    priority = 1100
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('xss-v33-stable')"
      }
    }
    description = "XSS protection"
  }

  rule {
    action   = "throttle"
    priority = 1200
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      rate_limit_threshold {
        count        = 500
        interval_sec = 60
      }
    }
    description = "Rate limiting"
  }

  rule {
    action   = "allow"
    priority = 2147483647
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default allow"
  }
}

resource "google_compute_region_network_endpoint_group" "api_gateway_neg" {
  name                  = "api-gateway-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.api_gateway.name
  }
}

resource "google_compute_region_network_endpoint_group" "core_app_neg" {
  name                  = "core-app-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.core_app.name
  }
}

resource "google_compute_backend_service" "api_gateway_backend" {
  name                  = "api-gateway-backend"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.security_layer.id

  backend {
    group = google_compute_region_network_endpoint_group.api_gateway_neg.id
  }
}

resource "google_compute_backend_service" "core_app_backend" {
  name                  = "core-app-backend"
  load_balancing_scheme = "EXTERNAL_MANAGED"

  backend {
    group = google_compute_region_network_endpoint_group.core_app_neg.id
  }
}

resource "google_compute_url_map" "external_lb_url_map" {
  name            = "external-lb-url-map"
  default_service = google_compute_backend_service.api_gateway_backend.id

  host_rule {
    hosts        = ["*"]
    path_matcher = "allpaths"
  }

  path_matcher {
    name            = "allpaths"
    default_service = google_compute_backend_service.api_gateway_backend.id

    path_rule {
      paths   = ["/api/*"]
      service = google_compute_backend_service.core_app_backend.id
    }
  }
}

resource "google_compute_target_http_proxy" "external_proxy" {
  name    = "external-lb-http-proxy"
  url_map = google_compute_url_map.external_lb_url_map.id
}

resource "google_compute_global_forwarding_rule" "external_forwarding_rule" {
  name                  = "external-lb-forwarding-rule"
  target                = google_compute_target_http_proxy.external_proxy.id
  port_range            = "80"
  ip_address            = google_compute_global_address.lb_ip.address
  load_balancing_scheme = "EXTERNAL_MANAGED"
}
