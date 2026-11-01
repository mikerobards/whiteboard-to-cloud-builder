"""stages/spark_terraform_repair.py tests via boundary mocks (no refactor).

The script runs its loop at import, so tests exec() its source with
openai.OpenAI and subprocess.run mocked. tmp_path stands in for both the
terraform dir ("tf/") and the repo root (repair-log.md).

NOT COVERED (needs the real model + real terraform): prompt/RULES text
quality and end-to-end convergence. Those are covered by evals/run_evals.py.
"""

import json
import re
import subprocess
import sys
import types
from pathlib import Path

import openai
import pytest

REPO = Path(__file__).resolve().parent.parent

INIT_OK = (0, "init ok\n", "")
VAL_OK = (0, "Success! The configuration is valid.\n", "")
NAMED_ERROR = "Error: bad thing\n  on a.tf line 3:\n details\n"
UNNAMED_ERROR = "Error: something with no file references\n"


def _fake_openai(monkeypatch, script):
    """script: list of (content, prompt_tokens, completion_tokens)."""
    calls = {"prompts": [], "ctor": []}

    class Completions:
        def create(self, **kwargs):
            calls["prompts"].append(kwargs)
            assert script, "model called more times than scripted"
            content, pin, pout = script.pop(0)
            usage = types.SimpleNamespace(prompt_tokens=pin,
                                          completion_tokens=pout)
            msg = types.SimpleNamespace(content=content)
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=msg)], usage=usage)

    class Client:
        def __init__(self, **kwargs):
            calls["ctor"].append(kwargs)
            self.chat = types.SimpleNamespace(completions=Completions())

    monkeypatch.setattr(openai, "OpenAI", Client)
    return calls


def _fake_terraform(monkeypatch, results):
    """results: list of (returncode, stdout, stderr) consumed in order."""
    commands = []

    def fake_run(args, **kwargs):
        commands.append((list(args), dict(kwargs)))
        assert results, "terraform called more times than scripted"
        rc, out, err = results.pop(0)
        return types.SimpleNamespace(returncode=rc, stdout=out, stderr=err)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return commands


def _run_repair(monkeypatch, workdir, tf_files, model_script, tf_results,
                max_attempts=3):
    workdir.mkdir(parents=True, exist_ok=True)
    tfdir = workdir / "tf"
    tfdir.mkdir(exist_ok=True)
    for name, content in tf_files.items():
        (tfdir / name).write_text(content)
    monkeypatch.setenv("META_API_KEY", "test-fake-key")
    monkeypatch.setattr(sys, "argv", ["spark_terraform_repair.py", "tf",
                                      "test-model", str(max_attempts)])
    monkeypatch.chdir(workdir)
    model_calls = _fake_openai(monkeypatch, model_script)
    commands = _fake_terraform(monkeypatch, tf_results)
    src = (REPO / "stages" / "spark_terraform_repair.py").read_text()
    with pytest.raises(SystemExit) as exc:
        exec(compile(src, "spark_terraform_repair.py", "exec"),
             {"__name__": "__main__"})
    return exc.value.code, model_calls, commands


def test_valid_first_try_makes_no_model_calls(monkeypatch, tmp_path, capsys):
    code, calls, commands = _run_repair(
        monkeypatch, tmp_path, {"a.tf": 'resource "x" "y" {}\n'},
        [], [INIT_OK, VAL_OK])
    assert code == 0
    assert calls["prompts"] == []
    assert not (tmp_path / "repair-log.md").exists()
    assert "valid" in capsys.readouterr().out
    assert [c[0][1] for c in commands] == ["init", "validate"]
    assert commands[0][1]["cwd"] == "tf"


def test_repairs_named_file_and_leaves_others_untouched(
        monkeypatch, tmp_path, capsys):
    tf = {"a.tf": 'resource "broken" "a" {}\n',
          "b.tf": 'output "keep" { value = 1 }\n'}
    fixed = 'resource "fixed" "a" {}\n'
    code, calls, _ = _run_repair(
        monkeypatch, tmp_path, tf,
        [(json.dumps({"a.tf": fixed}), 10, 5)],
        [INIT_OK, (1, NAMED_ERROR, ""), INIT_OK, VAL_OK])
    assert code == 0
    assert (tmp_path / "tf" / "b.tf").read_text() == tf["b.tf"]
    assert (tmp_path / "tf" / "a.tf").read_text() == fixed
    assert calls["ctor"][0]["base_url"] == "https://api.meta.ai/v1"
    prompt = calls["prompts"][0]["messages"][0]["content"]
    assert "on a.tf line 3" in prompt
    assert tf["a.tf"] in prompt
    assert tf["b.tf"] not in prompt
    assert '- Provider "google"' in prompt
    log = (tmp_path / "repair-log.md").read_text()
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", log)
    assert "attempt 1" in log
    assert "on a.tf line 3" in log
    assert "Files rewritten: a.tf" in log
    out = capsys.readouterr().out
    assert "prompt_tokens=10" in out and "completion_tokens=5" in out


