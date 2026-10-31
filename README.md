# Whiteboard-to-Cloud Builder

Snap a photo of a hand-drawn architecture sketch, get GCP Terraform plus a clean architecture diagram. Built for the Meta Global AI Developer Hackathon (Push the Frontier track), powered entirely by Meta's Muse Spark.

## How it works

One model does the whole job, in five stages:

1. **Boxes** — Spark detects every labeled shape in the photo: components, containers, external actors, and connection mechanisms, with normalized coordinates → `boxes.json`
2. **Graph** — Spark reads the arrows between shapes, recording mechanisms (Direct VPC Egress, Private Google Access) as edge attributes → `edges.json`
3. **Terraform** — Spark generates a complete multi-file root module from the boxes and graph → `terraform/*.tf`
4. **Diagram** — Spark renders a clean SVG architecture diagram from the same inputs → `diagram.svg`
5. **Cost** — Spark estimates the monthly GCP cost of the generated module from its resource types and sizes → `cost.json` (an estimate from training-data pricing, not a quote)

No training, no hand-written parsers. A SAM segmentation spike was tested and dropped early; the pipeline is Spark-only end to end.

## Setup

- Python 3.10+
- `python -m venv .venv`, then activate it (Windows Git Bash note: use `python`, not `python3`, which resolves to a different interpreter)
- `python -m pip install -r requirements.txt` (only `openai`, `python-dotenv`, `Pillow`, and `truststore` are needed for the pipeline; `torch`/`torchvision`/`transformers` are only for the dropped SAM experiment)
- `cp .env.example .env` and add your Meta API key (`META_API_KEY=...`)

## Usage

Full pipeline, one command (run from the repo root; outputs are always written to the working directory):

```bash
python pipeline.py ./images/GCP-1-clean.jpeg
```

Other sample sketches: `Handwritten-GCP-1.jpg`, `Sanitized.png`, `v3-whiteboard.jpg`.

Or run stages individually:

```bash
python stages/spark_boxes.py ./images/GCP-1-clean.jpeg
python stages/spark_graph.py ./images/GCP-1-clean.jpeg boxes.json
python stages/spark_terraform.py boxes.json edges.json
python stages/spark_cost.py [terraform_dir] [model]
python stages/spark_diagram.py boxes.json edges.json
```

Each stage validates its output and retries up to three times. The pipeline prints total token usage and an approximate dollar cost at the end. Note: the terraform stage deletes and regenerates every `*.tf` file in `terraform/` on each run.

## Testing the repair loop

The `terraform-repair` stage validates the generated module and asks Spark to fix any errors, looping until `terraform validate` passes (3 attempts by default). To try it with a deliberately broken module:

1. Copy a known-good module to a scratch directory (outside the repo, so the pipeline's `terraform/` output stays intact):

   ```bash
   cp -r terraform /tmp/tf-broken
   ```

2. Break one file on purpose — e.g. add an unsupported `description` argument to the bucket in `/tmp/tf-broken/storage.tf`:

   ```hcl
   resource "google_storage_bucket" "bucket_files_static_assets" {
     ...
     description = "broken on purpose"
   }
   ```

3. Run the repair script against it (args: `[terraform_dir] [model] [max_attempts]`):

   ```bash
   python stages/spark_terraform_repair.py /tmp/tf-broken
   ```

4. Watch the loop: an `attempt N/M` banner, the full raw validate errors, `rewrote: ...`, per-call `usage:` lines, and finally `valid`.
5. Confirm: `terraform -chdir=/tmp/tf-broken validate` should pass, and `repair-log.md` (repo root) records the timestamp, attempt, errors, and files rewritten.
6. Delete the scratch dir when done.

The loop only guarantees valid HCL — it never runs `terraform apply`. That's still your call.

## Tests and evals

Front door: `python harness.py` runs the unit tests (offline, default),
`python harness.py --evals` adds the golden evals, and
`python harness.py --pipeline <photo>` runs the full pipeline on a photo.
Anything else prints usage and exits 2. Every step streams live with a
pass/fail summary at the end.

Unit tests — offline, no API key needed:

```bash
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m pytest tests/ -q
```

Tests mock the model client and `subprocess` at the boundary (a fixture fails any test that touches the network), and never refactor the stage scripts to do it. Untestable-without-refactor areas are noted in the test files rather than covered.

Evals — real API calls, roughly $0.05 per case (~$0.10 for the full two-case run):

```bash
python evals/run_evals.py
```

Runs boxes, graph, terraform, plus a repair drill against the v2 and v3 golden cases, then prints a score table and total cost. Exits nonzero unless every check passes. This is the prompt-regression gate: run it after any stage-prompt change. Strict by design — any deviation from the goldens fails.

## Cost

Roughly $0.04 per full run at current Meta API pricing. The entire demo costs less than a nickel.

## Repo layout

- `pipeline.py` — end-to-end runner with retries, validation, and cost reporting
- `stages/` — the six pipeline stages (`spark_boxes.py`, `spark_graph.py`, `spark_terraform.py`, `spark_terraform_repair.py`, `spark_cost.py`, `spark_diagram.py`)
- `terraform/` — generated Terraform root module, split by concern (`network.tf`, `compute.tf`, ...); overwritten on every pipeline run
- `experiments/` — the dropped SAM spike (`sam_test.py`) and the box-overlay debug script, kept as documentation rather than hidden
- `images/` — sample sketches
- `boxes.json`, `edges.json`, `cost.json`, `diagram.svg` — sample outputs from the reference sketch
- `main.tf` (root) — stale single-file sample from an older version of the terraform stage; the pipeline no longer produces it
- `v2-outputs/` (gitignored) — local archive of older outputs
- `requirements.txt`, `.env.example`, `AGENTS.md`
