"""One front door for verification.

Usage:
  python harness.py                    -> pytest tests/ (offline, default)
  python harness.py --evals            -> pytest, then evals/run_evals.py ($)
  python harness.py --pipeline <photo> -> pipeline.py on the photo ($)

Never runs `terraform apply`. Ever.
"""

import os
import re
import subprocess
import sys

USAGE = """usage: python harness.py [--evals | --pipeline <photo>]

  (no args)            run pytest tests/ (offline, no API key, no network)
  --evals              run pytest, then evals/run_evals.py (real API calls, ~$0.06)
  --pipeline <photo>   run the full pipeline.py on the given photo (~$0.04)

Never runs `terraform apply`."""

COST_RE = re.compile(r"total:.*~=\s*\$[\d.]+")


def _run_live(cmd):
    """Run cmd, streaming its output live. Returns (returncode, output).

    Output goes to stdout as it arrives AND is captured, so the streamed
    transcript is never swallowed and the cost line can be scraped for
    the summary. PYTHONUNBUFFERED keeps the child Python process from
    block-buffering when piped; the command itself is unchanged.
    """
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env=env)
    chunks = []
    for line in proc.stdout:
        sys.stdout.write(line)
        chunks.append(line)
    proc.stdout.close()
    return proc.wait(), "".join(chunks)


def _cost_of(output):
    found = COST_RE.findall(output)
    return found[-1] if found else None


def main(argv):
    """argv without the program name. Returns an exit code."""
    pybin = sys.executable  # the venv interpreter, never python3/bare pytest
    if len(argv) == 0:
        jobs = [("pytest", [pybin, "-m", "pytest", "tests/"])]
    elif argv == ["--evals"]:
        jobs = [("pytest", [pybin, "-m", "pytest", "tests/"]),
                ("evals", [pybin, "evals/run_evals.py"])]
    elif len(argv) == 2 and argv[0] == "--pipeline":
        jobs = [("pipeline", [pybin, "pipeline.py", argv[1]])]
    else:
        print(USAGE, file=sys.stderr)
        return 2

    results = []  # (name, passed, cost_or_None)
    for name, cmd in jobs:
        print(f"=== harness: {name}: {' '.join(cmd)} ===", flush=True)
        code, output = _run_live(cmd)
        passed = code == 0
        cost = _cost_of(output) if name in ("pipeline", "evals") else None
        results.append((name, passed, cost))
        if not passed:
            break  # fail fast: never spend API money after a red gate

    print("=== harness summary ===")
    for name, passed, cost in results:
        line = f"{name}: {'PASS' if passed else 'FAIL'}"
        if cost:
            line += f" ({cost})"
        print(line)
    ran = {name for name, _, _ in results}
    for name, _ in jobs:
        if name not in ran:
            print(f"{name}: SKIPPED")
    return 0 if all(passed for _, passed, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