def test_repair_log_is_markdownlint_clean(monkeypatch, tmp_path):
    # Terraform box-drawing output carries trailing spaces ("│ ") that
    # trip markdownlint MD009 — the log must strip them (and ANSI codes).
    error = ("\x1b[31m╷\x1b[0m\n"
             "│ Error: Unsupported argument\n"
             "│ \n"
             '│   on a.tf line 6, in resource "x" "y":\n'
             "╵\n")
    fix = json.dumps({"a.tf": 'resource "x" "a" {}\n'})
    code, _, _ = _run_repair(
        monkeypatch, tmp_path, {"a.tf": "x\n"},
        [(fix, 1, 1)],
        [INIT_OK, (1, error, ""), INIT_OK, VAL_OK])
    assert code == 0
    log = (tmp_path / "repair-log.md").read_text()
    assert "│ Error: Unsupported argument" in log
    assert "\x1b" not in log
    assert not re.search(r"[ \t]+$", log, re.M), "trailing whitespace in log"
    assert log.endswith("\n") and not log.endswith("\n\n")


def test_errors_naming_no_file_send_all_files(monkeypatch, tmp_path):
    tf = {"a.tf": 'resource "x" "a" {}\n', "b.tf": 'output "y" {}\n'}
    both = {"a.tf": tf["a.tf"], "b.tf": 'output "y" { value = 2 }\n'}
    code, calls, _ = _run_repair(
        monkeypatch, tmp_path, tf, [(json.dumps(both), 1, 1)],
        [INIT_OK, (1, UNNAMED_ERROR, ""), INIT_OK, VAL_OK])
    assert code == 0
    prompt = calls["prompts"][0]["messages"][0]["content"]
    assert tf["a.tf"] in prompt and tf["b.tf"] in prompt
    assert (tmp_path / "tf" / "b.tf").read_text() == both["b.tf"]


def test_rejects_non_dict_response(monkeypatch, tmp_path):
    code, _, _ = _run_repair(
        monkeypatch, tmp_path, {"a.tf": "x\n"}, [("[1, 2]", 1, 1)],
        [INIT_OK, (1, NAMED_ERROR, "")])
    assert code == 1


def test_rejects_empty_response(monkeypatch, tmp_path):
    code, _, _ = _run_repair(
        monkeypatch, tmp_path, {"a.tf": "x\n"}, [("{}", 1, 1)],
        [INIT_OK, (1, NAMED_ERROR, "")])
    assert code == 1


def test_rejects_bad_file_entries(monkeypatch, tmp_path):
    for i, payload in enumerate(({"nope.txt": "x"}, {"a.tf": "   "})):
        code, _, _ = _run_repair(
            monkeypatch, tmp_path / f"case{i}", {"a.tf": "x\n"},
            [(json.dumps(payload), 1, 1)],
            [INIT_OK, (1, NAMED_ERROR, "")])
        assert code == 1


def test_rejects_omitted_shown_file_without_wiping(monkeypatch, tmp_path):
    before = 'resource "broken" "a" {}\n'
    code, _, _ = _run_repair(
        monkeypatch, tmp_path, {"a.tf": before},
        [(json.dumps({"b.tf": 'output "x" { value = 1 }\n'}), 1, 1)],
        [INIT_OK, (1, NAMED_ERROR, "")])
    assert code == 1
    assert (tmp_path / "tf" / "a.tf").read_text() == before


def test_gives_up_after_attempt_cap(monkeypatch, tmp_path, capsys):
    fix = json.dumps({"a.tf": 'resource "x" "a" {}\n'})
    code, calls, _ = _run_repair(
        monkeypatch, tmp_path, {"a.tf": "x\n"},
        [(fix, 1, 1), (fix, 1, 1)],
        [INIT_OK, (1, NAMED_ERROR, ""), INIT_OK, (1, NAMED_ERROR, "")],
        max_attempts=2)
    assert code == 1
    assert len(calls["prompts"]) == 2
    log = (tmp_path / "repair-log.md").read_text()
    assert log.count("## ") == 2
    assert "on a.tf line 3" in capsys.readouterr().out


def test_filename_pattern_matches_real_validate_output():
    # The pattern lives inline in the script (no refactor allowed), so this
    # test extracts the real pattern string from the source and exercises it.
    src = (REPO / "stages" / "spark_terraform_repair.py").read_text()
    m = re.search(r're\.findall\(r"([^"]+)", errors\)', src)
    assert m, "pattern extraction broke — script refactor?"
    pat = re.compile(m.group(1))
    line = ('  on storage.tf line 6, in resource "google_storage_bucket"'
            ' "b":')
    assert pat.findall(line) == ["storage.tf"]
    assert pat.findall("declared at variables.tf:1,1-22.") == ["variables.tf"]
    plugin = ("Path: .terraform/providers/registry.terraform.io/hashicorp/"
              "google/8.9.0/darwin_arm64/terraform-provider-google_v8.9.0_x5")
    assert pat.findall(plugin) == []
