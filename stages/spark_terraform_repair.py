import json
import os
import re
import ssl
import subprocess
import sys
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
import httpx
import truststore

load_dotenv()  # reads META_API_KEY from .env in the project root
# Never paste the key into this file. Keep it in .env only (gitignored).

# Usage: python stages/spark_terraform_repair.py [terraform_dir] [model] [max_attempts]
# Validates terraform_dir with `terraform init` + `terraform validate` and asks
# the model to fix any errors, looping until valid or attempts run out.
# This loop only guarantees valid HCL; it never runs `terraform apply`.
TFDIR = sys.argv[1] if len(sys.argv) > 1 else "terraform"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "muse-spark-1.1"
MAX_ATTEMPTS = max(1, int(sys.argv[3])) if len(sys.argv) > 3 else 3

# Work-laptop TLS: the corporate proxy's CA lives in the Windows cert store.
_tls = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_http = httpx.Client(verify=_tls)
client = OpenAI(base_url="https://api.meta.ai/v1",
                api_key=os.environ["META_API_KEY"],
                http_client=_http)

# Generation rules, copied verbatim from stages/spark_terraform.py.
# The repaired module must obey all of them.
RULES = """- Provider "google". Variables: project_id (no default), region (default "us-east1").
- Multiple files in one root module, no submodules, no count/for_each. Valid HCL that a terraform init could consume.
- Boot images: use a current Debian family (debian-cloud/debian-12). Never use retired families such as debian-11.
- Databases: if a database shape's detail names an engine (e.g. Postgres, MySQL), set database_version to match (POSTGRES_15, MYSQL_8_0); default to POSTGRES_15 when no engine is given.
- This is a demo/test file: set deletion_protection = false on Cloud Run v2 services and SQL instances so teardown is clean.
- Service account account_id values must be 6-30 characters long (e.g. backend-vm-sa, cloud-run-sa) — shorter IDs are rejected by GCP.
- Coverage check before finalizing: every component in boxes.json must have at least one corresponding resource in the output. A load balancer is never a single resource — expand it into a network endpoint group, backend service, URL map, proxy, and forwarding rule.
- Serverless network endpoint groups (network_endpoint_type = "SERVERLESS"): configure only the cloud_run block — never add a network_endpoint block with instance/port.
- Cloud Run v2 ingress must be one of INGRESS_TRAFFIC_ALL, INGRESS_TRAFFIC_INTERNAL_ONLY, or INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER (or omitted) — never invent values. Prefer INTERNAL_LOAD_BALANCER when a load balancer fronts the service.
- Memorystore Redis (google_redis_instance) attaches to the VPC via authorized_network — never use a bare network argument.
- Never invent arguments on a resource: only use arguments the provider documents for that resource type (e.g. google_storage_bucket has no description argument — leave it off rather than guessing).
- Do not invent components, networks, firewall rules, or IAM beyond what the shapes and edges describe."""


def tf_files():
    return sorted(f for f in os.listdir(TFDIR) if f.endswith(".tf"))


ANSI = re.compile(r"\x1b\[[0-9;]*m")  # terraform SGR color codes


def clean(text):
    # Strip ANSI codes AND trailing whitespace per line: terraform's
    # box-drawing output ("│ " on blank lines) would otherwise trip MD009
    # (no-trailing-spaces) in repair-log.md on every run.
    return "\n".join(line.rstrip()
                     for line in ANSI.sub("", text).split("\n"))


def run_terraform(args):
    try:
        return subprocess.run(args, cwd=TFDIR, capture_output=True, text=True)
    except FileNotFoundError:
        print("ERROR: terraform binary not found on PATH",
              file=sys.stderr, flush=True)
        sys.exit(1)


total_in = total_out = 0
calls = 0
errors = ""

