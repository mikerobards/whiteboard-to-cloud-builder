# Whiteboard-to-Cloud Builder

Snap a photo of a hand-drawn architecture sketch, get GCP Terraform plus a clean architecture diagram. Built for the Meta Global AI Developer Hackathon (Push the Frontier track), powered entirely by Meta's Muse Spark.

## How it works

One model does the whole job, in four stages:

1. **Boxes** — Spark detects every labeled shape in the photo: components, containers, external actors, and connection mechanisms, with normalized coordinates → `boxes.json`
2. **Graph** — Spark reads the arrows between shapes, recording mechanisms (Direct VPC Egress, Private Google Access) as edge attributes → `edges.json`
3. **Terraform** — Spark generates a complete root-module `main.tf` from the boxes and graph
4. **Diagram** — Spark renders a clean SVG architecture diagram from the same inputs → `diagram.svg`

No training, no hand-written parsers. A SAM segmentation spike was tested and dropped early; the pipeline is Spark-only end to end.

## Setup

- Python 3.10+
- `python -m venv .venv`, then activate it (Windows Git Bash note: use `python`, not `python3`, which resolves to a different interpreter)
- `python -m pip install -r requirements.txt`
- `cp .env.example .env` and add your Meta API key (`META_API_KEY=...`)

## Usage

Full pipeline, one command:

```
python pipeline.py ./images/GCP-1.jpg
```

Or run stages individually:

```
python spark_boxes.py ./images/GCP-1.jpg
python spark_graph.py ./images/GCP-1.jpg boxes.json
python spark_terraform.py boxes.json edges.json
python spark_diagram.py boxes.json edges.json
```

Each stage validates its output and retries up to three times. The pipeline prints total token usage and an approximate dollar cost at the end.

## Cost

Roughly $0.04 per full run at current Meta API pricing. The entire demo costs less than a nickel.

## Repo layout

- `spark_boxes.py`, `spark_graph.py`, `spark_terraform.py`, `spark_diagram.py` — the four pipeline stages
- `pipeline.py` — end-to-end runner with retries, validation, and cost reporting
- `images/` — sample sketches
- `boxes.json`, `edges.json`, `main.tf`, `diagram.svg` — sample outputs from the reference sketch
- `requirements.txt`, `.env.example`
