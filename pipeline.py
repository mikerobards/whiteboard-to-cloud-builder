import json
import os
import re
import subprocess
import sys
import time
from dotenv import load_dotenv

load_dotenv()  # stages read it themselves; harmless here

PHOTO = sys.argv[1] if len(sys.argv) > 1 else "./images/GCP-1.jpg"
PYBIN = sys.executable  # the venv interpreter, not the Store shim

# Meta API price per 1M tokens (Oct 2026): input $1.25, output $4.25
IN_PRICE, OUT_PRICE = 1.25, 4.25

STAGES = [
    # name, command, output file, check
    ("boxes",     [PYBIN, "stages/spark_boxes.py",
     PHOTO],               "boxes.json",  "json"),
    ("graph",     [PYBIN, "stages/spark_graph.py",
     PHOTO, "boxes.json"], "edges.json",  "json"),
    ("terraform", [PYBIN, "stages/spark_terraform.py",
     "boxes.json", "edges.json"], "terraform", "tfdir"),
    ("diagram",   [PYBIN, "stages/spark_diagram.py",
     "boxes.json", "edges.json"],   "diagram.svg", "svg"),
]


def validate(kind, path):
    if kind == "tfdir":
        tfs = [f for f in os.listdir(path) if f.endswith(".tf")]
        if not tfs:
            raise ValueError("no .tf files in terraform/")
        return
    raw = open(path).read()
    if not raw.strip():
        raise ValueError("empty output")
    if kind == "json":
        json.loads(raw)
    elif kind == "svg" and "<svg" not in raw:
        raise ValueError("no <svg> in output")
    elif kind == "hcl" and "resource" not in raw:
        raise ValueError("no resource blocks in output")


def tokens_of(stdout):
    m1 = re.search(r"prompt_tokens=(\d+)", stdout)
    m2 = re.search(r"completion_tokens=(\d+)", stdout)
    return (int(m1.group(1)) if m1 else 0, int(m2.group(1)) if m2 else 0)


total_in = total_out = 0
for name, cmd, out, kind in STAGES:
    print(f"=== {name} ===", flush=True)
    for attempt in range(1, 4):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            try:
                validate(kind, out)
            except Exception as e:
                print(f"  attempt {attempt}: invalid {out} ({e}), retrying...")
            else:
                pin, pout = tokens_of(r.stdout)
                total_in += pin
                total_out += pout
                print(f"  ok -> {out} ({pin} in / {pout} out tokens)")
                break
        else:
            tail = (r.stderr or "").strip().splitlines()
            print(f"  attempt {attempt}: exit {r.returncode}"
                  + (f" ({tail[-1][:120]})" if tail else "") + ", retrying...")
        time.sleep(2 * attempt)
    else:
        print(f"PIPELINE FAILED at stage '{name}'. Fix it and rerun.")
        sys.exit(1)

cost = total_in / 1e6 * IN_PRICE + total_out / 1e6 * OUT_PRICE
print("done: boxes.json, edges.json, terraform/*.tf, diagram.svg")
print(f"total: {total_in} in / {total_out} out tokens ~= ${cost:.4f}")
