"""Guideline agent: reads annotation guidelines and generates label schemas.

Uses DeepSeek LLM to parse guideline markdown and produce structured label
lists compatible with CVAT Nuclio function.yaml specs.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path


def read_guideline(guideline_path: Path) -> str:
    """Read guideline markdown and return its content."""
    if not guideline_path.exists():
        raise FileNotFoundError(f"Guideline not found: {guideline_path}")
    return guideline_path.read_text(encoding="utf-8")


def extract_labels_from_guideline(guideline_text: str) -> list[str]:
    """Extract label names from guideline markdown using regex patterns."""
    labels = []
    for match in re.finditer(r"^\s*\d+\.\s+\*\*(.+?)\*\*", guideline_text, re.MULTILINE):
        name = match.group(1).strip().lower().replace(" ", "_")
        if name and name not in labels:
            labels.append(name)
    if not labels:
        for match in re.finditer(r"^\s*[-*]\s+(.+?)\s*$", guideline_text, re.MULTILINE):
            name = match.group(1).strip().lower().replace(" ", "_")
            if name and name not in labels and len(name) < 40:
                labels.append(name)
    return labels


def generate_labels_with_llm(
    guideline_text: str,
    *,
    task_type: str = "semantic_segmentation",
    api_key: str = "",
    base_url: str = "https://api.deepseek.com",
    model: str = "deepseek-chat",
) -> list[dict]:
    """Use DeepSeek LLM to parse guideline and generate structured CVAT labels."""
    if not api_key:
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is required for LLM label generation")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai package is required; pip install openai") from exc

    shape_map = {
        "semantic_segmentation": "mask",
        "instance_segmentation": "polygon",
        "object_detection": "rectangle",
        "keypoint": "skeleton",
    }
    default_shape = shape_map.get(task_type, "rectangle")

    system = (
        "You are an annotation label schema generator. Given an annotation guideline document, "
        "extract ALL class/label names mentioned. Return a JSON array where each element is "
        '{"name": "label_name", "type": "' + default_shape + '"}. '
        "Label names must be lowercase with underscores instead of spaces. "
        "Return ONLY the JSON array, no other text or code fences."
    )
    client = OpenAI(api_key=api_key, base_url=base_url.rstrip("/"), timeout=60.0, max_retries=0)
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"GUIDELINE:\n\n{guideline_text}"},
        ],
    )
    content = (response.choices[0].message.content or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE).strip()
    labels = json.loads(content)
    if not isinstance(labels, list) or not labels:
        raise ValueError("LLM returned empty or invalid label list")
    return labels


def generate_nuclio_spec(labels: list[dict]) -> str:
    """Generate Nuclio function.yaml spec JSON from label list."""
    spec = []
    for i, label in enumerate(labels):
        spec.append({
            "id": i,
            "name": label["name"],
            "type": label.get("type", "mask"),
        })
    return json.dumps(spec, indent=2, ensure_ascii=False)