for attempt in range(1, MAX_ATTEMPTS + 1):
    print(f"=== terraform-repair (attempt {attempt}/{MAX_ATTEMPTS}) ===",
          flush=True)
    tfs = tf_files()
    print("validating: " + (", ".join(tfs) if tfs else "(no .tf files)"),
          flush=True)

    init = run_terraform(["terraform", "init", "-backend=false"])
    if init.returncode != 0:
        errors = (init.stdout or "") + (init.stderr or "")
        valid = False
    else:
        val = run_terraform(["terraform", "validate"])
        errors = (val.stdout or "") + (val.stderr or "")
        valid = val.returncode == 0

    if valid:
        print("valid", flush=True)
        if calls:
            print(f"usage: prompt_tokens={total_in}"
                  f" completion_tokens={total_out}"
                  f" (total across {calls} repair calls)",
                  flush=True)
        sys.exit(0)

    print(errors.rstrip() or "(no output)", flush=True)

    hits = set(os.path.basename(m)
               for m in re.findall(r"[\w\-./\\:]+\.tf", errors))
    selected = sorted(f for f in tfs if f in hits) or list(tfs)
    bundle = "".join(
        f"\n=== {name} ===\n{open(os.path.join(TFDIR, name)).read()}"
        for name in selected)

    prompt = """Return a JSON object only: no markdown fences, no explanations, no commentary.
The Terraform root module below fails `terraform validate`. Fix every error and return a JSON object mapping each corrected filename to its complete file contents, e.g. {"variables.tf": "...", "network.tf": "..."}.
Return every file listed below — corrected, or verbatim if it needs no change. Files you omit are deleted, so omit nothing.

These generation rules still apply — the repaired module must obey all of them:
""" + RULES + """

Raw `terraform validate` errors:
""" + errors.rstrip() + """

Current file contents:
""" + bundle + """
"""

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=12000,
        extra_body={"reasoning_effort": "low"},
    )

    text = resp.choices[0].message.content or ""
    m = re.search(r"```(?:terraform|hcl|json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    try:
        files = json.loads(text)
    except json.JSONDecodeError:
        print("ERROR: repair model did not return valid JSON",
              file=sys.stderr, flush=True)
        print(text[:500], file=sys.stderr, flush=True)
        sys.exit(1)
    if not isinstance(files, dict) or not files:
        print("ERROR: expected a JSON object of filename -> contents",
              file=sys.stderr, flush=True)
        sys.exit(1)
    for name, content in files.items():
        # NB: no keyword check here (unlike the generator): a valid file may
        # hold only outputs, locals, or a terraform block.
        if (not name.endswith(".tf") or not isinstance(content, str)
                or not content.strip()):
            print(f"ERROR: bad file entry {name!r}", file=sys.stderr, flush=True)
            sys.exit(1)
    missing = sorted(set(selected) - set(files))
    if missing:
        print("ERROR: model omitted shown files:"
              f" {', '.join(missing)}", file=sys.stderr, flush=True)
        sys.exit(1)

    # Wipe-then-write, scoped to the files the model was shown: files that
    # were never sent to the model are left untouched, so a repair of one
    # file can never delete the rest of the module.
    for stale in selected:
        os.remove(os.path.join(TFDIR, stale))
    for name, content in files.items():
        with open(os.path.join(TFDIR, name), "w") as f:
            f.write(content)
    print("rewrote: " + ", ".join(sorted(files)), flush=True)

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Markdownlint-clean: blank lines around headings/fences, single
    # trailing newline, clean() strips trailing spaces (MD009). Raw
    # validate lines run long, so MD013 is off.
    new_log = not os.path.exists("repair-log.md")
    with open("repair-log.md", "a") as log:
        if new_log:
            log.write("# Repair Log\n\n<!-- markdownlint-disable MD013 -->\n")
        log.write(f"\n## {stamp} — attempt {attempt}/{MAX_ATTEMPTS}"
                  f" ({TFDIR})\n\n")
        log.write("Validate errors:\n\n```text\n" + clean(errors.rstrip())
                  + "\n```\n\n")
        log.write("Files rewritten: " + ", ".join(sorted(files)) + "\n")

    line = f"usage: {resp.usage}"
    print(line, flush=True)
    m1 = re.search(r"prompt_tokens=(\d+)", line)
    m2 = re.search(r"completion_tokens=(\d+)", line)
    total_in += int(m1.group(1)) if m1 else 0
    total_out += int(m2.group(1)) if m2 else 0
    calls += 1

print(f"ERROR: still invalid after {MAX_ATTEMPTS} attempts", file=sys.stderr, flush=True)
print(errors.rstrip() or "(no output)", flush=True)
sys.exit(1)
