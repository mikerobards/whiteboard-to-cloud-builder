import sys
import os
import ssl
import json
import base64
from typing import Any, cast
from PIL import Image
from openai import OpenAI
from dotenv import load_dotenv
import httpx
import truststore
load_dotenv()


IMAGE_PATH = sys.argv[1]  # e.g. /path/to/GCP-1-clean.jpeg
MODEL = sys.argv[2] if len(sys.argv) > 2 else "muse-spark-1.1"

img = Image.open(IMAGE_PATH).convert("RGB")
w, h = img.size
print(f"image size: {w}x{h}")

with open(IMAGE_PATH, "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

# Work-laptop TLS: the corporate proxy's CA lives in the Windows cert store.
_tls = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_http = httpx.Client(verify=_tls)
client = OpenAI(base_url="https://api.meta.ai/v1",
                api_key=os.environ["META_API_KEY"],
                http_client=cast(Any, _http))

prompt = """Return JSON only, no other text.
For every rectangular or oval shape in this architecture diagram, including outer containers, return:
- label: the main title text inside the shape only, ignore any other text, notes, or subtitles inside the same shape
- type: component, container, external, or connection
- parent: the label of the shape that directly contains this one, or null if no shape contains it — do not invent a container
- box: [x_min, y_min, x_max, y_max] in 0-1000 normalized coordinates, origin top-left
Do not list arrows as shapes. Do not guess Terraform resources, just the shapes you see.
Users is an oval — return it with type: external.
If a shape's label is "Direct VPC Egress" or "Private Google Access", set type: connection, never component — no Terraform for mechanisms."""

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
with open("boxes.json", "w") as f:
    f.write(text or "")
