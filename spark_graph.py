import base64
import json
import os
import ssl
import sys
from dotenv import load_dotenv
from openai import OpenAI
from typing import Any, cast
import httpx
import truststore

load_dotenv()  # reads META_API_KEY from .env in the project root
# Never paste the key into this file. Keep it in .env only (gitignored).

IMAGE_PATH = sys.argv[1]                      # e.g. ./images/GCP-1.jpg
BOXES_PATH = sys.argv[2] if len(sys.argv) > 2 else "boxes.json"
MODEL = sys.argv[3] if len(sys.argv) > 3 else "muse-spark-1.1"

with open(IMAGE_PATH, "rb") as f:
    b64 = base64.b64encode(f.read()).decode()
boxes = json.load(open(BOXES_PATH))

# Work-laptop TLS: the corporate proxy's CA lives in the Windows cert store.
# truststore hands that store directly to httpx's TLS context.
_tls = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_http = httpx.Client(verify=_tls)
client = OpenAI(base_url="https://api.meta.ai/v1",
                api_key=os.environ["META_API_KEY"],
                http_client=cast(Any, _http))

prompt = """Return JSON only, no other text.
You are given an architecture diagram photo and the list of shapes already detected in it.
Return every arrow in the diagram, in left-to-right order, as:
{"edges": [{"source": "<label exactly as in the shapes list>", "target": "<label exactly as in the shapes list>", "mechanism": "<text written on or beside the arrow, or null>"}]}
Rules:
- Use only labels from the shapes list for source and target.
- Shapes with type "connection" (Direct VPC Egress, Private Google Access) are mechanisms, not source or target components: put them in "mechanism" on the edge they sit on.
- Do not invent arrows, do not list shapes, do not guess Terraform resources.
Shapes:
""" + json.dumps(boxes)

resp = client.chat.completions.create(
    model=MODEL,
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {
                "url": f"data:image/jpeg;base64,{b64}"}},
        ],
    }],
    temperature=0,
    max_tokens=3000,
    extra_body={"reasoning_effort": "low"},
)

text = resp.choices[0].message.content
print(text)
print("usage:", resp.usage)
with open("edges.json", "w") as f:
    f.write(text or "")
