import json
import os
import re
import ssl
import sys
from typing import Any, cast
from dotenv import load_dotenv
from openai import OpenAI
import httpx
import truststore

load_dotenv()  # reads META_API_KEY from .env in the project root
# Never paste the key into this file. Keep it in .env only (gitignored).

TF_DIR = sys.argv[1] if len(sys.argv) > 1 else "terraform"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "muse-spark-1.1"


def parse_resources(tf_dir):
    """Parse each .tf file in tf_dir, one summary line per resource block.

    Returns list[str] like "TYPE.NAME (k=v, ...)" or
    "TYPE.NAME (no charge attributes)" when no sizing keys are found.
    Pure: no API calls, no writes.
    """
    sizing_keys = {
        "machine_type",
        "image",
        "source_image",
        "size",
        "disk_size_gb",
        "disk_type",
        "storage_class",
        "ingress",
        "tier",
        "database_version",
        "node_count",
        "memory",
        "memory_size_gb",
        "cpu",
        "max_instances",
        "min_instances",
    }
    try:
        files = sorted(f for f in os.listdir(tf_dir) if f.endswith(".tf"))
    except FileNotFoundError:
        return []
    resources = []
    for fname in files:
        with open(os.path.join(tf_dir, fname)) as f:
            content = f.read()
        matches = list(
            re.finditer(r'resource\s+"([^"]+)"\s+"([^"]+)"', content)
        )
        for i, m in enumerate(matches):
            rtype, rname = m.group(1), m.group(2)
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            block = content[start:end]
            attrs = []
            seen = set()
            for am in re.finditer(
                r'(\w+)\s*=\s*(?:"([^"]+)"|([A-Za-z0-9_.\-]+))', block
            ):
                key = am.group(1)
                if key in sizing_keys and key not in seen:
                    val = am.group(2) if am.group(2) is not None else am.group(3)
                    attrs.append(f"{key}={val}")
                    seen.add(key)
            if attrs:
                resources.append(f"{rtype}.{rname} ({', '.join(attrs)})")
            else:
                resources.append(f"{rtype}.{rname} (no charge attributes)")
    return resources


def validate_cost(data, expected_resource_keys):
    """Validate decoded cost JSON against expected TYPE.NAME keys.

    Checks: required top-level and per-resource keys present, every
    expected resource present in data["resources"], total_monthly_usd
    equals the sum of monthly_usd within 0.01. Raises ValueError.
    Pure: no API calls, no writes.
    """
    if not isinstance(data, dict):
        raise ValueError("cost output must be a JSON object")
    for key in ("currency", "assumptions", "resources",
                "total_monthly_usd", "disclaimer"):
        if key not in data:
            raise ValueError(f"missing required key: {key}")
    resources = data["resources"]
    if not isinstance(resources, list):
        raise ValueError("resources must be a list")
    expected = set()
    for exp in expected_resource_keys:
        key = exp.split()[0] if exp.split() else exp
        if "(" in key:
            key = key[:key.index("(")].strip()
        expected.add(key.strip())
    seen = set()
    total = 0.0
    for r in resources:
        if not isinstance(r, dict):
            raise ValueError("resource entry must be an object")
        for key in ("type", "name", "monthly_usd", "confidence", "note"):
            if key not in r:
                raise ValueError(f"resource missing required key: {key}")
        try:
            monthly = float(r["monthly_usd"])
        except (TypeError, ValueError):
            raise ValueError(f"monthly_usd must be a number: {r!r}")
        rkey = f"{r['type']}.{r['name']}"
        if rkey not in expected:
            raise ValueError(f"unexpected resource: {rkey}")
        if rkey in seen:
            raise ValueError(f"duplicate resource: {rkey}")
        total += monthly
        seen.add(rkey)
    for key in expected:
        if key not in seen:
            raise ValueError(f"missing expected resource: {key}")
    try:
        claimed = float(data["total_monthly_usd"])
    except (TypeError, ValueError):
        raise ValueError("total_monthly_usd must be a number")
    if abs(claimed - total) > 0.01:
        raise ValueError(
            f"total_monthly_usd {claimed} != sum of resources {total:.2f}"
        )


resources = parse_resources(TF_DIR)
resource_lines = "\n".join(resources)

# Work-laptop TLS: the corporate proxy's CA lives in the Windows cert store.
_tls = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_http = httpx.Client(verify=_tls)
client = OpenAI(base_url="https://api.meta.ai/v1",
                api_key=os.environ["META_API_KEY"],
                http_client=cast(Any, _http))

prompt = """You are estimating Google Cloud monthly costs for Terraform-planned infrastructure.
This is a ROUGH ESTIMATE for planning purposes, not a quote.

Resources:
""" + resource_lines + """

Rules:
1. Estimate the monthly cost in USD for each resource. Assume 730 hours/month
   (always-on) for provisioned resources. For serverless / on-demand resources
   (Cloud Run, etc.), assume a light demo workload and state the assumption
   in the "assumptions" array.
2. Use your training knowledge of GCP list pricing; prefer us-central1.
   If you are unsure of a price, give your best estimate and mark
   confidence "low" — never hide uncertainty inside a confident number.
3. Do NOT invent resources. Estimate ONLY the resources listed above.
4. One number per resource, no ranges. Round to two decimals.
5. total_monthly_usd MUST equal the sum of the per-resource monthly_usd
   values. Show the arithmetic is consistent.
6. Coverage check: every resource in the input list MUST appear in the
   "resources" array. Resources with no charge (VPC network, firewall rule)
   are listed with monthly_usd 0.00 and note "no charge".

Return ONLY a JSON object with exactly this shape:

{
  "currency": "USD",
  "assumptions": ["<workload / region / pricing-basis assumptions>"],
  "resources": [
    {
      "type": "<terraform resource type>",
      "name": "<terraform resource name>",
      "monthly_usd": 0.00,
      "confidence": "high|medium|low",
      "note": "<one-line basis, e.g. 'e2-medium @ ~$24.27/mo us-central1'>"
    }
  ],
  "total_monthly_usd": 0.00,
  "disclaimer": "Rough estimate from training-data pricing, not a quote. Verify with the GCP Pricing Calculator."
}
"""

resp = client.chat.completions.create(
    model=MODEL,
    messages=[{"role": "user", "content": prompt}],
    temperature=0,
    max_tokens=4000,
    extra_body={"reasoning_effort": "low"},
)

text = resp.choices[0].message.content or ""
m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
if m:
    text = m.group(1)
if "{" in text:
    text = text[text.index("{"):]
    if "}" in text:
        text = text[:text.rindex("}") + 1]

try:
    data = json.loads(text)
    expected_keys = [line.split()[0] for line in resources if line.split()]
    validate_cost(data, expected_keys)
except (json.JSONDecodeError, ValueError) as e:
    print(f"ERROR: bad model output: {e}", file=sys.stderr)
    sys.exit(1)

with open("cost.json", "w") as f:
    json.dump(data, f, indent=2)
print("usage:", resp.usage)
