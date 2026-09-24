#!/usr/bin/env python3
"""Kiểm tra luật số của Week 2 có khớp tài liệu guideline hay không.

    python tools/check_rules.py            # in luật đang dùng
    python tools/check_rules.py --check    # thoát khác 0 nếu lệch

Vì sao có lệnh này
------------------
Ngưỡng cả-skeleton giờ là dữ liệu (`rules/week2-rules.json`), không còn nằm cứng
trong code. Nhưng dữ liệu chỉ hữu ích nếu phát hiện được lúc nó **lệch** với tài liệu
nguồn. Lệnh này so từng nhóm và chỉ rõ chỗ lệch, để dùng được trong CI:

    python tools/check_rules.py --check  ||  exit 1

Luồng tự cập nhật đầy đủ:

    python tools/sync_all.py       # tài liệu nguồn -> guideline/generated/ (+ .sync-manifest)
    python tools/check_rules.py --check   # guideline sinh ra -> luật agent đang chạy
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from browser_agent.vision.rules import (  # noqa: E402
    DEFAULT_RULES,
    FACE_GUIDELINE,
    FACE_SOURCE,
    RulesError,
    compare,
    load_rules,
    skeleton_min_points,
    thresholds_in_guideline,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="thoát khác 0 nếu luật lệch guideline")
    parser.add_argument("--rules", default=None, help="file luật khác (mặc định rules/week2-rules.json)")
    parser.add_argument("--guideline", default=None, help="file guideline khác")
    args = parser.parse_args()

    rules_path = Path(args.rules) if args.rules else None
    guide_path = Path(args.guideline) if args.guideline else None

    try:
        data = load_rules(rules_path)
        configured = skeleton_min_points(rules_path)
    except RulesError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2

    print(f"luật: {(rules_path or DEFAULT_RULES).relative_to(ROOT)} (version {data.get('version')})")
    source = guide_path or (FACE_SOURCE if FACE_SOURCE.is_file() else FACE_GUIDELINE)
    print(f"đối chiếu với: {source.relative_to(ROOT)}\n")

    try:
        documented = thresholds_in_guideline(guide_path)
    except RulesError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2

    print(f"{'nhóm':<14} {'luật':>7}  {'nguồn':>7}")
    for group in sorted(set(configured) | set(documented)):
        minimum, total = configured.get(group, ("-", "-"))
        doc = documented.get(group)
        doc_text = f"{doc[0]}/{doc[1]}" if doc else "—"
        print(f"{group:<14} {str(minimum) + '/' + str(total):>7}  {doc_text:>7}")

    try:
        problems = compare(rules_path, guide_path)
    except RulesError as exc:
        print(f"\nLỖI: {exc}", file=sys.stderr)
        return 2

    if problems:
        print(f"\nLỆCH {len(problems)} chỗ:")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nCách sửa: cập nhật rules/week2-rules.json cho khớp tài liệu nguồn."
        )
        return 1 if args.check else 0

    print(f"\nKHỚP: cả {len(configured)} nhóm trong luật đều đúng như tài liệu nguồn ghi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
