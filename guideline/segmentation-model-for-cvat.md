As of September 2026, there are a few strong pretrained panoptic-segmentation choices that are especially relevant for **CVAT pre-labeling**. The best model on paper is not automatically the best one to integrate: for CVAT, I care about mask quality, inference speed, pretrained availability, dependency cleanliness, and how easily `segments_info + mask` can be converted into CVAT annotations.

My shortlist would be:

| Model               |    Year |         COCO panoptic | Pretrained | Integration | Best use                               |
| ------------------- | ------: | --------------------: | ---------- | ----------- | -------------------------------------- |
| **EoMT-DINOv3**     | 2025/26 |     up to **58.9 PQ** | ✅ HF       | ⭐⭐⭐⭐⭐       | **Best overall for CVAT**              |
| **PMT-DINOv3**      |    2026 | strong, close to EoMT | ✅ HF       | ⭐⭐⭐⭐½       | Newest / frozen encoder                |
| **MaskDINO Swin-L** |    2023 |           **58.3 PQ** | ✅          | ⭐⭐⭐⭐        | Mature high-accuracy baseline          |
| **OneFormer**       |    2023 |          ~**58.0 PQ** | ✅ HF       | ⭐⭐⭐⭐⭐       | Easiest universal segmentation         |
| **OMG-Seg**         |    2024 |             universal | ✅          | ⭐⭐⭐         | Open-vocab/image/video experimentation |
| **EOV-Seg**         |    2025 |            open-vocab | ✅          | ⭐⭐⭐         | Custom classes not in COCO             |

For your use case, I would start with **EoMT-DINOv3**.

---

# 1. EoMT-DINOv3 — my first choice

The model is:

**Encoder-only Mask Transformer — EoMT**

Paper:

**Your ViT is Secretly an Image Segmentation Model — CVPR 2025 Highlight**

The authors subsequently added **DINOv3 backbones**, and current pretrained models support:

* semantic segmentation
* instance segmentation
* panoptic segmentation

The official repo reports up to **58.9 PQ on COCO** with EoMT-L at 1280×1280. EoMT is intentionally much simpler than Mask2Former-style decoder-heavy architectures and the paper reports up to roughly 4× speed improvements in some comparable settings. ([GitHub][1])

Official repo:

