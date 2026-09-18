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

> **Trạng thái inference (EoMT COCO-panoptic):** drivable area được **xấp xỉ** từ `road` → `area/drivable` và `pavement-merged` → `area/alternative`. Lane marking **không được sinh ra** vì COCO không có class `lane/*` — cần label polyline riêng để train.

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

> `tools/gen_labels.py` là generator cũ (gọi LLM, có cả task `keypoint` không
> tồn tại trong guideline). Nó **không** được nối vào pipeline deploy và không
> còn là nguồn sự thật — dùng `tools/sync_taxonomy.py`.
