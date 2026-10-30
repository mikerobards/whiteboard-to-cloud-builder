"""stages/spark_terraform.py output-parsing tests via boundary mocks.

Same technique as test_repair_logic.py: exec() the script source with
openai.OpenAI mocked. boxes.json/edges.json only feed the prompt (never
parsed for control flow), so minimal fixtures suffice.

NOT COVERED (needs the real model): prompt/RULES text and the quality of
the boxes-to-resources mapping. Covered by evals/run_evals.py instead.
"""

import json
import sys
import types
from pathlib import Path

import openai
import pytest

REPO = Path(__file__).resolve().parent.parent

GOOD_FILES = {
    "variables.tf": 'variable "project_id" {\n  type = string\n}\n',
    "network.tf": 'resource "google_compute_network" "v" {}\n',
}


def _fake_openai(monkeypatch, content):
    calls = {}

    class Completions:
        def create(self, **kwargs):
            calls["prompt"] = kwargs["messages"][0]["content"]
            usage = types.SimpleNamespace(prompt_tokens=7,
                                          completion_tokens=3)
            msg = types.SimpleNamespace(content=content)
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=msg)], usage=usage)

    class Client:
        def __init__(self, **kwargs):
            self.chat = types.SimpleNamespace(completions=Completions())

    monkeypatch.setattr(openai, "OpenAI", Client)
    return calls


def _run_gen(monkeypatch, workdir, model_content, preexisting=None):
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "boxes.json").write_text('[{"label": "X"}]')
    (workdir / "edges.json").write_text('{"edges": []}')
    if preexisting:
        t = workdir / "terraform"
        t.mkdir(exist_ok=True)
        for name, content in preexisting.items():
            (t / name).write_text(content)
    monkeypatch.setenv("META_API_KEY", "test-fake-key")
    monkeypatch.setattr(sys, "argv", ["spark_terraform.py", "boxes.json",
                                      "edges.json", "test-model"])
    monkeypatch.chdir(workdir)
    calls = _fake_openai(monkeypatch, model_content)
    src = (REPO / "stages" / "spark_terraform.py").read_text()
    exec(compile(src, "spark_terraform.py", "exec"), {"__name__": "__main__"})
    return calls


def test_fenced_json_is_stripped_and_written(monkeypatch, tmp_path, capsys):
    content = "```json\n" + json.dumps(GOOD_FILES) + "\n```"
    _run_gen(monkeypatch, tmp_path, content,
             preexisting={"stale.tf": "old"})
    t = tmp_path / "terraform"
    assert not (t / "stale.tf").exists()
    for name, body in GOOD_FILES.items():
        assert (t / name).read_text() == body
    out = capsys.readouterr().out
    assert "prompt_tokens=7" in out and "completion_tokens=3" in out


def test_bare_json_is_accepted(monkeypatch, tmp_path):
    _run_gen(monkeypatch, tmp_path, json.dumps(GOOD_FILES))
    assert (tmp_path / "terraform" / "network.tf").read_text() == \
        GOOD_FILES["network.tf"]


def _expect_exit_1(monkeypatch, workdir, model_content):
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "boxes.json").write_text("[]")
    (workdir / "edges.json").write_text("{}")
    monkeypatch.setenv("META_API_KEY", "test-fake-key")
    monkeypatch.setattr(sys, "argv", ["spark_terraform.py", "boxes.json",
                                      "edges.json", "test-model"])
    monkeypatch.chdir(workdir)
    _fake_openai(monkeypatch, model_content)
    src = (REPO / "stages" / "spark_terraform.py").read_text()
    with pytest.raises(SystemExit) as exc:
        exec(compile(src, "spark_terraform.py", "exec"),
             {"__name__": "__main__"})
    assert exc.value.code == 1


def test_rejects_non_dict_response(monkeypatch, tmp_path):
    _expect_exit_1(monkeypatch, tmp_path, "[1, 2]")


def test_rejects_empty_response(monkeypatch, tmp_path):
    _expect_exit_1(monkeypatch, tmp_path, "{}")


def test_rejects_bad_file_entries(monkeypatch, tmp_path):
    _expect_exit_1(monkeypatch, tmp_path,
                   json.dumps({"nope.txt": "resource x"}))
    _expect_exit_1(monkeypatch, tmp_path / "c2",
                   json.dumps({"a.tf": "   "}))


def test_rejects_file_without_resource_keyword(monkeypatch, tmp_path):
    # Generator-strict by design (unlike the repair stage, which accepts
    # outputs-only files): every emitted file must mention a resource,
    # variable, or provider block.
    _expect_exit_1(monkeypatch, tmp_path,
                   json.dumps({"out.tf": 'output "x" { value = 1 }\n'}))
