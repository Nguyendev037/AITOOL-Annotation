"""Profile guideline: ánh xạ label trong tài liệu -> label của model.

Vì sao tách khỏi `taxonomy.yaml`
--------------------------------
`taxonomy.yaml` là nguồn sự thật cho label và label ID đang dùng trong CVAT; nó
chỉ được người sửa. Profile là bản **đọc** tài liệu nguồn (PDF/DOCX trong
`guildlline/`) và nói: tài liệu khai label nào, model nào sinh được, shape gì,
và **dẫn chứng nằm ở đâu trong nguồn**. Profile không bao giờ ghi ngược vào
`taxonomy.yaml` — tự suy label từ văn xuôi tự do rồi ghi đè là cách phá
annotation đang có.

Luật kiểm (quan trọng nhất là luật cuối)
----------------------------------------
1. schema hợp lệ;
2. `model_label` phải có thật trong `taxonomy.yaml`, đúng task;
3. shape của profile phải khớp shape của nhóm trong taxonomy;
4. không trùng `model_label` trong cùng profile;
5. `source_sha256` phải khớp tài liệu đang có trên đĩa;
6. mỗi mục phải có `evidence` **có thật trong bản trích xuất** của tài liệu.

Luật 6 là luật đáng giá nhất: một trích dẫn bịa sẽ bị bắt ngay, nên profile
không thể "đúng" nhờ may mắn. Đây cũng là lý do kiểm tra chạy được **offline**:
bản trích xuất nằm sẵn trong `guideline/generated/`, không cần gọi LLM.

Trạng thái
----------
`applied`  — đã qua kiểm, có hiệu lực.
`pending`  — giữ chờ, kèm `reasons`. Profile mơ hồ hoặc model không hỗ trợ
             **không** tự có hiệu lực.
"""
from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = ROOT / "guideline" / "profiles"
SOURCES_DIR = ROOT / "guildlline"
GENERATED_DIR = ROOT / "guideline" / "generated"
TAXONOMY_YAML = ROOT / "taxonomy.yaml"

#: Mức hỗ trợ của model cho một label. `none` nghĩa là tài liệu có label nhưng
#: model không sinh được — phải nói thẳng thay vì im lặng bỏ qua.
SUPPORT_LEVELS = ("full", "partial", "none")

VALID_STATUS = ("applied", "pending")


class ProfileError(RuntimeError):
    """Profile sai cấu trúc."""


@dataclass
class ProfileEntry:
    document_label: str
    model_label: str
    shape: str
    support: str
    evidence: str
    note: str = ""


@dataclass
class Profile:
    task: str
    source: str
    source_sha256: str
    status: str = "pending"
    entries: list[ProfileEntry] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    generated_by: str = ""

    def as_dict(self) -> dict:
        return {
            "task": self.task,
            "source": self.source,
            "source_sha256": self.source_sha256,
            "status": self.status,
            "generated_by": self.generated_by,
            "reasons": list(self.reasons),
            "entries": [
                {
                    "document_label": e.document_label,
                    "model_label": e.model_label,
                    "shape": e.shape,
                    "support": e.support,
                    "evidence": e.evidence,
                    **({"note": e.note} if e.note else {}),
                }
                for e in self.entries
            ],
        }


# --------------------------------------------------------------------------- #
# Nguồn
# --------------------------------------------------------------------------- #
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generated_markdown(source: str) -> Path:
    """Bản trích xuất tất định của một tài liệu nguồn.

    Tên file do `tools/sync_extract.slugify` quyết định; ở đây suy lại đúng quy
    tắc đó để không phải import chéo.
    """
    stem = Path(source).stem
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return GENERATED_DIR / f"{slug}.md"