[EoMT GitHub](https://github.com/tue-mps/eomt?utm_source=chatgpt.com)

### Exact checkpoint I'd test

For highest-quality annotation:

```text
tue-mps/eomt-dinov3-coco-panoptic-large-1280
```

Hugging Face provides the pretrained checkpoint directly. It uses:

```text
DINOv3 ViT-L/16
1280 × 1280
COCO Panoptic
~0.3B parameters
```

([Hugging Face][2])

For faster CVAT labeling:

```text
tue-mps/eomt-dinov3-coco-panoptic-large-640
```

([Hugging Face][3])

And if memory is limited:

```text
tue-mps/eomt-dinov3-coco-panoptic-base-640
```

The especially nice part is that recent Hugging Face Transformers directly supports EoMT-DINOv3:

```python
from transformers import (
    AutoImageProcessor,
    AutoModelForUniversalSegmentation,
)

model_id = "tue-mps/eomt-dinov3-coco-panoptic-large-640"

processor = AutoImageProcessor.from_pretrained(model_id)
model = AutoModelForUniversalSegmentation.from_pretrained(
    model_id,
    device_map="auto",
)

inputs = processor(images=image, return_tensors="pt").to(model.device)

outputs = model(**inputs)

result = processor.post_process_panoptic_segmentation(
    outputs,
    target_sizes=[image.size[::-1]],
)[0]
```

The result already has exactly the two things your CVAT adapter wants:

```python
result["segmentation"]
result["segments_info"]
```

Hugging Face documents this panoptic post-processing path directly. ([GitHub][4])

That significantly reduces integration complexity.

---

# 2. PMT-DINOv3 — newest model I'd experiment with

There's now a newer successor from the same group:

**PMT — Plain Mask Transformer for Image and Video Segmentation with Frozen Vision Encoders**

CVPR Workshops 2026.

[PMT official GitHub](https://github.com/tue-mps/pmt?utm_source=chatgpt.com)

The interesting change is:

```text
EoMT

DINO encoder
    ↓
fine-tuned for segmentation


PMT

DINOv3 encoder
    ↓
FROZEN
    ↓
small Plain Mask Decoder
```

The authors report that PMT matches strong frozen-encoder segmentation methods while being substantially faster, and the same architecture extends to image and video segmentation. ([CVF Open Access][5])

There are already pretrained HF models:

```text
tue-mps/coco_panoptic_pmt_large_1280_dinov3
```

([Hugging Face][6])

and:

```text
tue-mps/coco_panoptic_pmt_large_640_dinov3
tue-mps/coco_panoptic_pmt_base_640_dinov3
tue-mps/coco_panoptic_pmt_small_640_dinov3
```

The base 640 checkpoint is explicitly available as a pretrained COCO panoptic model. ([Hugging Face][7])

### Why PMT is interesting for you

If later you want to fine-tune on your own dataset, the frozen DINOv3 encoder is attractive:

```text
DINOv3
  │
  │ frozen
  ▼
PMT decoder
  │
  ▼
your segmentation classes
```

Instead of having to optimize the entire foundation model.

However, because PMT is much newer and less battle-tested, I'd use **EoMT as production baseline first** and PMT as experiment #2.

---

# 3. MaskDINO — mature accuracy baseline

MaskDINO remains extremely strong.

**Mask DINO: Towards a Unified Transformer-based Framework for Object Detection and Segmentation — CVPR 2023**

Official repository:

[MaskDINO GitHub](https://github.com/IDEA-Research/MaskDINO?utm_source=chatgpt.com)

Available Swin-L checkpoint:

```text
COCO panoptic
PQ       58.3
Mask AP  50.6
Box AP   56.2
mIoU     67.5
```

([GitHub][8])

It handles:

```text
object detection
        +
instance segmentation
        +
semantic segmentation
        =
panoptic segmentation
```

### Advantage

Very mature and extensively studied.

### Disadvantage for your CVAT setup

The dependency stack is more annoying than EoMT:

```text
Detectron2
MaskDINO
specific Torch versions
Swin dependencies
custom configs
```

For your `cvat-model-integrator` Skill, I'd probably deploy this using the **sidecar-model + thin Nuclio adapter** architecture rather than put the entire MaskDINO environment inside the Nuclio function.

---

# 4. OneFormer — easiest universal model

If you want something that is extremely convenient to prototype, don't overlook **OneFormer**.

It uses the same model for:

```text
semantic
instance
panoptic
```

You simply specify the desired task.

Official COCO results include:

```text
Swin-L      57.9 PQ
DiNAT-L     58.0 PQ
```

([GitHub][9])

And Hugging Face has:

```text
shi-labs/oneformer_coco_swin_large
```

which directly supports all three segmentation modes. ([Hugging Face][10])

Inference is almost trivial:

```python
from transformers import (
    OneFormerProcessor,
    OneFormerForUniversalSegmentation,
)

model_id = "shi-labs/oneformer_coco_swin_large"

processor = OneFormerProcessor.from_pretrained(model_id)
model = OneFormerForUniversalSegmentation.from_pretrained(model_id)

inputs = processor(
    images=image,
    task_inputs=["panoptic"],
    return_tensors="pt",
)
```

([Hugging Face][11])

If EoMT gives you dependency trouble, **OneFormer is a very good fallback**.

---

# 5. OMG-Seg — interesting if you want much more than panoptic

**OMG-Seg — CVPR 2024** is unusual because it tries to unify more than ten segmentation tasks:

```text
semantic
instance
panoptic

image segmentation
video segmentation

open vocabulary

interactive segmentation

video object segmentation
```

([GitHub][12])

This becomes interesting if your CVAT setup eventually wants:

```text
automatic annotation
+
interactive annotation
+
video annotation
+
open-vocabulary segmentation
```

from one general family.

However, its stack is heavier:

```text
PyTorch
MMCV
MMEngine
MMDetection
MMSegmentation
OpenCLIP
...
```

and the official install currently pins several OpenMMLab versions. ([GitHub][13])

So I wouldn't make it the **first** CVAT model.

---

# 6. What if your classes aren't COCO classes?

This is the biggest limitation of the models above.

A COCO model knows classes like:

```text
person
car
chair
cup
dog
road-ish/stuff classes
...
```

It doesn't automatically know arbitrary labels such as:

```text
driver_arm
steering_wheel
instrument_cluster
seat_belt
gear_shifter
phone_in_hand
dashboard
air_vent
...
```

For that case you have two routes.

### Route A — fine-tune EoMT / PMT

This is what I'd prefer if you have a stable taxonomy.

```text
COCO-pretrained EoMT
          │
          ▼
your labeled CVAT data
          │
          ▼
fine-tune
          │
          ▼
custom panoptic model
```

The EoMT repo explicitly supports fine-tuning while skipping/replacing the classification head for a different label set. ([GitHub][1])

### Route B — open-vocabulary panoptic model

One recent model is:

**EOV-Seg — Efficient Open-Vocabulary Panoptic Segmentation — AAAI 2025**

It has released checkpoints and supports arbitrary vocabulary classes. ([GitHub][14])

Its closed-set-style PQ numbers aren't directly competitive with EoMT/MaskDINO because the task is harder—it's solving **open-vocabulary** segmentation.

I would consider it if your labels keep changing.

---

# How I'd integrate EoMT into CVAT

CVAT doesn't need to understand “panoptic segmentation” as a special UI object.

Convert the panoptic output:

```text
EoMT

segmentation:
H × W integer map

segments_info:
[
  {
    id,
    label_id,
    score,
    ...
  }
]
```

into:

```text
                    CVAT

THING classes
person #1 ─────────── mask
person #2 ─────────── mask
car #1 ────────────── mask
car #2 ────────────── mask

STUFF classes
road ───────────────── mask
sky ────────────────── mask
grass ──────────────── mask
```

That is exactly compatible with CVAT's mask annotations.

CVAT's Segmentation Mask format is explicitly designed to represent semantic, instance **and panoptic segmentation**, producing both merged class masks and instance masks. ([CVAT Documentation][15])

For automatic annotation, CVAT detector functions can populate annotations across an entire task, and the UI allows mapping model labels to task labels. ([CVAT Documentation][16])

---

## Important: return masks, not polygons

For panoptic pre-labeling I'd configure the adapter to return:

```text
RLE masks
```

rather than polygons.

Because you recently encountered exactly the problematic case:

```text
person
███

 occluder

███
```

One instance can contain **disconnected visible components**.

A CVAT mask can preserve that naturally.

A polygon cannot.

Therefore I would explicitly leave:

> **Return masks as polygons = OFF**

when using the model.

CVAT supports either masks or converted polygons for automatic annotation, but masks are the more faithful representation here. ([CVAT Documentation][16])

---

# My recommended benchmark

Given the CVAT model-integration Skill we just built, I'd run a small bake-off rather than choose purely from COCO PQ:

```text
                  200 representative images
                            │
             ┌──────────────┼──────────────┐
             ▼              ▼              ▼
        EoMT-DINOv3      PMT-DINOv3     OneFormer
         Large 640        Large 640       Swin-L
             │              │              │
             └──────────────┼──────────────┘
                            ▼
                          CVAT
                            │
                            ▼
                     annotator edits
```

Measure:

| Metric                         | Why                                    |
| ------------------------------ | -------------------------------------- |
| panoptic PQ / IoU              | raw prediction quality                 |
| false-negative objects         | missing labels cost lots of human time |
| false-positive segments        | reviewer cleanup                       |
| boundary IoU                   | annotation edge quality                |
| instance split errors          | one person → 2 masks                   |
| instance merge errors          | two people → 1 mask                    |
| class errors                   | wrong semantics                        |
| seconds/image after correction | **most important**                     |
| GPU memory                     | deployment practicality                |
| inference sec/image            | annotation throughput                  |

The last-but-one isn't academic, but it's actually the most valuable metric for your problem:

> **How many seconds does an annotator need to turn the model output into approved ground truth?**

A 1-PQ difference is irrelevant if one model cuts correction time from 45 seconds to 15 seconds.

---

# What I would install first

For your local GitHub-cloned CVAT:

### Accuracy-oriented

```text
tue-mps/eomt-dinov3-coco-panoptic-large-1280
```

### Better speed/quality balance

```text
tue-mps/eomt-dinov3-coco-panoptic-large-640
```

### Lower VRAM

```text
tue-mps/eomt-dinov3-coco-panoptic-base-640
```

Then compare it against:

```text
tue-mps/coco_panoptic_pmt_large_640_dinov3
```

I would **not start with MaskDINO anymore** unless EoMT performs poorly on your domain. EoMT-DINOv3 is newer, has strong panoptic performance, has clean Hugging Face inference support, and is substantially easier to wrap behind your CVAT Nuclio adapter. ([GitHub][1])

If your segmentation data is actually the **in-cabin automotive data** we were discussing earlier, tell me your intended class list. That changes the recommendation significantly: I'd compare **COCO EoMT vs ADE/Cityscapes-like checkpoints vs an open-vocabulary model**, and potentially design a more useful **EoMT + SAM2 correction pipeline** rather than expecting a generic COCO panoptic checkpoint to know all cabin components.

[1]: https://github.com/tue-mps/EoMT "GitHub - tue-mps/eomt: [CVPR 2025 Highlight] Official code and models for Encoder-only Mask Transformer (EoMT). · GitHub"
[2]: https://huggingface.co/tue-mps/eomt-dinov3-coco-panoptic-large-1280?utm_source=chatgpt.com "tue-mps/eomt-dinov3-coco-panoptic-large-1280 · Hugging Face"
[3]: https://huggingface.co/tue-mps/eomt-dinov3-coco-panoptic-large-640?utm_source=chatgpt.com "tue-mps/eomt-dinov3-coco-panoptic-large-640 · Hugging Face"
[4]: https://github.com/huggingface/transformers/blob/main/docs/source/en/model_doc/eomt_dinov3.md?utm_source=chatgpt.com "transformers/docs/source/en/model_doc/eomt_dinov3.md at main · huggingface/transformers · GitHub"
[5]: https://openaccess.thecvf.com/content/CVPR2026W/ECV/html/Cavagnero_PMT_Plain_Mask_Transformer_for_Image_and_Video_Segmentation_with_CVPRW_2026_paper.html?utm_source=chatgpt.com "CVPR 2026 Open Access Repository"
[6]: https://huggingface.co/tue-mps/coco_panoptic_pmt_large_1280_dinov3?utm_source=chatgpt.com "tue-mps/coco_panoptic_pmt_large_1280_dinov3 · Hugging Face"
[7]: https://huggingface.co/tue-mps/coco_panoptic_pmt_base_640_dinov3/blob/main/README.md?utm_source=chatgpt.com "README.md · tue-mps/coco_panoptic_pmt_base_640_dinov3 at main"
[8]: https://github.com/IDEA-Research/MaskDINO?utm_source=chatgpt.com "GitHub - IDEA-Research/MaskDINO: [CVPR 2023] Official implementation of the paper \"Mask DINO: Towards A Unified Transformer-based Framework for Object Detection and Segmentation\" · GitHub"
[9]: https://github.com/SHI-Labs/OneFormer?utm_source=chatgpt.com "GitHub - SHI-Labs/OneFormer: [CVPR 2023] OneFormer: One Transformer to Rule Universal Image Segmentation · GitHub"
[10]: https://huggingface.co/shi-labs/oneformer_coco_swin_large?utm_source=chatgpt.com "shi-labs/oneformer_coco_swin_large · Hugging Face"
[11]: https://huggingface.co/shi-labs/oneformer_coco_swin_large/blob/main/README.md?utm_source=chatgpt.com "README.md · shi-labs/oneformer_coco_swin_large at main"
[12]: https://github.com/lxtgh/omg-seg?utm_source=chatgpt.com "GitHub - lxtGH/OMG-Seg: Official Repo For OMG-LLaVA and OMG-Seg codebase [CVPR-24 and NeurIPS-24] · GitHub"
[13]: https://github.com/lxtGH/OMG-Seg/blob/main/INSTALL.md?utm_source=chatgpt.com "OMG-Seg/INSTALL.md at main · lxtGH/OMG-Seg · GitHub"
[14]: https://github.com/nhw649/EOV-Seg?utm_source=chatgpt.com "GitHub - nhw649/EOV-Seg: [AAAI 2025] Official implementation of the paper \"EOV-Seg: Efficient Open-Vocabulary Panoptic Segmentation\" · GitHub"
[15]: https://docs.cvat.ai/docs/manual/advanced/formats/format-smask/?utm_source=chatgpt.com "Segmentation Mask | CVAT"
[16]: https://docs.cvat.ai/docs/manual/advanced/automatic-annotation/?utm_source=chatgpt.com "Overview | CVAT"
