\*\*\*\*# AGENTS.md — whiteboard-to-cloud-builder

Snap a photo of a hand-drawn GCP architecture sketch, get GCP Terraform plus a
clean architecture diagram. The whole pipeline is a single model (Meta Muse
Spark, via an OpenAI-compatible API) run in four stages. No training, no
hand-written parsers.

## Setup

- Python 3.10+. `python -m venv .venv`, activate it, `python -m pip install -r requirements.txt`.
- `cp .env.example .env` and set `META_API_KEY`. Keys live in `.env` only (gitignored) — never paste one into code.
- Only `openai`, `python-dotenv`, `Pillow`, `truststore` (+ `httpx`, pulled in by `openai`) are needed for the Spark pipeline. `torch`/`torchvision`/`transformers`/`numpy` exist only for the dropped SAM experiment; skip them for pipeline-only work. Nothing is version-pinned.

## Running

Full pipeline (always pass an explicit photo path — the default is stale, see Gotchas):

```sh
python pipeline.py ./images/GCP-1-clean.jpeg
```

Stages individually:

```sh
python stages/spark_boxes.py ./images/GCP-1-clean.jpeg
python stages/spark_graph.py ./images/GCP-1-clean.jpeg boxes.json
python stages/spark_terraform.py boxes.json edges.json
python stages/spark_diagram.py boxes.json edges.json
```

`pipeline.py` runs all four with up to 3 attempts each, validates outputs, and
prints total token usage plus an approximate dollar cost (~$0.04/run). Avoid
blind rerun loops; each run costs real API money.

## Pipeline contract (read before touching stages)

| Stage     | Script                      | Args                      | Output                                    |
| --------- | --------------------------- | ------------------------- | ----------------------------------------- |
| Boxes     | `stages/spark_boxes.py`     | `<photo> [model]`         | `boxes.json` (JSON list)                  |
| Graph     | `stages/spark_graph.py`     | `<photo> <boxes> [model]` | `edges.json` (`{"edges": [...]}`)         |
| Terraform | `stages/spark_terraform.py` | `<boxes> <edges> [model]` | `terraform/*.tf` (multi-file root module) |
| Diagram   | `stages/spark_diagram.py`   | `<boxes> <edges> [model]` | `diagram.svg` (standalone SVG)            |

- Outputs are always written to the **current working directory** under fixed
  names, regardless of input paths. Run from the repo root.
- The terraform stage **deletes every `*.tf` in `terraform/`** before writing.
  Anything hand-placed there is lost on the next run.
- Model defaults to `muse-spark-1.1` (last argv), `temperature=0`,
  `extra_body={"reasoning_effort": "low"}`. Keep these unless deliberately
  experimenting.
- Every stage must print a line like `usage: <openai Usage ...>` containing
  `prompt_tokens=N` and `completion_tokens=N`. `pipeline.py` scrapes stdout
  with regex for cost reporting — do not remove or reformat that print.

## Schemas

`boxes.json` — list of shapes:

```json
{
  "label": "Core Application Service",
  "detail": "Business Logic\n...",
  "type": "component",
  "parent": "Application Subnet",
  "box": [553, 200, 720, 335]
}
```

- `type`: `component` | `container` | `external` (actors, drawn as ellipses) | `connection` (mechanisms like Direct VPC Egress — never get Terraform).
- `detail`: subtitle text or `null`; never merged into `label`.
- `parent`: containing shape's label or `null`; never invented.
- `box`: `[x_min, y_min, x_max, y_max]`, 0–1000 normalized, top-left origin.

`edges.json` — `{"edges": [{"source", "target", "mechanism"}]}`:

- `source`/`target` must match `boxes.json` labels exactly.
- `type: connection` shapes go in `mechanism` (or arrow-adjacent text does),
  never as endpoints. `mechanism` is `null` when the arrow is unlabeled.

## Output conventions

Terraform (`terraform/`):

- One root module, no submodules, no `count`/`for_each`. Split by concern:
  `variables.tf` (vars + provider), `network.tf`, `compute.tf`, `storage.tf`,
  `data.tf`, `messaging.tf`, `loadbalancer.tf`, `iam.tf`, `monitoring.tf` —
  only files for concerns present in the diagram.
