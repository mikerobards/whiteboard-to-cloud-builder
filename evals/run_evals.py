"""Golden evals for prompt-regression checking. Real API calls, real cost.

Usage: python evals/run_evals.py
Runs the real boxes/graph/terraform stages plus a repair drill against two
golden cases and scores the outputs. NOT part of pipeline.py; run this after
changing a stage prompt to see what moved. Exit 0 only if every check passes.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYBIN = sys.executable

# Meta API price per 1M tokens (Oct 2026): input $1.25, output $4.25
IN_PRICE, OUT_PRICE = 1.25, 4.25

REPAIR_ATTEMPTS = 3

# Strict golden thresholds: any deviation from the goldens fails loudly.
# That is the point — silent drift in a demo pipeline is worse than noise.
MIN_LABEL_RATE = 1.0
MIN_PARENT_RATE = 1.0
MIN_EDGE_RATE = 1.0
MIN_COVERAGE = 1.0

CASES = [
    {"name": "v2",
     "photo": "images/Handwritten-GCP-1.jpg",
     "golden_boxes": "v2-outputs/boxes.json", "n_boxes": 8,
     "golden_edges": "v2-outputs/edges.json", "n_edges": 5,
     "golden_tf": ["v2-outputs/main.tf"]},
    {"name": "v3",
     "photo": "images/v3-whiteboard.jpg",
     "golden_boxes": "boxes.json", "n_boxes": 8,
     "golden_edges": "edges.json", "n_edges": 7,
     "golden_tf": None},  # None = repo terraform/*.tf
]


def tokens_of(stdout):
    # Duplicated from pipeline.py, which is not import-safe (importing it
    # runs the pipeline). Keep the two in sync: last match wins.
    m1 = re.findall(r"prompt_tokens=(\d+)", stdout)
    m2 = re.findall(r"completion_tokens=(\d+)", stdout)
    return (int(m1[-1]) if m1 else 0, int(m2[-1]) if m2 else 0)


def score_boxes(pred, gold):
    """Box count, label exact-match rate, parent correctness vs goldens."""
    gold_labels = {b.get("label") for b in gold}
    pred_labels = {b.get("label") for b in pred}
    matched = gold_labels & pred_labels
    label_rate = len(matched) / len(gold_labels) if gold_labels else 0.0
    gold_parent = {b.get("label"): b.get("parent") for b in gold}
    pred_parent = {b.get("label"): b.get("parent") for b in pred}
    same_parent = sum(1 for lab in matched
                      if pred_parent.get(lab) == gold_parent.get(lab))
    parent_rate = same_parent / len(matched) if matched else 0.0
    count_ok = len(pred) == len(gold)
    passed = (count_ok and label_rate >= MIN_LABEL_RATE
              and parent_rate >= MIN_PARENT_RATE)
    return {"count": (len(pred), len(gold)), "label_rate": label_rate,
            "parent_rate": parent_rate,
            "missing": sorted(gold_labels - pred_labels),
            "extra": sorted(pred_labels - gold_labels),
            "passed": passed}


def _edge_key(e):
    return (e.get("source"), e.get("target"), e.get("mechanism"))


def score_edges(pred, gold):
    """Edge exact-match rate (endpoints + mechanism) vs expected edges."""
    gold_keys = {_edge_key(e) for e in gold}
    pred_keys = {_edge_key(e) for e in pred}
    matched = gold_keys & pred_keys
    rate = len(matched) / len(gold_keys) if gold_keys else 0.0
    return {"rate": rate, "matched": len(matched),
            "expected": len(gold_keys),
            "missing": sorted(gold_keys - matched),
            "extra": sorted(pred_keys - gold_keys),
            "passed": rate >= MIN_EDGE_RATE}


def _slug_variants(label):
    words = re.sub(r"[^a-z0-9]+", " ", (label or "").lower()).split()
    if not words:
        return set()
    return {"_".join(words), "-".join(words), "".join(words)}


def coverage_of(components, tf_text):
    """Fraction of components with >= 1 resource in the HCL.

    Heuristic: a component counts as covered when a slug variant of its
    label (snake/kebab/squashed) appears anywhere in the module text.
    """
    hay = tf_text.lower()
    missing = [c for c in components
               if not any(v in hay for v in _slug_variants(c))]
    rate = ((len(components) - len(missing)) / len(components)
            if components else 0.0)
    return {"rate": rate, "missing": sorted(missing),
            "passed": rate >= MIN_COVERAGE}


def _run(args, cwd):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    pin, pout = tokens_of(r.stdout)
    return r, pin, pout


def _terraform_ok(tfdir):
    init = subprocess.run(["terraform", "init", "-backend=false",
                           "-input=false"], cwd=tfdir, capture_output=True,
                          text=True)
    if init.returncode != 0:
        return False, (init.stdout or "") + (init.stderr or "")
    val = subprocess.run(["terraform", "validate"], cwd=tfdir,
                         capture_output=True, text=True)
    ok = val.returncode == 0
    return ok, (val.stdout or "") + (val.stderr or "")


def _load_goldens(case):
    boxes = json.loads((REPO / case["golden_boxes"]).read_text())
    edges = json.loads((REPO / case["golden_edges"]).read_text())["edges"]
    if len(boxes) != case["n_boxes"] or len(edges) != case["n_edges"]:
        print(f"ERROR: golden counts drifted for case {case['name']}: "
              f"boxes {len(boxes)} (want {case['n_boxes']}), "
              f"edges {len(edges)} (want {case['n_edges']}). "
              f"Update CASES or restore the goldens.", file=sys.stderr)
        sys.exit(2)
    return boxes, edges


def _eval_case(case):
    """Run one case. Returns (rows, prompt_tokens, completion_tokens).

    rows: list of (check, detail, passed). Stage crashes fail their check
    (and dependents) without aborting the other case.
    """
    rows = []
    total_in = total_out = 0
    gold_boxes, gold_edges = _load_goldens(case)
    workdir = Path(tempfile.mkdtemp(prefix=f"w2c-eval-{case['name']}-"))
    print(f"--- case {case['name']} (workdir {workdir}) ---", flush=True)
    photo = str(REPO / case["photo"])

    # Boxes (real stage, real cost).
    r, pin, pout = _run([PYBIN, str(REPO / "stages" / "spark_boxes.py"),
                         photo], workdir)
    total_in += pin
    total_out += pout
    pred_boxes = None
    try:
        if r.returncode != 0:
            raise ValueError(f"boxes stage exit {r.returncode}")
        pred_boxes = json.loads((workdir / "boxes.json").read_text())
        assert isinstance(pred_boxes, list)
        s = score_boxes(pred_boxes, gold_boxes)
        detail = (f"count {s['count'][0]}/{s['count'][1]}, "
                  f"labels {s['label_rate']:.0%}, "
                  f"parents {s['parent_rate']:.0%}")
        if s["missing"]:
            detail += f" missing={s['missing']}"
        if s["extra"]:
            detail += f" extra={s['extra']}"
        rows.append(("boxes", detail, s["passed"]))
    except Exception as e:  # noqa: BLE001 - evals report, never crash
        rows.append(("boxes", f"FAILED: {e}", False))

    # Graph (real stage on the predicted boxes, like the pipeline does).
    pred_edges = None
    if pred_boxes is None:
        rows.append(("graph", "FAILED: no predicted boxes", False))
    else:
        r, pin, pout = _run(
            [PYBIN, str(REPO / "stages" / "spark_graph.py"), photo,
             "boxes.json"], workdir)
        total_in += pin
        total_out += pout
        try:
            if r.returncode != 0:
                raise ValueError(f"graph stage exit {r.returncode}")
            pred_edges = json.loads((workdir / "edges.json").read_text())
            pred_edges = pred_edges["edges"]
            s = score_edges(pred_edges, gold_edges)
            detail = (f"{s['matched']}/{s['expected']} edges "
                      f"({s['rate']:.0%})")
            if s["missing"]:
                detail += f" missing={s['missing']}"
            if s["extra"]:
                detail += f" extra={s['extra']}"
            rows.append(("graph", detail, s["passed"]))
        except Exception as e:  # noqa: BLE001
            rows.append(("graph", f"FAILED: {e}", False))

    # Terraform (real stage; validate + coverage vs predicted components).
    if pred_boxes is None or pred_edges is None:
        rows.append(("terraform", "FAILED: missing stage outputs", False))
    else:
        r, pin, pout = _run(
            [PYBIN, str(REPO / "stages" / "spark_terraform.py"),
             "boxes.json", "edges.json"], workdir)
        total_in += pin
        total_out += pout
        try:
            if r.returncode != 0:
                raise ValueError(f"terraform stage exit {r.returncode}")
            tfdir = workdir / "terraform"
            ok, out = _terraform_ok(tfdir)
            tfs = sorted(tfdir.glob("*.tf"))
            tf_text = "".join(f.read_text() for f in tfs)
            comps = [b.get("label") for b in pred_boxes
                     if b.get("type") == "component"]
            cov = coverage_of(comps, tf_text)
            passed = ok and cov["passed"]
            detail = (f"validate={'pass' if ok else 'FAIL'}, "
                      f"coverage {cov['rate']:.0%} "
                      f"({len(comps) - len(cov['missing'])}/{len(comps)})")
            if cov["missing"]:
                detail += f" missing={cov['missing']}"
            if not ok:
                tail = out.strip().splitlines()
                detail += f" err={tail[-1][:100]}" if tail else ""
            rows.append(("terraform", detail, passed))
        except Exception as e:  # noqa: BLE001
            rows.append(("terraform", f"FAILED: {e}", False))
    # Diagram stage intentionally skipped: unscored, saves one model call.

    # Repair drill: break a temp copy of the GOLDEN terraform output.
    try:
        repdir = workdir / "repair"
        repdir.mkdir()
        if case["golden_tf"] is None:
            for src in (REPO / "terraform").glob("*.tf"):
                shutil.copy(src, repdir / src.name)
        else:
            for rel in case["golden_tf"]:
                src = REPO / rel
                shutil.copy(src, repdir / src.name)
        target = None
        for f in sorted(repdir.glob("*.tf")):
            text = f.read_text()
            m = re.search(r'(resource "google_storage_bucket" "[^"]+" \{)\n',
                          text)
            if m:
                f.write_text(text[:m.end()] +
                             '  description = "broken on purpose"\n' +
                             text[m.end():])
                target = f.name
                break
        if target is None:
            raise ValueError("no google_storage_bucket block to break")
        golden_ok, _ = _terraform_ok(repdir)
        if not golden_ok:
            print(f"  note: golden {case['name']} module is itself invalid; "
                  f"repair must fix that too", flush=True)
        r, pin, pout = _run(
            [PYBIN, str(REPO / "stages" / "spark_terraform_repair.py"),
             "repair", "muse-spark-1.1", str(REPAIR_ATTEMPTS)], workdir)
        total_in += pin
        total_out += pout
        ok, _ = _terraform_ok(repdir)
        passed = r.returncode == 0 and ok
        rows.append(("repair", f"broke {target}, "
                     f"{'valid' if passed else 'STILL INVALID'} "
                     f"within {REPAIR_ATTEMPTS} attempts", passed))
    except Exception as e:  # noqa: BLE001
        rows.append(("repair", f"FAILED: {e}", False))

    return rows, total_in, total_out


def main():
    all_rows = []
    total_in = total_out = 0
    for case in CASES:
        rows, pin, pout = _eval_case(case)
        total_in += pin
        total_out += pout
        all_rows.extend([(case["name"],) + row for row in rows])

    print("\ncase  check      result  detail")
    for name, check, detail, passed in all_rows:
        print(f"{name:4}  {check:9}  {'PASS' if passed else 'FAIL':6}  "
              f"{detail}")
    cost = total_in / 1e6 * IN_PRICE + total_out / 1e6 * OUT_PRICE
    print(f"total: {total_in} in / {total_out} out tokens ~= ${cost:.4f}")
    ok = all(passed for _, _, _, passed in all_rows)
    print("OVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
