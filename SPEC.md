# SPEC.md — whiteboard-to-cloud-builder

The normative spec. `AGENTS.md` is the operational guide for working in the
repo; this file states what the system must do. When they disagree, this file
wins.

## 1. Problem statement

A photo of a hand-drawn cloud architecture sketch or diagram goes in; production-shaped
GCP Terraform and a clean architecture diagram come out. One model (Meta Muse
Spark, via an OpenAI-compatible API), six stages, no training, no
hand-written parsers.

## 2. Stage contracts

### Boxes — `stages/spark_boxes.py <photo> [model]` → `boxes.json`

- Detects every labeled shape with: `label`; `detail` (subtitle text or `null`,
  never merged into `label`); `type` (`component` | `container` | `external` |
  `connection`); `parent` (containing shape's label or `null`, never invented);
  `box` (`[x_min, y_min, x_max, y_max]`, 0–1000 normalized, top-left origin).
- `type: connection` shapes are mechanisms (e.g. Direct VPC Egress) — they
  never become Terraform resources.
- Output is a JSON list. It must parse.

### Graph — `stages/spark_graph.py <photo> <boxes> [model]` → `edges.json`

- Reads the arrows between shapes: `source` and `target` must match
  `boxes.json` labels; `mechanism` is the connection-type label or
  arrow-adjacent text, else `null`.
- Mechanisms are edge attributes, never endpoints.
- Output is `{"edges": [...]}`. It must parse.

### Terraform — `stages/spark_terraform.py <boxes> <edges> [model]` → `terraform/*.tf`

- Emits a multi-file Terraform root module: no submodules, no
  `count`/`for_each`.
- Files split by concern (variables, network, compute, storage, data,
  messaging, loadbalancer, iam, monitoring) — only concerns present in the
  diagram.
- Must satisfy every prompt rule in §3.

### Repair — `stages/spark_terraform_repair.py [terraform_dir] [model] [max_attempts]` → in place

- Runs `terraform init -backend=false` + `terraform validate`. On failure,
  asks the model to fix the errors — prompt rules + raw validate errors +
  full contents of the implicated files — rewrites, re-validates.
- Attempt cap: 3 per invocation. Exit 0 on valid; exit 1 after the cap, failing
  loudly so the human takes over.
- Fixes instances, not patterns: every repair is logged to `repair-log.md`;
  the human decides what becomes a permanent prompt rule.
- Guarantees valid HCL, not correct infrastructure. Never runs
  `terraform apply`.

### Cost — `stages/spark_cost.py [terraform_dir] [model]` → `cost.json`

- Estimates monthly GCP cost from the resource types and sizing attributes
  parsed out of `terraform/`. Runs after repair, so it prices the final
  validated module.
- Output is a JSON object: `currency`, `assumptions`, `resources` (one entry
  per input resource: `type`, `name`, `monthly_usd`, `confidence`, `note`),
  `total_monthly_usd` (must equal the sum of `monthly_usd`), `disclaimer`.
- Coverage: every resource parsed from `terraform/` must appear in
  `resources`; resources with no charge are listed at `0.00`.
- Estimates come from the model's training-data pricing and are labeled as
  such — never presented as a quote.

### Diagram — `stages/spark_diagram.py <boxes> <edges> [model]` → `diagram.svg`

- Standalone SVG rendering of the detected architecture (visual spec lives in
  `AGENTS.md`).

## 3. Prompt rules (normative)

The Terraform generator and repairer MUST obey all of the following:

1. Provider `google`. Variables: `project_id` (no default), `region` (default `us-east1`).
2. One root module, multiple files, no submodules, no `count`/`for_each`. Valid HCL.
3. Boot images: a current Debian family (`debian-12`). Never retired families.
4. Databases: `database_version` from the box `detail` (`POSTGRES_15` / `MYSQL_8_0`); default `POSTGRES_15` when no engine is named.
5. Demo: `deletion_protection = false` on Cloud Run v2 services and SQL instances.
6. Service account `account_id`: 6–30 characters.
7. Coverage: every `component` in `boxes.json` maps to at least one resource. A load balancer is never one resource — expand to NEG + backend service + URL map + proxy + forwarding rule.
8. Serverless NEGs: `cloud_run` block only, never a `network_endpoint` block with instance/port.
9. Cloud Run v2 `ingress`: a real enum only (`INGRESS_TRAFFIC_ALL` / `INGRESS_TRAFFIC_INTERNAL_ONLY` / `INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER`); prefer `INTERNAL_LOAD_BALANCER` when a load balancer fronts the service.
10. Memorystore Redis: `authorized_network`, never a bare `network` argument.
11. Never invent resource arguments — only arguments the provider documents for that resource type.
12. Never invent components, networks, firewall rules, or IAM beyond what the shapes and edges describe.

## 4. Design decisions

- **Self-correcting loop.** Perception stages are stable; generation is where variance lives. The pipeline validates and repairs instead of asking the human to debug model output.
- **Attempt caps.** 3 per repair invocation; `pipeline.py` retries failed stages up to 3 times (worst case 9 repair calls — bounded, still cents).
- **Human applies.** No code path runs `terraform apply`. Ever.
- **Prompt-hardening discipline.** Model mistakes are fixed by hardening prompts and re-running, never by hand-editing generated files.
- **Meta models only.** Muse Code and `muse-spark-1.1`. Named exceptions: Gemini generates diagram images, Claude answers questions.
- **Strict evals.** Golden thresholds are 1.0 — drift fails loudly instead of silently. Label comparison is case-insensitive (casing is not architecture); resource coverage is by type, not by name.
- **Cost budget.** About $0.04 per pipeline run, $0.06 per full eval run, half a cent per repair call. Against $150 in credits, effectively free.

## 5. Golden cases

- **v2**: `images/Handwritten-GCP-1.jpg` → 8 boxes, 5 edges (goldens in `v2-outputs/`).
- **v3**: `images/v3-whiteboard.jpg` → 8 boxes, 7 edges.
- `python evals/run_evals.py` must exit 0. The v2 golden `main.tf` is stale against the current provider — it is kept as a repair-drill target, not a deployable sample. The v3 golden is the repo's `terraform/`.

## 6. Non-goals

- Not a general whiteboard interpreter — GCP architecture sketches only.
- Not a deployment tool — the output is validated HCL for human review and apply.
- No CI, no linter. Verification is `pytest tests/`, `python evals/run_evals.py`, and human eyes on the artifacts.
