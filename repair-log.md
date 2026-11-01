# Repair Log

<!-- markdownlint-disable MD013 -->

## 2026-10-30 13:11:34 — attempt 1/3 (terraform-broken-test/)

Validate errors:

```text
╷
│ Error: Unsupported argument
│
│   on storage.tf line 6, in resource "google_storage_bucket" "bucket_files_static_assets":
│    6:   description                 = "broken on purpose"
│
│ An argument named "description" is not expected here.
╵
```

Files rewritten: storage.tf

## 2026-11-01 13:48:20 — attempt 1/3 (terraform)

Validate errors:

```text
╷
│ Error: Unsupported argument
│
│   on storage.tf line 7, in resource "google_storage_bucket" "files_assets":
│    7:   description                 = "demo break"
│
│ An argument named "description" is not expected here.
╵
```

Files rewritten: storage.tf

## 2026-11-01 13:49:10 — attempt 1/3 (terraform)

Validate errors:

```text
╷
│ Error: Incorrect attribute value type
│
│   on compute.tf line 5, in resource "google_cloud_run_v2_service" "serverless_fe":
│    5:   deletion_protection = 0
│
│ Inappropriate value for attribute "deletion_protection": bool required, but
│ have number.
╵
```

Files rewritten: compute.tf

## 2026-11-01 13:49:43 — attempt 1/3 (terraform)

Validate errors:

```text
╷
│ Error: Invalid reference
│
│   on compute.tf line 5, in resource "google_cloud_run_v2_service" "serverless_fe":
│    5:   deletion_protection = FALSE
│
│ A reference to a resource type must be followed by at least one attribute
│ access, specifying the resource name.
╵
```

Files rewritten: compute.tf

## 2026-11-01 13:50:31 — attempt 1/3 (terraform)

Validate errors:

```text
╷
│ Error: Unsupported argument
│
│   on storage.tf line 7, in resource "google_storage_bucket" "files_assets":
│    7:   description                 = "demo break"
│
│ An argument named "description" is not expected here.
╵
```

Files rewritten: storage.tf

## 2026-11-01 13:51:57 — attempt 1/3 (terraform)

Validate errors:

```text
╷
│ Error: invalid value "Mikey" for member (IAM members must have one of the values outlined here: https://cloud.google.com/billing/docs/reference/rest/v1/Policy#Binding)
│
│   with google_cloud_run_v2_service_iam_member.serverless_fe_public,
│   on compute.tf line 31, in resource "google_cloud_run_v2_service_iam_member" "serverless_fe_public":
│   31:   member   = "Mikey"
│
╵
```

Files rewritten: compute.tf

## 2026-11-01 13:53:40 — attempt 1/3 (terraform)

Validate errors:

```text
╷
│ Error: invalid value "Mikey" for member (IAM members must have one of the values outlined here: https://cloud.google.com/billing/docs/reference/rest/v1/Policy#Binding)
│
│   with google_cloud_run_v2_service_iam_member.serverless_fe_public,
│   on compute.tf line 31, in resource "google_cloud_run_v2_service_iam_member" "serverless_fe_public":
│   31:   member   = "Mikey"
│
╵
```

Files rewritten: compute.tf

## 2026-11-01 14:03:09 — attempt 1/3 (terraform)

Validate errors:

```text
╷
│ Error: Unsupported argument
│
│   on data.tf line 6, in resource "google_sql_database_instance" "postgres":
│    6:   description         = "demo break"
│
│ An argument named "description" is not expected here.
╵
```

Files rewritten: data.tf

## 2026-11-01 14:03:35 — attempt 1/3 (terraform)

Validate errors:

```text
╷
│ Error: Unsupported argument
│
│   on loadbalancer.tf line 15, in resource "google_compute_backend_service" "frontend_backend":
│   15:   descritption          = "Good stuff"
│
│ An argument named "descritption" is not expected here. Did you mean
│ "description"?
╵
```

Files rewritten: loadbalancer.tf

## 2026-11-01 14:04:01 — attempt 1/3 (terraform)

Validate errors:

```text
╷
│ Error: Unsupported argument
│
│   on loadbalancer.tf line 8, in resource "google_compute_region_network_endpoint_group" "cloud_run_neg":
│    8:     description = "good stuff"
│
│ An argument named "description" is not expected here.
╵
```

Files rewritten: loadbalancer.tf

## 2026-11-01 14:04:35 — attempt 1/3 (terraform)

Validate errors:

```text
╷
│ Error: Unsupported argument
│
│   on data.tf line 21, in resource "google_sql_database" "default_db":
│   21:   size     = "100GB"
│
│ An argument named "size" is not expected here.
╵
```

Files rewritten: data.tf

## 2026-11-01 14:04:54 — attempt 1/3 (terraform)

Validate errors:

```text
╷
│ Error: Invalid reference
│
│   on network.tf line 11, in resource "google_compute_subnetwork" "private_subnet":
│   11:   private_ip_google_access = FALSE
│
│ A reference to a resource type must be followed by at least one attribute
│ access, specifying the resource name.
╵
```

Files rewritten: network.tf

## 2026-11-01 14:05:46 — attempt 1/3 (terraform)

Validate errors:

```text
╷
│ Error: Unsupported argument
│
│   on compute.tf line 11, in resource "google_compute_instance" "backend_vm":
│   11:       desc = "good stuff"
│
│ An argument named "desc" is not expected here.
╵
```

Files rewritten: compute.tf
