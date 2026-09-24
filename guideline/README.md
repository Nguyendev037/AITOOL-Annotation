# Guideline cho annotation

Thư mục `guildlline/` giữ tài liệu gốc chính thức dạng PDF. Thư mục `guideline/` giữ bản Markdown đã chuẩn hóa để pipeline đọc nhanh và nhất quán.

Sơ đồ kiến trúc nằm tại [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

## Tài liệu hiện có

| File | Mô tả |
|---|---|
| `guildlline/Annotation_Guideline_BBox_Polygon_Polyline.pdf` | Guideline gốc cho BBox / Polygon / Polyline |
| `guildlline/Semantic_Segmentation_Annotation_Guideline.pdf` | Guideline gốc cho Semantic Segmentation |
| `guideline/bbox_polygon_polyline.md` | Bản chuẩn hóa cho BBox / Polygon / Polyline |
| `guideline/semantic_segmentation.md` | Bản chuẩn hóa cho semantic segmentation |
| `guideline/segmentation-model-for-cvat.md` | Phân tích lựa chọn model segmentation cho CVAT |

## Taxonomy đầy đủ (theo 2 PDF gốc)

> ⚠️ **Bản máy đọc nằm ở [`../taxonomy.yaml`](../taxonomy.yaml).** Các mục dưới
> đây là bản diễn giải cho người đọc; `taxonomy.yaml` mới là thứ code,
> nuclio function và CVAT thực sự đọc. Khi taxonomy thay đổi, **sửa
> `taxonomy.yaml`** rồi chạy:
>
> ```powershell
> python tools/sync_taxonomy.py --write   # sinh lại mọi artifact
> python tools/sync_taxonomy.py --check   # xác nhận không còn lệch
> ```
>
> Quy trình đầy đủ (kèm bước rebuild/redeploy): [../nuclio/README.md](../nuclio/README.md) mục 6b.

### Nhóm 1 — Object instance (Rectangle / Bounding Box)

`pedestrian`, `rider`, `car`, `truck`, `bus`, `train`, `motorcycle`, `bicycle`, `traffic light`, `traffic sign`

### Nhóm 2 — Drivable area (Polygon)

`area/drivable`, `area/alternative`

### Nhóm 3 — Lane marking (Polyline)

`lane/crosswalk`, `lane/double white`, `lane/double yellow`, `lane/road curb`, `lane/single other`, `lane/single white`, `lane/single yellow`

> **Trạng thái inference:** drivable area được **xấp xỉ** từ `road` → `area/drivable` và `pavement-merged` → `area/alternative` (EoMT COCO-panoptic). Lane marking **đã có model riêng** — `smart-lane` chạy detector classical CV trên CPU (không tốn VRAM), trace được `lane/single white|yellow|other` ở ~40% dưới khung hình; `lane/double *`, `lane/crosswalk` và `lane/road curb` chưa đáng tin — xem `nuclio/README.md` mục 7.

### Nhóm 4 — Semantic segmentation (19 class)

`road`, `sidewalk`, `building`, `wall`, `fence`, `pole`, `traffic_light`, `traffic_sign`, `vegetation`, `terrain`, `sky`, `person`, `rider`, `car`, `truck`, `bus`, `train`, `motorcycle`, `bicycle`

## Mapping COCO → guideline (dùng bởi `/detect`)

Model YOLO26 map COCO → guideline. Chỉ giữ các class object được guideline cho phép, còn lại bị lọc bỏ:

| COCO | Guideline |
|---|---|
| person | pedestrian |
| bicycle | bicycle |
| car | car |
| motorcycle | motorcycle |
| bus | bus |
| train | train |
| truck | truck |
| traffic light | traffic light |
| stop sign | traffic sign |

**Giới hạn đã biết:**

- `rider` chưa phân biệt được với `person` (COCO `person` không có thuộc tính "đang cưỡi").
- `traffic sign` chỉ phủ được `stop sign`; các loại biển báo khác chưa được model pretrained nhận diện.

> Lưu ý: lệnh đồng bộ `python -m app.main --sync-guidelines` thuộc kiến trúc cũ đã bị gỡ bỏ. Khi cần chuẩn hóa guideline mới, tạo Markdown thủ công từ PDF gốc trong `guildlline/`, rồi cập nhật `taxonomy.yaml` và chạy `python tools/sync_taxonomy.py --write`.

## Luật số của agent — `rules/week2-rules.json`

Ngưỡng annotation (ví dụ "mắt ≥ 4/8 điểm") **không nằm trong code** mà nằm trong
[`../rules/week2-rules.json`](../rules/week2-rules.json). Sửa file đó là hành vi agent
đổi ngay — không cần sửa Python.

Bộ kiểm tra đọc ngưỡng **thẳng từ bảng trong tài liệu nguồn `.docx`** và so với luật
đang dùng, nên không thể lệch âm thầm:

```powershell
python tools/check_rules.py            # in luật đang dùng + nguồn ghi gì
python tools/check_rules.py --check    # thoát khác 0 nếu lệch (dùng trong CI)
```

Vì sao đối chiếu với `.docx` nguồn chứ không phải bản Markdown sinh ra: bước sinh
Markdown (`tools/sync_guidelines.py`) cần `DEEPSEEK_API_KEY` và **hiện không chạy được**
vì `.env` thiếu key. Mốc đối chiếu phải là thứ BTC phát hành.

Agent **không tự sửa** luật từ câu chữ tài liệu — guideline là văn xuôi tự do, tự suy
ra hành vi từ đó sẽ sai lặng lẽ. Agent chỉ **phát hiện** và **báo**; người chốt luật.

> `tools/gen_labels.py` là generator cũ (gọi LLM, có cả task `keypoint` không
> tồn tại trong guideline). Nó **không** được nối vào pipeline deploy và không
> còn là nguồn sự thật — dùng `tools/sync_taxonomy.py`.

<!-- BEGIN GENERATED SOURCES -->

### Tài liệu nguồn và bản trích xuất tự động

Sinh bởi `python tools/sync_all.py`. Đừng sửa tay vùng này.

| Tài liệu nguồn (`guildlline/`) | sha256 | Trạng thái | Bản trích xuất |
|---|---|---|---|
| `Annotation_Guideline_BBox_Polygon_Polyline.pdf` | `63bce09da0e8` | không đổi | [`guideline/generated/annotation-guideline-bbox-polygon-polyline.md`](guideline/generated/annotation-guideline-bbox-polygon-polyline.md) |
| `Semantic_Segmentation_Annotation_Guideline.pdf` | `8d8d1dc910b2` | không đổi | [`guideline/generated/semantic-segmentation-annotation-guideline.md`](guideline/generated/semantic-segmentation-annotation-guideline.md) |
| `Week2_Guideline_Face_Landmark_VF50_HocVien_v1.3.docx` | `ac1e0e342e2d` | không đổi | [`guideline/generated/week2-guideline-face-landmark-vf50-hocvien-v1-3.md`](guideline/generated/week2-guideline-face-landmark-vf50-hocvien-v1-3.md) |
| `Week2_Guideline_HumanPose17_HocVien_v1.1.docx` | `98b33f2abf58` | không đổi | [`guideline/generated/week2-guideline-humanpose17-hocvien-v1-1.md`](guideline/generated/week2-guideline-humanpose17-hocvien-v1-1.md) |

<!-- END GENERATED SOURCES -->
