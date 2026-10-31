"""spark_cost.py pure-logic tests.

Importing stages/spark_cost.py would RUN the stage (top-level API call),
so these tests AST-extract just the parse_resources/validate_cost
function defs and exec them in isolation. No subprocess, no API.

NOT COVERED (would need a live API key): the prompt build, the model
call, and the cost.json write in stages/spark_cost.py.
"""

import ast
import json
import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load_functions():
    tree = ast.parse((REPO / "stages/spark_cost.py").read_text())
    wanted = {"parse_resources", "validate_cost"}
    mod = ast.Module(
        body=[n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name in wanted],
        type_ignores=[],
    )
    ns = {"os": os, "json": json, "re": re}
    exec(compile(mod, "spark_cost.py", "exec"), ns)
    assert wanted <= set(ns), "function extraction broke — spark_cost.py refactor?"
    return ns["parse_resources"], ns["validate_cost"]


parse_resources, validate_cost = _load_functions()


def _good_payload():
    return {
        "currency": "USD",
        "assumptions": ["730h/mo, us-central1 list pricing"],
        "resources": [
            {
                "type": "google_compute_instance",
                "name": "backend_vm",
                "monthly_usd": 24.27,
                "confidence": "high",
                "note": "e2-medium @ ~$24.27/mo us-central1",
            },
            {
                "type": "google_compute_network",
                "name": "main",
                "monthly_usd": 0.00,
                "confidence": "high",
                "note": "no charge",
            },
        ],
        "total_monthly_usd": 24.27,
        "disclaimer": "Rough estimate from training-data pricing, not a quote. "
                      "Verify with the GCP Pricing Calculator.",
    }


def test_parse_resources_finds_resources_and_sizing_attrs(tmp_path):
    (tmp_path / "compute.tf").write_text(
        'resource "google_compute_instance" "backend_vm" {\n'
        '  machine_type = "e2-medium"\n'
        '  boot_disk {\n'
        '    initialize_params {\n'
        '      image = "debian-12"\n'
        '      size = 10\n'
        '    }\n'
        '  }\n'
        '}\n'
    )
    (tmp_path / "network.tf").write_text(
        'resource "google_compute_network" "main" {\n'
        '}\n'
    )
    lines = parse_resources(str(tmp_path))
    assert len(lines) == 2
    vm = [ln for ln in lines if ln.startswith("google_compute_instance.backend_vm")]
    assert len(vm) == 1
    assert "machine_type=e2-medium" in vm[0]
    assert "image=debian-12" in vm[0]
    assert "size=10" in vm[0]
    net = [ln for ln in lines if ln.startswith("google_compute_network.main")]
    assert len(net) == 1
    assert "no charge attributes" in net[0]


def test_validate_cost_accepts_good_payload():
    data = _good_payload()
    expected = [
        "google_compute_instance.backend_vm",
        "google_compute_network.main",
    ]
    validate_cost(data, expected)  # must not raise


def test_validate_cost_rejects_missing_resource():
    data = _good_payload()
    expected = [
        "google_compute_instance.backend_vm",
        "google_compute_network.main",
        "google_storage_bucket.assets",
    ]
    with pytest.raises(ValueError):
        validate_cost(data, expected)


def test_validate_cost_rejects_total_mismatch():
    data = _good_payload()
    data["total_monthly_usd"] = 99.99
    expected = [
        "google_compute_instance.backend_vm",
        "google_compute_network.main",
    ]
    with pytest.raises(ValueError):
        validate_cost(data, expected)


def test_validate_cost_rejects_malformed_json():
    with pytest.raises(ValueError):
        json.loads("{nope")
    with pytest.raises(ValueError):
        validate_cost({"foo": "bar"}, ["google_compute_network.main"])
    bad = _good_payload()
    del bad["resources"]
    with pytest.raises(ValueError):
        validate_cost(bad, ["google_compute_instance.backend_vm"])


def test_parse_resources_keeps_redis_memory_size(tmp_path):
    (tmp_path / "cache.tf").write_text(
        'resource "google_redis_instance" "cache" {\n'
        '  tier = "STANDARD_HA"\n'
        '  memory_size_gb = 5\n'
        '}\n'
    )
    lines = parse_resources(str(tmp_path))
    assert len(lines) == 1
    assert lines[0].startswith("google_redis_instance.cache")
    assert "tier=STANDARD_HA" in lines[0]
    assert "memory_size_gb=5" in lines[0]


def test_validate_cost_rejects_duplicate_resource():
    data = _good_payload()
    vm = dict(data["resources"][0])
    data["resources"].append(vm)
    data["total_monthly_usd"] = round(
        data["total_monthly_usd"] + vm["monthly_usd"], 2)
    expected = [
        "google_compute_instance.backend_vm",
        "google_compute_network.main",
    ]
    with pytest.raises(ValueError):
        validate_cost(data, expected)


def test_validate_cost_rejects_unexpected_resource():
    data = _good_payload()
    data["resources"].append({
        "type": "google_compute_instance",
        "name": "sneaky_extra",
        "monthly_usd": 10.00,
        "confidence": "low",
        "note": "invented by the model",
    })
    data["total_monthly_usd"] = round(data["total_monthly_usd"] + 10.00, 2)
    expected = [
        "google_compute_instance.backend_vm",
        "google_compute_network.main",
    ]
    with pytest.raises(ValueError):
        validate_cost(data, expected)
