import json
from PIL import Image, ImageDraw

img = Image.open(sys.argv[1]).convert("RGB") if False else None
