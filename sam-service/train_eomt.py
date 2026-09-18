#!/usr/bin/env python3
"""Fine-tune an EoMT universal segmentation checkpoint on YOLO polygons."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image, ImageDraw
from torch.utils.data import DataLoader, Dataset
from transformers import AutoImageProcessor, AutoModelForUniversalSegmentation


def load_names(path: Path) -> list[str]:
    names: dict[int, str] = {}
    in_names = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line == "names:":
            in_names = True
            continue
        if in_names:
            parts = line.split(":", 1)
            if len(parts) == 2 and parts[0].strip().isdigit():
                names[int(parts[0].strip())] = parts[1].strip().strip("'\"")
            elif line and not raw_line.startswith(" "):
                break
    if not names or sorted(names) != list(range(len(names))):
        raise RuntimeError(f"data.yaml must contain contiguous names 0..N-1: {path}")
    return [names[index] for index in range(len(names))]


def image_paths(dataset_root: Path) -> list[Path]:
    split_file = dataset_root / "train.txt"
    if not split_file.exists():
        raise RuntimeError(f"Missing split file: {split_file}")
    paths: list[Path] = []
    for raw_line in split_file.read_text(encoding="utf-8").splitlines():
        value = raw_line.strip()
        if not value:
            continue
        candidate = Path(value)
        path = candidate if candidate.is_absolute() else dataset_root / value
        if not path.exists() and candidate.parts and candidate.parts[0] == "data":
            path = dataset_root.joinpath(*candidate.parts[1:])
        if not path.exists():
            raise RuntimeError(f"Image listed in train.txt does not exist: {path}")
        paths.append(path)
    if not paths:
        raise RuntimeError(f"No images listed in {split_file}")
    return paths


def label_path(dataset_root: Path, image_path: Path) -> Path:
    relative = image_path.relative_to(dataset_root)
    parts = list(relative.parts)
    if "images" not in parts:
        raise RuntimeError(f"Image path must contain an images directory: {image_path}")
    parts[parts.index("images")] = "labels"
    return dataset_root.joinpath(*parts).with_suffix(".txt")


def yolo_masks(path: Path, width: int, height: int, class_count: int) -> dict[int, np.ndarray]:
    masks: dict[int, np.ndarray] = {}
    if not path.exists():
        return masks
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        values = raw_line.split()
        if len(values) < 7 or (len(values) - 1) % 2:
            raise RuntimeError(f"Invalid polygon at {path}:{line_number}")
        class_id = int(values[0])
        if not 0 <= class_id < class_count:
            raise RuntimeError(f"Class {class_id} outside 0..{class_count - 1} at {path}:{line_number}")
        points = np.asarray([float(value) for value in values[1:]], dtype=np.float32).reshape(-1, 2)
        polygon = [(round(float(x) * width), round(float(y) * height)) for x, y in points]
        mask = Image.new("1", (width, height), 0)
        ImageDraw.Draw(mask).polygon(polygon, fill=1)
        current = np.asarray(mask, dtype=bool)
        masks[class_id] = np.logical_or(masks.get(class_id, np.zeros_like(current)), current)
    return masks


class YoloSegmentation(Dataset[dict[str, Any]]):
    def __init__(self, paths: list[Path], root: Path, processor: Any, class_count: int):
        self.paths = paths
        self.root = root
        self.processor = processor
        self.class_count = class_count
        size = processor.size
        self.target_size = (int(size.get("height", size.get("shortest_edge", 640))), int(size.get("width", size.get("shortest_edge", 640))))

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, index: int) -> dict[str, Any]:
        image_path = self.paths[index]
        image = Image.open(image_path).convert("RGB")
        masks = yolo_masks(label_path(self.root, image_path), image.width, image.height, self.class_count)
        encoded = self.processor(images=image, return_tensors="pt")
        pixel_values = encoded["pixel_values"][0]
        resized_masks = []
        class_labels = []
        for class_id, mask in sorted(masks.items()):
            resized = Image.fromarray((mask * 255).astype(np.uint8)).resize(self.target_size[::-1], Image.Resampling.NEAREST)
            resized_masks.append(torch.from_numpy(np.asarray(resized, dtype=np.float32) > 0))
            class_labels.append(class_id)
        if not resized_masks:
            resized_masks = [torch.empty((0, *self.target_size), dtype=torch.bool)]
            class_labels = [torch.empty((0,), dtype=torch.long)]
        return {
            "pixel_values": pixel_values,
            "mask_labels": torch.stack(resized_masks),
            "class_labels": torch.tensor(class_labels, dtype=torch.long),
        }


def collate(batch: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "pixel_values": torch.stack([item["pixel_values"] for item in batch]),
        "mask_labels": [item["mask_labels"] for item in batch],
        "class_labels": [item["class_labels"] for item in batch],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="Dataset directory containing data.yaml and train.txt")
    parser.add_argument("--output", type=Path, required=True, help="Directory for the fine-tuned Hugging Face checkpoint")
    parser.add_argument("--base-model", default="tue-mps/eomt-dinov3-coco-panoptic-large-640")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--val-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true", help="Validate and report the dataset without loading the model")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.epochs < 1 or args.batch_size < 1 or not 0 < args.val_fraction < 1:
        raise SystemExit("epochs, batch-size must be positive and val-fraction must be between 0 and 1")
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    root = args.dataset.resolve()
    names = load_names(root / "data.yaml")
    paths = image_paths(root)
    annotated = [path for path in paths if label_path(root, path).exists()]
    report = {"images": len(paths), "annotated_images": len(annotated), "classes": len(names), "class_names": names}
    if args.dry_run:
        print(json.dumps(report, indent=2))
        return
    if len(annotated) < 2:
        raise RuntimeError("At least two annotated images are required; run --dry-run to inspect dataset coverage")
    random.shuffle(paths)
    split = max(1, int(len(paths) * (1 - args.val_fraction)))
    train_paths, val_paths = paths[:split], paths[split:]
    processor = AutoImageProcessor.from_pretrained(args.base_model)
    id2label = {index: name for index, name in enumerate(names)}
    label2id = {name: index for index, name in id2label.items()}
    model = AutoModelForUniversalSegmentation.from_pretrained(
        args.base_model,
        num_labels=len(names),
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True,
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=0.01)
    train_loader = DataLoader(YoloSegmentation(train_paths, root, processor, len(names)), batch_size=args.batch_size, shuffle=True, collate_fn=collate)
    val_loader = DataLoader(YoloSegmentation(val_paths or train_paths[-1:], root, processor, len(names)), batch_size=args.batch_size, shuffle=False, collate_fn=collate)
    best_loss = float("inf")
    for epoch in range(args.epochs):
        model.train()
        train_loss = 0.0
        for batch in train_loader:
            batch = {key: value.to(device) if isinstance(value, torch.Tensor) else [item.to(device) for item in value] for key, value in batch.items()}
            loss = model(**batch).loss
            loss.backward()
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            train_loss += float(loss.detach())
        model.eval()
        val_loss = 0.0
        with torch.inference_mode():
            for batch in val_loader:
                batch = {key: value.to(device) if isinstance(value, torch.Tensor) else [item.to(device) for item in value] for key, value in batch.items()}
                val_loss += float(model(**batch).loss)
        mean_train = train_loss / max(1, len(train_loader))
        mean_val = val_loss / max(1, len(val_loader))
        print(f"epoch={epoch + 1}/{args.epochs} train_loss={mean_train:.5f} val_loss={mean_val:.5f}")
        if mean_val < best_loss:
            best_loss = mean_val
            args.output.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(args.output)
            processor.save_pretrained(args.output)
            (args.output / "dataset_manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()