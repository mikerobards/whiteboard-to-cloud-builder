import json
import os
import re
import ssl
import sys
from dotenv import load_dotenv
from openai import OpenAI
import httpx
import truststore

load_dotenv()  # reads META_API_KEY from .env in the project root
# Never paste the key into this file. Keep it in .env only (gitignored).

BOXES_PATH = sys.argv[1] if len(sys.argv) > 1 else "boxes.json"
EDGES_PATH = sys.argv[2] if len(sys.argv) > 2 else "edges.json"
MODEL = sys.argv[3] if len(sys.argv) > 3 else "muse-spark-1.1"

boxes = json.load(open(BOXES_PATH))
edges = json.load(open(EDGES_PATH))

# Work-laptop TLS: the corporate proxy's CA lives in the Windows cert store.
_tls = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_http = httpx.Client(verify=_tls)
client = OpenAI(base_url="https://api.meta.ai/v1",
                api_key=os.environ["META_API_KEY"],
                http_client=_http)  # type: ignore[arg-type]  # Truststore-backed httpx client

prompt = """Return Terraform HCL only: no markdown fences, no explanations, no commentary.
Generate a complete root-module main.tf for this GCP architecture.

Detected shapes (boxes.json):
""" + json.dumps(boxes) + """

Detected arrows (edges.json):
""" + json.dumps(edges) + """

Component to resource mapping (fixed, use exactly these):
- "VPC Network" (container) -> google_compute_network, plus one google_compute_subnetwork inside it. The sketch says "Private Google Access (enabled on subnet)": set private_ip_google_access = true on the subnetwork.
- "Firewall Rule: Allow TCP:8080" (component, inside VPC Network) -> google_compute_firewall on that network: allow TCP port 8080, source_ranges = the subnetwork's CIDR block, target = the VM via target_tags.
- "Compute Engine VM" (component, inside VPC Network; sketch: "Backend in private subnet") -> google_compute_instance on the subnetwork with NO access_config block (no external IP), tagged to match the firewall rule. Give it a service account.
- "Cloud Run Service" (component; sketch: "Serverless FE") -> google_cloud_run_v2_service with Direct VPC Egress: a vpc_access block using network_interfaces { network, subnetwork } (not a VPC connector) and egress = "ALL_TRAFFIC". Container image: us-docker.pkg.dev/cloudrun/container/hello as a placeholder.
- "Cloud Storage Bucket" (component; sketch: "Files & static assets") -> google_storage_bucket.
- Edge "Cloud Run Service -> Cloud Storage Bucket" (direct): grant the Cloud Run service's service account roles/storage.objectViewer on the bucket via google_storage_bucket_iam_member.
- Edge "Compute Engine VM -> Cloud Storage Bucket" via Private Google Access: covered by private_ip_google_access on the subnetwork; grant the VM's service account roles/storage.objectViewer on the bucket as well.

Rules:
- Provider "google". Variables: project_id (no default), region (default "us-east1").
- One file, no modules, no count/for_each. Valid HCL that a terraform init could consume.
- Do not invent components, networks, firewall rules, or IAM beyond what the shapes and edges describe.
"""

resp = client.chat.completions.create(
    model=MODEL,
    messages=[{"role": "user", "content": prompt}],
    temperature=0,
    max_tokens=8000,
    extra_body={"reasoning_effort": "low"},
)

text = resp.choices[0].message.content or ""
m = re.search(r"```(?:terraform|hcl)?\s*(.*?)```", text, re.S)
if m:
    text = m.group(1)
print(text)
print("usage:", resp.usage)
with open("main.tf", "w") as f:
    f.write(text)
