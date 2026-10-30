"""pipeline.py pure-logic tests.

Importing pipeline.py would RUN the pipeline (top-level stage loop), so
these tests AST-extract just the tokens_of/validate function defs and exec
them in isolation. No refactor of pipeline.py, no subprocess, no API.

NOT COVERED (would need a refactor to import safely): the STAGES wiring,
the retry loop, and the cost-total math at the bottom of pipeline.py.
"""

import ast
import json
import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load_functions():
    tree = ast.parse((REPO / "pipeline.py").read_text())
    wanted = {"tokens_of", "validate"}
    mod = ast.Module(
        body=[n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name in wanted],
        type_ignores=[],
    )
    ns = {"os": os, "json": json, "re": re}
    exec(compile(mod, "pipeline.py", "exec"), ns)
    assert wanted <= set(ns), "function extraction broke — pipeline.py refactor?"
    return ns["tokens_of"], ns["validate"]


tokens_of, validate = _load_functions()


def test_tokens_of_single_usage_line():
    out = ("usage: CompletionUsage(completion_tokens=50, prompt_tokens=100,"
           " total_tokens=150)")
    assert tokens_of(out) == (100, 50)


def test_tokens_of_multiple_lines_takes_last():
    out = ("usage: CompletionUsage(completion_tokens=50, prompt_tokens=100)\n"
           "usage: prompt_tokens=300 completion_tokens=150 (total)")
    assert tokens_of(out) == (300, 150)


def test_tokens_of_no_usage_line():
    assert tokens_of("valid\n") == (0, 0)
    assert tokens_of("") == (0, 0)


def test_validate_json_ok(tmp_path):
    f = tmp_path / "b.json"
    f.write_text('{"edges": []}')
    validate("json", str(f))  # must not raise


def test_validate_json_malformed(tmp_path):
    f = tmp_path / "b.json"
    f.write_text("{nope")
    with pytest.raises(ValueError):
        validate("json", str(f))


def test_validate_empty_output_rejected(tmp_path):
    f = tmp_path / "empty.json"
    f.write_text("  \n")
    with pytest.raises(ValueError):
        validate("json", str(f))


def test_validate_svg(tmp_path):
    ok = tmp_path / "ok.svg"
    ok.write_text("<svg></svg>")
    validate("svg", str(ok))
    bad = tmp_path / "bad.svg"
    bad.write_text("not a diagram")
    with pytest.raises(ValueError):
        validate("svg", str(bad))


def test_validate_tfdir(tmp_path):
    d = tmp_path / "terraform"
    d.mkdir()
    with pytest.raises(ValueError):
        validate("tfdir", str(d))
    (d / "main.tf").write_text('resource "x" "y" {}')
    validate("tfdir", str(d))  # must not raise


def test_validate_hcl(tmp_path):
    ok = tmp_path / "ok.tf"
    ok.write_text('resource "x" "y" {}')
    validate("hcl", str(ok))
    bad = tmp_path / "bad.tf"
    bad.write_text('variable "x" {}')
    with pytest.raises(ValueError):
        validate("hcl", str(bad))