- Provider `google`; `project_id` (no default), `region` (default `us-east1`).
- Demo rules: Debian 12 boot images (never retired families),
  `deletion_protection = false` on Cloud Run v2/SQL, SA `account_id` 6–30
  chars, Cloud Run ingress only from the real enum
  (`..._ALL`/`..._INTERNAL_ONLY`/`..._INTERNAL_LOAD_BALANCER`), SERVERLESS NEGs
  carry only the `cloud_run` block, Redis attaches via `authorized_network`,
  never invent resource arguments (e.g. no `description` on
  `google_storage_bucket`).
- Coverage: every `component` in `boxes.json` maps to ≥1 resource. A load
  balancer is never one resource — expand to NEG + backend service + URL map +
  proxy + forwarding rule. Don't invent components/networks/IAM beyond the
  shapes and edges.

Diagram (`diagram.svg`):

- Standalone SVG, `viewBox="0 0 1320 990"`. Reuse box coords as-is:
  `x_svg = x/1000*1320`, `y_svg = y/1000*990`.
- Containers: rounded rect behind children (via `parent`), `#E8F0FE` fill,
  `#4285F4` border, label top-left. Components: white fill, `#202124` border.
  External: ellipse. Connection types: midpoint text on the arrow, not boxes.
- Arrows edge-to-edge with marker arrowheads, mechanism label at midpoint.
  Palette: blue `#4285F4`, green `#34A853`, gray `#5F6368`. Title
  "Whiteboard-to-Cloud - Generated Architecture".

## Shared code patterns (keep when editing stages)

- `load_dotenv()` + `os.environ["META_API_KEY"]`; OpenAI client is always
  `OpenAI(base_url="https://api.meta.ai/v1", api_key=...,
http_client=httpx.Client(verify=truststore.SSLContext(...)))`. The
  truststore wrapper is for a TLS-intercepting corporate proxy — keep it.
- Prompts are inline single strings demanding bare output (JSON-only /
  SVG-only, no fences); terraform/diagram stages defensively strip code fences
  and substring from `<svg` before parsing. Validate, then write; on bad model
  output print `ERROR: ...` to stderr and `sys.exit(1)` so `pipeline.py`
  retries.
- `pipeline.py` validation: JSON must parse, SVG must contain `<svg>`,
  `terraform/` must contain ≥1 `.tf`. Extend `validate()` if you add an output
  kind (note: the `"hcl"` branch is currently dead code).

## Repo layout

- `pipeline.py` — runner (retries, validation, cost). `stages/` — the four
  stages. `images/` — sample sketches.
- Root `boxes.json`, `edges.json`, `diagram.svg` — reference sample outputs.
  `terraform/` — current generated module (generated; overwritten every run).
- Root `main.tf` — stale single-file sample from an older terraform stage.
  The pipeline no longer produces it; don't treat it as current.
- `experiments/` — dropped SAM segmentation spike (`sam_test.py`,
  `sam_masks.png`) kept as documentation, plus `draw_boxes.py`. Do not extend;
  the pipeline is Spark-only by decision.
- `v2-outputs/` — gitignored local archive of older outputs.
- No tests, linter, or CI. Verify by running the affected stage(s) and
  checking the artifact: `python -m json.tool boxes.json`,
  `terraform -chdir=terraform validate` (needs `terraform init` first),
  open `diagram.svg` in a browser.

## Gotchas / known drift

- `pipeline.py` still defaults to `./images/GCP-1.jpg`, which does not exist.
  Real inputs: `GCP-1-clean.jpeg`, `Handwritten-GCP-1.jpg`, `Sanitized.png`,
  `v3-whiteboard.jpg`. Always pass an explicit path.
- `stages/spark_terraform.py`'s "Component to resource mapping" block is
  hardcoded to old v2-diagram labels (VPC Network, Compute Engine VM, ...);
  the current reference boxes use different labels. Update that block
  deliberately when retargeting — don't assume it matches.
- `experiments/draw_boxes.py` is a broken stub (missing `sys` import,
  `if False` guard). Leave it or rewrite it deliberately.
- `README.md` is the user-facing doc; this file is the agent-facing one. When
  behavior, paths, or outputs change, update both in the same pass.
