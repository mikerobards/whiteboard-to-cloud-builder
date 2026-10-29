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
                http_client=_http)

prompt = """Return a JSON object only: no markdown fences, no explanations, no commentary.
Generate a complete Terraform root module for this GCP architecture, organized as multiple files.
The JSON object maps filenames to complete file contents, e.g. {"variables.tf": "...", "network.tf": "..."}.
Organize into logical files by concern, the way a real Terraform root module is laid out:
- variables.tf: variables and the provider block
- network.tf: VPC networks, subnetworks, firewalls, peering, service networking
- compute.tf: VMs, Cloud Run services and jobs, schedulers
- storage.tf: buckets and their IAM
- data.tf: databases and caches (SQL, Redis, Spanner)
- messaging.tf: Pub/Sub topics and subscriptions
- loadbalancer.tf: load balancer expansion (NEG, backend service, URL map, proxy, forwarding rule) and Cloud Armor policies
- iam.tf: service accounts and IAM bindings
- monitoring.tf: logging sinks, monitoring, notification channels
Only create files for concerns present in the diagram \u2014 a small diagram may need only variables.tf, network.tf, and compute.tf. Every file must be complete, valid HCL; together they form one root module.

Detected shapes (boxes.json) — shapes may carry a detail field with subtitle text; use it for specs like database engines:
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
- Do not invent components, networks, firewall rules, or IAM beyond what the shapes and edges describe.
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
    print("ERROR: terraform stage did not return valid JSON", file=sys.stderr)
    print(text[:500], file=sys.stderr)
    sys.exit(1)
if not isinstance(files, dict) or not files:
    print("ERROR: expected a JSON object of filename -> contents", file=sys.stderr)
    sys.exit(1)
for name, content in files.items():
    if (not name.endswith(".tf") or not isinstance(content, str) or not content.strip()
            or ("resource" not in content and "variable" not in content and "provider" not in content)):
        print(f"ERROR: bad file entry {name!r}", file=sys.stderr)
        sys.exit(1)
outdir = "terraform"
os.makedirs(outdir, exist_ok=True)
for stale in os.listdir(outdir):
    if stale.endswith(".tf"):
        os.remove(os.path.join(outdir, stale))
for name, content in files.items():
    with open(os.path.join(outdir, name), "w") as f:
        f.write(content)
print("wrote: " + ", ".join(sorted(files)))
print("usage:", resp.usage)
