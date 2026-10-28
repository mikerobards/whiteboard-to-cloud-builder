import numpy as np
import torch
from PIL import Image
from transformers import Sam3Model, Sam3Processor

IMAGE = "./images/GCP-1-clean.jpeg"
# One box only, to test speed first: Cloud Storage bucket, in pixels
BOXES = [
    [83, 3, 442, 118],      # Users
    [26, 166, 1190, 838],   # GCP project
    [83, 270, 442, 384],    # Cloud Run
    [500, 251, 1154, 598],  # VPC
    [531, 328, 1117, 418],  # Firewall
    [531, 465, 1117, 575],  # VM
    [410, 704, 813, 790],   # Bucket
]
LABELS = [[1, 1, 1, 1, 1, 1, 1]]


image = Image.open(IMAGE).convert("RGB")
print("loading model...")
model = Sam3Model.from_pretrained("unsloth/sam3.1", dtype=torch.float32)
processor = Sam3Processor.from_pretrained("unsloth/sam3.1")
model.eval()

inputs = processor(
    images=image,
    input_boxes=[BOXES],
    input_boxes_labels=LABELS,
    return_tensors="pt",
)
with torch.no_grad():
    outputs = model(**inputs)

results = processor.post_process_instance_segmentation(
    outputs, threshold=0.5, mask_threshold=0.5,
    target_sizes=inputs["original_sizes"].tolist(),
)[0]

print(f"masks: {len(results['masks'])}")
print("scores:", results["scores"].tolist())
print("boxes:", results["boxes"].tolist())

print("masks shape:", results["masks"].shape)
for i, m in enumerate(results["masks"]):
    ys, xs = (m > 0).nonzero(as_tuple=True)
    if len(xs):
        print(
            f"mask {i}: x {int(xs.min())}-{int(xs.max())}, y {int(ys.min())}-{int(ys.max())}, pixels {int((m > 0).sum())}")
    else:
        print(f"mask {i}: empty")


masks = results["masks"].cpu().numpy()
h, w = masks.shape[1], masks.shape[2]
canvas = np.ones((h, w, 3), dtype=np.uint8) * 255
colors = [(255, 0, 0), (0, 180, 0), (0, 0, 255), (255, 165, 0)]
for i, m in enumerate(masks):
    canvas[m] = colors[i % len(colors)]
Image.fromarray(canvas).save("masks_only.png")
print("saved masks_only.png")