def taxonomy_index(path: Path = TAXONOMY_YAML) -> tuple[dict[tuple[str, str], dict], dict[str, str]]:
    """((task, label) -> thông tin nhóm, task -> shape) đọc từ `taxonomy.yaml`.

    Khoá là **cặp (task, label)**, không phải chỉ `label`. Tên label trùng nhau
    giữa các nhóm là chuyện thật và hợp lệ: `rider`/`car`/`bus`/`train`/
    `motorcycle`/`bicycle` có ở cả `objects` (bbox) lẫn `semantic`, và các điểm
    `1`..`17` có ở cả `pose17` lẫn `face50`. Một map khoá theo tên sẽ để nhóm sau
    ghi đè nhóm trước — đúng lỗi đã xảy ra: bbox mất 7/10 label và pose17 mất cả 17.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    labels: dict[tuple[str, str], dict] = {}
    task_shape: dict[str, str] = {}
    for group in data.get("groups") or []:
        task = group.get("task")
        if task:
            task_shape[task] = group.get("shape") or ""
        for label in group.get("labels") or []:
            name = label.get("name")
            if name is None:
                continue
            key = (str(task or ""), str(name))
            labels[key] = {
                "group": group.get("id"),
                "task": task,
                "shape": group.get("shape"),
            }
    return labels, task_shape


# --------------------------------------------------------------------------- #
# Đọc / ghi
# --------------------------------------------------------------------------- #
def load_profile(path: Path) -> Profile:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProfileError(f"{path.name}: YAML không hợp lệ: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError(f"{path.name}: phải là mapping YAML")

    for key in ("task", "source", "source_sha256"):
        if not data.get(key):
            raise ProfileError(f"{path.name}: thiếu `{key}`")

    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ProfileError(f"{path.name}: `entries` phải là danh sách không rỗng")

    entries: list[ProfileEntry] = []
    for index, raw in enumerate(raw_entries, start=1):
        if not isinstance(raw, dict):
            raise ProfileError(f"{path.name}: entry {index} không phải mapping")
        for key in ("document_label", "model_label", "shape", "support", "evidence"):
            if not raw.get(key):
                raise ProfileError(f"{path.name}: entry {index} thiếu `{key}`")
        support = raw["support"]
        if support not in SUPPORT_LEVELS:
            raise ProfileError(
                f"{path.name}: entry {index} `support` {support!r} không thuộc {list(SUPPORT_LEVELS)}"
            )
        entries.append(
            ProfileEntry(
                document_label=str(raw["document_label"]),
                model_label=str(raw["model_label"]),
                shape=str(raw["shape"]),
                support=support,
                evidence=str(raw["evidence"]),
                note=str(raw.get("note") or ""),
            )
        )

    status = data.get("status", "pending")
    if status not in VALID_STATUS:
        raise ProfileError(f"{path.name}: `status` {status!r} không thuộc {list(VALID_STATUS)}")

    return Profile(
        task=str(data["task"]),
        source=str(data["source"]),
        source_sha256=str(data["source_sha256"]),
        status=status,
        entries=entries,
        reasons=[str(r) for r in (data.get("reasons") or [])],
        generated_by=str(data.get("generated_by") or ""),
    )


def dump_profile(profile: Profile) -> str:
    header = (
        "# SINH TỰ ĐỘNG bởi `python tools/guidelines.py generate`.\n"
        "# Đừng sửa tay: sửa `taxonomy.yaml` (label) hoặc tài liệu nguồn, rồi sinh lại.\n"
        "# `status: pending` nghĩa là CHƯA có hiệu lực — xem `reasons`.\n"
    )
    body = yaml.safe_dump(
        profile.as_dict(), allow_unicode=True, sort_keys=False, default_flow_style=False
    )
    return header + body


def load_profiles(dir_path: Path = PROFILES_DIR) -> dict[str, Profile]:
    profiles: dict[str, Profile] = {}
    for path in sorted(dir_path.glob("*.yaml")):
        profiles[path.stem] = load_profile(path)
    return profiles


# --------------------------------------------------------------------------- #
# Kiểm
# --------------------------------------------------------------------------- #
def _evidence_core(evidence: str) -> str:
    """Phần dẫn chứng phải có thật trong nguồn.

    Bỏ hai thứ do **người sinh** thêm vào, không phải chữ của nguồn:

    * chú thích trong ngoặc đơn, ví dụ
      ``| moingoai | 30 – 41 | 12 |  (điểm 38 nằm trong khoảng ...)``;
    * dấu ``…`` đánh dấu đoạn trích bị cắt hai đầu.

    Giữ lại hai thứ này khi so sẽ báo lỗi oan: dấu ``…`` không có trong tài liệu
    nguồn, nên phép so ``in`` trượt dù đoạn trích là thật.
    """
    cut = evidence.find("  (")
    core = evidence[:cut] if cut != -1 else evidence
    return core.strip().strip("…").strip()


def validate_profile(profile: Profile, *, source_text: str | None = None) -> list[str]:
    """Trả về danh sách vấn đề. Rỗng nghĩa là profile dùng được."""
    problems: list[str] = []
    labels, task_shape = taxonomy_index()

    if profile.task not in task_shape:
        problems.append(
            f"task {profile.task!r} không có trong taxonomy.yaml "
            f"(đang có: {', '.join(sorted(task_shape))})"
        )

    source_path = SOURCES_DIR / profile.source
    if not source_path.is_file():
        problems.append(f"không thấy tài liệu nguồn guildlline/{profile.source}")
    else:
        actual = sha256_file(source_path)
        if actual != profile.source_sha256:
            problems.append(
                f"source_sha256 không khớp tài liệu hiện có "
                f"(profile {profile.source_sha256[:12]}, thực tế {actual[:12]})"
            )

    expected_shape = task_shape.get(profile.task)
    seen: dict[str, str] = {}
    for entry in profile.entries:
        info = labels.get((profile.task, entry.model_label))
        if info is None:
            problems.append(
                f"`model_label` {entry.model_label!r} không có trong taxonomy.yaml "
                f"ở task {profile.task!r}"
            )
        elif expected_shape and entry.shape != expected_shape:
            problems.append(
                f"`{entry.model_label}`: shape {entry.shape!r} không khớp shape "
                f"{expected_shape!r} của task {profile.task!r}"
            )
        previous = seen.get(entry.model_label)
        if previous is not None:
            problems.append(
                f"`model_label` {entry.model_label!r} bị ánh xạ hai lần "
                f"({previous!r} và {entry.document_label!r})"
            )
        seen[entry.model_label] = entry.document_label

        # Luật đáng giá nhất: dẫn chứng phải có thật trong nguồn.
        if source_text is not None:
            core = _evidence_core(entry.evidence)
            if core not in source_text and " ".join(core.split()) not in " ".join(
                source_text.split()
            ):
                problems.append(
                    f"`{entry.document_label}`: dẫn chứng không có trong bản trích xuất "
                    f"của nguồn: {core[:70]!r}"
                )

    if profile.status == "applied" and problems:
        problems.append(
            "profile đang ở `status: applied` nhưng vẫn còn lỗi; "
            "profile lỗi không được có hiệu lực"
        )
    return problems


def read_source_text(profile: Profile) -> str | None:
    """Bản trích xuất của nguồn, nếu đã có. None khi chưa trích xuất."""
    path = generated_markdown(profile.source)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def check_all(dir_path: Path = PROFILES_DIR) -> tuple[int, list[str]]:
    """Kiểm mọi profile. Trả về (số profile đang có hiệu lực, danh sách vấn đề)."""
    problems: list[str] = []
    applied = 0
    profiles = load_profiles(dir_path)
    if not profiles:
        return 0, [f"không có profile nào trong {dir_path.relative_to(ROOT).as_posix()}"]
    for name, profile in profiles.items():
        found = validate_profile(profile, source_text=read_source_text(profile))
        for problem in found:
            problems.append(f"{name}.yaml: {problem}")
        if not found and profile.status == "applied":
            applied += 1
    return applied, problems
