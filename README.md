# Whiteboard-to-Cloud Builder

Snap a photo of a hand-drawn architecture sketch, get GCP Terraform plus a clean architecture diagram. Built for the Meta Global AI Developer Hackathon (Push the Frontier track), powered entirely by Meta's Muse Spark.

## How it works

One model does the whole job, in four stages:

1. **Boxes** — Spark detects every labeled shape in the photo: components, containers, external actors, and connection mechanisms, with normalized coordinates → `boxes.json`
2. **Graph** — Spark reads the arrows between shapes, recording mechanisms (Direct VPC Egress, Private Google Access) as edge attributes → `edges.json`
3. **Terraform** — Spark generates a complete multi-file root module from the boxes and graph → `terraform/*.tf`
4. **Diagram** — Spark renders a clean SVG architecture diagram from the same inputs → `diagram.svg`

No training, no hand-written parsers. A SAM segmentation spike was tested and dropped early; the pipeline is Spark-only end to end.

## Setup

- Python 3.10+
- `python -m venv .venv`, then activate it (Windows Git Bash note: use `python`, not `python3`, which resolves to a different interpreter)
- `python -m pip install -r requirements.txt` (only `openai`, `python-dotenv`, `Pillow`, and `truststore` are needed for the pipeline; `torch`/`torchvision`/`transformers` are only for the dropped SAM experiment)
- `cp .env.example .env` and add your Meta API key (`META_API_KEY=...`)

## Usage

Full pipeline, one command (run from the repo root; outputs are always written to the working directory):

```
python pipeline.py ./images/GCP-1-clean.jpeg
```

Other sample sketches: `Handwritten-GCP-1.jpg`, `Sanitized.png`, `v3-whiteboard.jpg`.

Or run stages individually:

```
python stages/spark_boxes.py ./images/GCP-1-clean.jpeg
python stages/spark_graph.py ./images/GCP-1-clean.jpeg boxes.json
python stages/spark_terraform.py boxes.json edges.json
python stages/spark_diagram.py boxes.json edges.json
```

Each stage validates its output and retries up to three times. The pipeline prints total token usage and an approximate dollar cost at the end. Note: the terraform stage deletes and regenerates every `*.tf` file in `terraform/` on each run.

## Cost

Roughly $0.04 per full run at current Meta API pricing. The entire demo costs less than a nickel.

## Repo layout

- `pipeline.py` — end-to-end runner with retries, validation, and cost reporting
- `stages/` — the four pipeline stages (`spark_boxes.py`, `spark_graph.py`, `spark_terraform.py`, `spark_diagram.py`)
- `terraform/` — generated Terraform root module, split by concern (`network.tf`, `compute.tf`, ...); overwritten on every pipeline run
- `experiments/` — the dropped SAM spike (`sam_test.py`) and the box-overlay debug script, kept as documentation rather than hidden
- `images/` — sample sketches
- `boxes.json`, `edges.json`, `diagram.svg` — sample outputs from the reference sketch
- `main.tf` (root) — stale single-file sample from an older version of the terraform stage; the pipeline no longer produces it
- `v2-outputs/` (gitignored) — local archive of older outputs
- `requirements.txt`, `.env.example`, `AGENTS.md`
