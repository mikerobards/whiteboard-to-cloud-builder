"""harness.py tests via boundary mocks (no subprocess, no network).

harness.py is import-safe (main(argv) + __main__ guard), so tests load it
by path with importlib and monkeypatch subprocess.Popen.

NOT COVERED (needs real runs): that pytest/evals/pipeline actually pass
end to end. That is what the harness itself is for.
"""

import importlib.util
import io
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load_harness():
    spec = importlib.util.spec_from_file_location("harness",
                                                  REPO / "harness.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


harness = _load_harness()

COST = "total: 100 in / 50 out tokens ~= $0.0003"


def _fake_popen(monkeypatch, script):
    """script: list of (stdout_lines, returncode) consumed in order."""
    commands = []

    class FakeProc:
        def __init__(self, lines, rc):
            self.stdout = io.StringIO("".join(lines))
            self._rc = rc

        def wait(self):
            return self._rc

    def fake_popen(cmd, **kwargs):
        commands.append((list(cmd), dict(kwargs)))
        assert script, "more subprocesses than scripted"
        assert cmd[0] == sys.executable, f"must run under sys.executable: {cmd}"
        lines, rc = script.pop(0)
        return FakeProc(lines, rc)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    return commands


def test_default_runs_pytest(monkeypatch, capsys):
    commands = _fake_popen(monkeypatch, [(["1 passed\n"], 0)])
    assert harness.main([]) == 0
    assert commands[0][0] == [sys.executable, "-m", "pytest", "tests/"]
    out = capsys.readouterr().out
    assert "1 passed" in out  # streamed, not swallowed
    assert "pytest: PASS" in out


def test_pytest_failure_exits_1(monkeypatch, capsys):
    _fake_popen(monkeypatch, [(["1 failed\n"], 1)])
    assert harness.main([]) == 1
    assert "pytest: FAIL" in capsys.readouterr().out


def test_evals_runs_pytest_then_evals(monkeypatch, capsys):
    commands = _fake_popen(monkeypatch, [(["1 passed\n"], 0),
                                        ([f"OVERALL: PASS\n{COST}\n"], 0)])
    assert harness.main(["--evals"]) == 0
    assert [c[0] for c in commands] == [
        [sys.executable, "-m", "pytest", "tests/"],
        [sys.executable, "evals/run_evals.py"],
    ]
    out = capsys.readouterr().out
    assert "pytest: PASS" in out
    assert f"evals: PASS ({COST})" in out


def test_evals_skips_evals_when_pytest_fails(monkeypatch, capsys):
    # Fail fast: never spend API money after a red offline gate.
    commands = _fake_popen(monkeypatch, [(["1 failed\n"], 1)])
    assert harness.main(["--evals"]) == 1
    assert len(commands) == 1
    out = capsys.readouterr().out
    assert "pytest: FAIL" in out
    assert "evals: SKIPPED" in out


def test_evals_failure_exits_1(monkeypatch, capsys):
    _fake_popen(monkeypatch, [(["1 passed\n"], 0),
                              (["OVERALL: FAIL\n"], 1)])
    assert harness.main(["--evals"]) == 1
    assert "evals: FAIL" in capsys.readouterr().out


@pytest.mark.parametrize("rc, verdict", [(0, "PASS"), (1, "FAIL")])
def test_pipeline_runs_photo_and_reports_cost(monkeypatch, capsys,
                                              rc, verdict):
    commands = _fake_popen(monkeypatch, [([f"{COST}\n"], rc)])
    assert harness.main(["--pipeline", "images/X.jpg"]) == rc
    assert commands[0][0] == [sys.executable, "pipeline.py", "images/X.jpg"]
    out = capsys.readouterr().out
    assert f"pipeline: {verdict} ({COST})" in out


@pytest.mark.parametrize("argv", [
    ["--bogus"], ["--pipeline"], ["--pipeline", "a.jpg", "extra"],
    ["--evals", "extra"], ["--help"], ["-h"], ["tests/"],
])
def test_anything_else_prints_usage_and_exits_2(monkeypatch, capsys, argv):
    commands = _fake_popen(monkeypatch, [])
    assert harness.main(argv) == 2
    assert commands == []
    err = capsys.readouterr().err
    assert "usage:" in err
    assert "--evals" in err and "--pipeline" in err


def test_output_streams_before_summary(monkeypatch, capsys):
    _fake_popen(monkeypatch, [(["line1\n", "line2\n"], 0)])
    harness.main([])
    out = capsys.readouterr().out
    assert out.index("line1") < out.index("line2") < out.index("summary")


def test_children_run_unbuffered(monkeypatch):
    commands = _fake_popen(monkeypatch, [(["ok\n"], 0)])
    harness.main([])
    assert commands[0][1]["env"]["PYTHONUNBUFFERED"] == "1"


def test_never_runs_terraform_apply():
    # Runtime shape: no job a test can trigger may contain "apply".
    src = (REPO / "harness.py").read_text()
    assert '"python3"' not in src and "'python3'" not in src
    for line in src.splitlines():
        if "apply" in line:
            assert "Never" in line, f"unexpected apply reference: {line}"
