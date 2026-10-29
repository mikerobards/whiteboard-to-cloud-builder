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
                http_client=cast(Any, _http))

prompt = """Return SVG code only: no markdown fences, no explanations, no commentary.
Generate a clean, professional architecture diagram as a single standalone SVG
(viewBox="0 0 1320 990", width 1320, height 990, white background).

Layout: reuse the shape coordinates below as-is. They are normalized 0-1000 in
both axes over the original 1320x990 sketch: place them with x_svg = x/1000*1320
and y_svg = y/1000*990. This keeps the author's own layout.

Shapes (boxes.json):
""" + json.dumps(boxes) + """

Arrows (edges.json):
""" + json.dumps(edges) + """

Rules:
- Draw every component/external shape with its exact label, centered; split the
  label onto two lines at a colon if one is present. Sans-serif, 20px.
- Containers (type "container", e.g. VPC Network): a larger rounded rectangle
  behind its children (nest via each child's parent field), light blue fill
  (#E8F0FE), blue border (#4285F4), label top-left inside the container.
- Components (type "component"): white fill, dark border (#202124).
- External actors (type "external", e.g. USERS (HTTPS)): draw as an ellipse.
- Connection-type shapes (Direct VPC Egress, Private Google Access) are NOT
  boxes: render each as a small text label at the midpoint of its edge's arrow.
- Arrows: lines from the edge of the source shape to the edge of the target
  shape, with arrowheads via an SVG marker. Label each arrow with its mechanism
  text at the midpoint; no label when mechanism is null.
- Palette: GCP accents — blue #4285F4, green #34A853, gray #5F6368. Clean
  straight lines only, no hand-drawn styling.
- Title at top: "Whiteboard-to-Cloud - Generated Architecture", 28px sans-serif,
  gray #5F6368.
"""

resp = client.chat.completions.create(
    model=MODEL,
    messages=[{"role": "user", "content": prompt}],
    temperature=0,
    max_tokens=8000,
    extra_body={"reasoning_effort": "low"},
)

text = resp.choices[0].message.content or ""
m = re.search(r"```(?:svg|xml)?\s*(.*?)```", text, re.S)
if m:
    text = m.group(1)
if "<svg" in text:
    text = text[text.index("<svg"):]
print(text[:500], "..." if len(text) > 500 else "")
print("usage:", resp.usage)
with open("diagram.svg", "w") as f:
    f.write(text)
