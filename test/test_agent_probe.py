"""Test cho `tools/agent_probe.py` dựa trên schema THẬT đọc từ CVAT localhost.

Vì sao cần: lần đầu chạy probe, nó dò label skeleton tên ``person`` nên không bao
giờ đối chiếu được HumanPose-17, và với bài mặt nó dò 7 label nhóm nên im lặng bỏ
qua. Cả hai đều là "xanh giả" — công cụ báo ổn trong khi chưa hề kiểm tra gì.

Payload dưới đây chép nguyên từ `GET /api/labels?project_id=3` của CVAT localhost
(project `pose_data`), chỉ rút gọn các trường không dùng.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from agent_probe import check_skeleton_schema, describe_pose_schema  # noqa: E402
from browser_agent.geometry import (  # noqa: E402
    POSE17_LABEL_CANDIDATES,
    POSE17_SKELETON,
    POSE17_SUBLABEL_COUNT,
)


def _skeleton(name: str, sublabels: list[str], *, first_id: int = 1) -> dict:
    return {
        "id": 437,
        "name": name,
        "type": "skeleton",
        "svg": "<polyline points='0,0 1,1'>",
        "sublabels": [
            {"id": first_id + offset, "name": sub, "attributes": []}
            for offset, sub in enumerate(sublabels)
        ],
    }


#: Chép từ CVAT localhost: label `body` có đúng 17 sublabel tên "1".."17".
REAL_BODY = _skeleton("body", [str(i) for i in range(1, 18)], first_id=438)
#: Chép từ CVAT localhost: label `person` có 17 sublabel nhưng tên giải phẫu.
REAL_PERSON = _skeleton(
    "person",
    [
        "nose", "left_eye", "right_eye", "left_ear", "right_ear",
        "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
        "left_wrist", "right_wrist", "left_hip", "right_hip",
        "left_knee", "right_knee", "left_ankle", "right_ankle",
    ],
    first_id=27,
)
#: Chép từ CVAT localhost: label `face` có 68 sublabel "1".."68" (KHÔNG phải VF-50).
REAL_FACE_68 = _skeleton("face", [str(i) for i in range(1, 69)], first_id=463)


def test_pose17_entry_point_is_a_candidate_and_is_called_body():
    """Entry point thật trên CVAT là `body`; `person` là bài 17 điểm kiểu khác."""
    assert POSE17_SKELETON.label_name == "body"
    assert POSE17_SKELETON.label_name in POSE17_LABEL_CANDIDATES
    assert POSE17_SUBLABEL_COUNT == 17


def test_real_body_schema_passes():
    problems = check_skeleton_schema(
        REAL_BODY, expected={str(pid): pid for pid in POSE17_SKELETON.point_ids}
    )
    assert problems == []


def test_real_person_schema_is_reported_as_mismatch_not_silently_accepted():
    """`person` đủ 17 sublabel nhưng sai tên -> phải báo LỆCH, không được coi là khớp."""
    problems = check_skeleton_schema(
        REAL_PERSON, expected={str(pid): pid for pid in POSE17_SKELETON.point_ids}
    )
    assert problems, "schema `person` phải bị báo lệch vì sublabel không phải '1'..'17'"


def test_real_face_68_schema_does_not_look_like_vf50():
    """Bài mặt trên CVAT có 68 sublabel: VF-50 (0..49) không được nhận vơ là khớp."""
    problems = check_skeleton_schema(
        REAL_FACE_68, expected={str(pid): pid for pid in range(50)}
    )
    assert problems
    assert any("thiếu sublabel" in p for p in problems)


def test_describe_pose_schema_picks_body_and_says_why_when_absent():
    ok = describe_pose_schema([REAL_PERSON, REAL_BODY])
    assert "`body`" in ok
    assert "KHỚP" in ok

    missing = describe_pose_schema([REAL_FACE_68])
    assert "KHÔNG" in missing
    assert "'body'" in missing and "'person'" in missing
