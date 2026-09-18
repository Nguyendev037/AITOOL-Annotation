# Dùng model dự án trong CVAT (nuclio serverless)

Tài liệu này mô tả cách đưa **model của dự án này** lên trang **Models** của
CVAT localhost để chạy **Automatic annotation** trực tiếp trong giao diện.

> Đây là mục đích chính của dự án: annotate ảnh bằng model ngay trong CVAT,
> không cần export/import thủ công.

---

## 1. Kiến trúc

```
┌──────────────────────────────────────── CVAT localhost (http://localhost:8080)
│
│  Models page  ──►  Auto-annotation
│       │
│       │  GET  /api/functions           (header: x-nuclio-project-name: cvat)
│       │  POST /api/function_invocations
│       ▼
│  nuclio dashboard (container `nuclio`, network `cvat_cvat`, port 8070 nội bộ)
│       │
│       │  POST /  với body {"image": "<base64>", "threshold": 0.5}
│       ▼
│  nuclio function  smart-bbox | smart-semantic | smart-drivable
│       │
│       │  POST /detect | /segment-semantic | /segment-drivable
│       ▼
│  model-service (container `cvat-smart-model`, host port 8001, GPU)
│       │
│       ▼
│  YOLO26m  /  EoMT-DINOv3 COCO-panoptic  (+ SAM2 refine)
```

**Vì sao cần 3 lớp?** nuclio function chỉ là adapter CPU mỏng: nó nhận ảnh
base64 từ CVAT, gọi model-service đang giữ GPU, rồi đổi kết quả sang hình học
CVAT (`rectangle` / `polygon`). Nhờ vậy ảnh không phải đi qua GPU hai lần và
function build rất nhanh.

---

## 2. Ba function được triển khai

| Function | Nhóm guideline | Shape | Class |
| --- | --- | --- | --- |
| `smart-bbox` | Object instance | `rectangle` | 10 class: `pedestrian`, `rider`, `car`, `truck`, `bus`, `train`, `motorcycle`, `bicycle`, `traffic light`, `traffic sign` |
| `smart-semantic` | Semantic segmentation | `polygon` | 19 class Cityscapes |
| `smart-drivable` | Drivable area | `polygon` | `area/drivable`, `area/alternative` |

Mỗi function khai báo label của mình trong `metadata.annotations.spec` của file
`nuclio/functions/*.yaml`. **CVAT đọc đúng danh sách này** để hiển thị và để
map label.

> Các khối `spec`, `help_message`, `description` và `name` trong 3 file yaml đó
> **được sinh tự động** từ `taxonomy.yaml` — đừng sửa tay. Xem mục 6.

---

## 3. Triển khai

### Bước 1 — model-service phải đang chạy

```powershell
docker compose up -d model-service
curl.exe http://127.0.0.1:8001/health     # cần status: ok, device: cuda
```

### Bước 2 — sinh payload và deploy

```powershell
python tools/deploy_nuclio.py --all
powershell -ExecutionPolicy Bypass -File tools/deploy_nuclio.ps1
```

Lần build đầu mất vài phút (tải `numpy`, `pillow`, `opencv-python-headless`).
Các lần sau dùng lại docker layer cache nên nhanh hơn nhiều.

Deploy riêng một function — lưu ý `--function` nhận **tên file yaml** (`bbox`,
`semantic`, `drivable`), còn `-Name` của script PowerShell nhận **tên function
trên nuclio** (`smart-bbox`, …):

```powershell
python tools/deploy_nuclio.py --function bbox
powershell -ExecutionPolicy Bypass -File tools/deploy_nuclio.ps1 -Name smart-bbox
```

> **Vì sao không dùng `nuctl` trực tiếp?** Dashboard nuclio (port 8070) không
> publish ra host, và `nuctl.exe` trên Windows gọi `/bin/sh` nên không chạy
> được. Vì vậy `tools/deploy_nuclio.ps1` gọi REST API của dashboard từ một
> container `curlimages/curl` gắn vào network `cvat_cvat`.

---

## 4. Kiểm tra

```powershell
# Trạng thái mọi function trong project cvat (+ log nếu lỗi)
powershell -ExecutionPolicy Bypass -File tools/nuclio_status.ps1 -Logs 30

# Gọi thật một function như CVAT sẽ gọi
python tools/smoke_nuclio.py --function smart-bbox --image test/detect/G01_B026.jpg --dump
```

Kết quả smoke test đã xác minh trên máy này:

| Function | Kết quả trên `G01_B026.jpg` |
| --- | --- |
| `smart-bbox` | 13 rectangle — `car` ×10, `traffic light` ×3 |
| `smart-drivable` | 1 polygon — `area/drivable` (conf 0.9945) |
| `smart-semantic` | 10 polygon — `car` ×6, `road`, `vegetation`, `sky`, `building` |

Sau đó mở **http://localhost:8080/models** — cả ba function `ready` sẽ nằm
cạnh các model hệ thống.

---

## 5. Dùng trong giao diện CVAT

1. Mở task → **Actions ▾ → Automatic annotation**.
2. Chọn model:
   - `Smart BBox (YOLO26)` cho bounding box,
   - `Smart Semantic (EoMT COCO)` cho semantic,
   - `Smart Drivable Area` cho drivable area.
3. Chọn các label cần chạy → **Annotate**.

---

## 6. ⚠️ Quy tắc khớp tên label (nguyên nhân lỗi phổ biến nhất)

CVAT map label của model sang label của task **theo đúng tên**, so sánh chuỗi
chính xác. Label không khớp bị **bỏ im lặng** — không có lỗi, chỉ ra 0 shape:

```python
# cvat/apps/lambda_manager/views.py
if item_label not in mapping:
    continue
```

Ngoài tên, CVAT còn đòi **shape type tương thích** (`labels_compatible`, đã đọc
trực tiếp trong container `cvat_server` phiên bản đang chạy):

```python
compatible_types = [[ShapeType.MASK, ShapeType.POLYGON]]
return (
    model_type == db_type
    or (db_type == "any" and model_type != "skeleton")
    or (model_type == "any" and db_type != "skeleton")
    or any(model_type in c and db_type in c for c in compatible_types)
)
```

Hệ quả thực tế:

| Task label khai báo | Model `rectangle` | Model `polygon` |
| --- | --- | --- |
| `type: rectangle` | ✅ | ❌ bị bỏ |
| `type: polygon` | ❌ bị bỏ | ✅ |
| `type: any` | ✅ | ✅ |
| `type: mask` | ❌ | ✅ (mask/polygon tương thích) |
| `type: skeleton` | ❌ | ❌ |

> **`type: any` KHÔNG phải lỗi.** Rất nhiều task CVAT để mặc định `any`; model
> của dự án vẫn chạy được với chúng.

### Kiểm tra trước khi chạy auto-annotation

```powershell
python tools/cvat_labels.py list                 # liệt kê task
python tools/cvat_labels.py check --verbose      # đối chiếu MỌI task với taxonomy
python tools/cvat_labels.py check --task 13 --json
```

Kết quả mỗi nhóm là `OK` / `MỘT PHẦN` / `HỎNG` kèm số label **dùng được**
(tên khớp **và** type tương thích) trên tổng số.

### Thêm label còn thiếu (mặc định là dry-run)

```powershell
python tools/cvat_labels.py add --task 13 --group semantic          # chỉ in kế hoạch
python tools/cvat_labels.py add --task 13 --group semantic --yes    # áp dụng thật
```

> ⚠️ Nếu task thuộc một **project**, label nằm ở project chứ không ở task. Tool
> sẽ `PATCH /api/projects/<id>` và **sửa label của mọi task trong dự án đó** —
> nó in cảnh báo này trước khi làm. Tool chỉ **thêm** label còn thiếu, không bao
> giờ sửa hay xoá label đang có.

### Nếu không muốn đụng vào task

**Cách A** — đặt tên label trong task giống hệt bảng ở mục 2.

**Cách B** — deploy thêm một biến thể đã remap tên label, không cần sửa code:

```powershell
python tools/deploy_nuclio.py --function bbox `
  --rename-to smart-bbox-cvat `
  --image-suffix cvat `
  --label-map-file nuclio/label-maps/cvat-cityscapes.json

powershell -ExecutionPolicy Bypass -File tools/deploy_nuclio.ps1 -Name smart-bbox-cvat
```

> Trên Windows hãy dùng `--label-map-file` (trỏ tới một file JSON) thay vì
> `--label-map`: PowerShell nuốt dấu `"` khi truyền JSON trực tiếp qua dòng lệnh.

> Lưu ý: `LABEL_MAP` chỉ đổi **tên label lúc trả về**. Danh sách label hiển thị
> trên Models page vẫn lấy từ `spec` trong file yaml, nên khi dùng cách B hãy
> sửa `spec` của bản yaml tương ứng cho khớp — hoặc chấp nhận rằng UI liệt kê
> tên gốc còn annotation tạo ra theo tên đã map.

---

## 6b. Đổi label sau này — sửa `taxonomy.yaml`, không sửa code

**Câu trả lời ngắn: có, đổi được, và chỉ cần sửa đúng một file.**

`taxonomy.yaml` ở gốc repo là **nguồn sự thật duy nhất** cho toàn bộ taxonomy
(4 nhóm theo guideline). Mọi nơi từng hardcode tên label đều đã được nối vào
file này:

```
taxonomy.yaml
  ├─► model-service/taxonomy.json ──► handlers/detect.py   (map COCO -> object)
  │                              └──► handlers/segment.py  (map COCO -> drivable,
  │                                                         lý do lane không hỗ trợ)
  │                              └──► run_results.py       (màu vẽ preview)
  ├─► nuclio/functions/*.yaml   (khối giữa 2 marker GENERATED)
  └─► env TAXONOMY_JSON của function ──► nuclio/src/main.py (map COCO -> semantic)
```

### Quy trình khi guideline thay đổi

```powershell
# 1. Sửa taxonomy.yaml (thêm/bớt/đổi tên label, đổi map COCO, đổi màu preview)

# 2. Sinh lại mọi artifact phái sinh
python tools/sync_taxonomy.py --write

# 3. Kiểm tra không còn lệch (dùng được trong CI)
python tools/sync_taxonomy.py --check

# 4. Áp dụng vào service đang chạy
docker compose up -d --build model-service
python tools/deploy_nuclio.py --all
powershell -ExecutionPolicy Bypass -File tools/deploy_nuclio.ps1
```

### Vì sao không còn "quên chỗ nào"

- `sync_taxonomy.py --check` **thoát với mã 1** nếu bất kỳ artifact nào lệch với
  `taxonomy.yaml`, nên drift bị phát hiện thay vì âm thầm.
- `handlers/detect.py` và `handlers/segment.py` **raise ngay khi import** nếu
  thiếu `model-service/taxonomy.json` — service không thể chạy với label cũ.
- `nuclio/src/main.py` **raise trong `init_context`** nếu thiếu `TAXONOMY_JSON`
  — function không thể khởi động mà bỏ qua taxonomy.
- `taxonomy.yaml` được **validate** khi nạp: shape hợp lệ, không trùng label
  trong một nhóm, không hai label cùng nhận một class COCO, màu phải là
  `[r, g, b]` 0–255.
- Nhóm không có `task` **bắt buộc** phải khai `supported: false` kèm
  `unsupported_reason` — không thể lặng lẽ bỏ sót một nhóm như `lane/*`.

### Xem trước mà không sửa gì

```powershell
python tools/sync_taxonomy.py --print-spec semantic      # JSON label CVAT sẽ đọc
python tools/sync_taxonomy.py --print-runtime            # artifact runtime đầy đủ
```

### Sau khi đổi label, nhớ đổi cả task CVAT

CVAT vẫn map label theo **tên chuỗi chính xác**. Đổi tên trong `taxonomy.yaml`
mà task CVAT chưa đổi thì auto-annotation sẽ ra **0 shape**. Xem mục 6.

---

## 7. Giới hạn đã biết (không phải lỗi)

### `smart-semantic` — là xấp xỉ, không phải model train cho 19 class

Backend là **EoMT-DINOv3 COCO-panoptic (133 class)**. Adapter map các class
COCO sang taxonomy 19 class Cityscapes và **bỏ toàn bộ class còn lại**.

| Vấn đề | Chi tiết |
| --- | --- |
| `pole` | COCO panoptic **không có** class cột/trụ → không bao giờ sinh ra |
| `rider` | COCO panoptic **không có** class người lái → không bao giờ sinh ra |
| `traffic_sign` | Xấp xỉ từ COCO `stop_sign` (COCO không có biển báo chung) |
| `sidewalk` | Từ COCO `pavement-merged` và `platform` |
| `building` | Từ COCO `building-other-merged` và `house` |
| `terrain` | Từ COCO `dirt-merged`, `sand`, `mountain-merged`, `rock-merged`, `gravel`, `snow` |

Bảng map đầy đủ nằm ở `COCO_TO_CITYSCAPES` trong `nuclio/src/main.py`.

### `smart-bbox` — `rider` không bao giờ xuất hiện

YOLO26 pretrained trên COCO, mà COCO detection không có class `rider`; người
lái xe được nhận là `person` → map thành `pedestrian`. Label `rider` vẫn được
khai báo để task có sẵn label đó.

Bản fine-tune trên `train/1354` (25 ảnh) **không tốt hơn bản gốc** nên function
đang dùng `yolo26m.pt` gốc. Xem `docs/TRAINING.md`.

### `smart-drivable` — lane marking (Polyline) không hỗ trợ

`lane/*` không tồn tại trong COCO panoptic, và cả `train/1354` lẫn
`train/1571` đều có **0 annotation** cho 9 class `area/*` + `lane/*`. Không có
dữ liệu thì không train được, nên function chỉ khai báo 2 class drivable và
**không** khai báo polyline. `/segment-drivable` cũng trả về
`lane_marking.supported = false` kèm lý do.

### Độ chính xác

`area/drivable` là xấp xỉ từ COCO `road`, không phải model train trên
BDD100K. Kết quả dùng để **pre-annotation** rồi người sửa lại, không nên coi là
ground truth.

---

## 8. Xử lý sự cố

| Hiện tượng | Nguyên nhân / cách sửa |
| --- | --- |
| Models page không thấy function | Chạy `tools/nuclio_status.ps1`; function phải `ready`. Kiểm tra label `nuclio.io/project-name: cvat` còn đúng không. |
| Function `unhealthy` | `tools/nuclio_status.ps1 -Logs 40` để xem log build. Thường do `pip install` lúc build không có mạng. |
| Function `ready` nhưng CVAT báo lỗi khi chạy | model-service phải sống: `curl.exe http://127.0.0.1:8001/health` |
| Chạy xong không có shape nào | Label của task không khớp tên — xem mục 6. |
| `502 model-service error` | model-service lỗi thật; xem `docker logs cvat-smart-model --tail 50` |
| Muốn xoá function | `powershell -ExecutionPolicy Bypass -File tools/delete_nuclio.ps1 -Name <tên>` |
| Xoá function báo HTTP 405 | Bạn đang gọi `DELETE /api/functions/<tên>`. Route đó chỉ nhận `GET`/`PUT`. nuclio xoá bằng `DELETE /api/functions` **kèm JSON body** `{"metadata":{"name":...}}` — dùng `tools/delete_nuclio.ps1`. |
| Xoá function báo `invalid character 'ï'` | Body JSON dính BOM UTF-8 (PowerShell 5.1 `Set-Content -Encoding utf8`). Dùng `[System.IO.File]::WriteAllText` với `UTF8Encoding($false)` — script trong repo đã làm vậy. |

---

## 9. Cấu trúc file

```
taxonomy.yaml                 ← NGUỒN SỰ THẬT DUY NHẤT cho label (4 nhóm guideline)

nuclio/
├── README.md                 ← tài liệu này
├── src/
│   └── main.py               ← adapter dùng chung cho cả 3 function (TASK env)
├── functions/
│   ├── bbox.yaml             ← env + trigger cho smart-bbox (spec: GENERATED)
│   ├── semantic.yaml         ← ... smart-semantic
│   └── drivable.yaml         ← ... smart-drivable
├── label-maps/
│   └── cvat-cityscapes.json  ← ví dụ label map cho task dùng tên Cityscapes
└── build/                    ← payload JSON sinh ra (không commit)

model-service/
└── taxonomy.json             ← GENERATED từ taxonomy.yaml (commit để --check chạy được)

tools/
├── sync_taxonomy.py          ← taxonomy.yaml -> mọi artifact phái sinh, có --check
├── cvat_labels.py            ← đối chiếu label task CVAT với taxonomy (+ thêm label thiếu)
├── deploy_nuclio.py          ← sinh payload từ yaml + src/main.py + taxonomy
├── deploy_nuclio.ps1         ← POST payload lên nuclio dashboard
├── delete_nuclio.ps1         ← xoá function khỏi nuclio dashboard
├── nuclio_status.ps1         ← xem trạng thái + log function
└── smoke_nuclio.py           ← gọi thử function như CVAT gọi
```

`tools/cvat_labels.py` đọc thông tin đăng nhập theo thứ tự: `--token` →
`CVAT_LOCAL_TOKEN` → `--username/--password` → `CVAT_LOCAL_USERNAME` /
`CVAT_LOCAL_PASSWORD`. Biến môi trường được nạp thêm từ `.env` (gitignored).
Nếu chưa có token:

```powershell
docker exec cvat_server python manage.py drf_create_token <username>
```

Biến môi trường của function (đặt trong `nuclio/functions/*.yaml`):

| Biến | Ý nghĩa | Mặc định |
| --- | --- | --- |
| `TASK` | `bbox` / `semantic` / `drivable` | `bbox` |
| `MODEL_SERVER_URL` | Địa chỉ model-service | `http://host.docker.internal:8001` |
| `MODEL_SERVER_TIMEOUT` | Timeout gọi model-service (giây) | `180` |
| `MIN_ANNOTATION_AREA` | Bỏ shape nhỏ hơn ngưỡng này (px) | `64` |
| `POLYGON_EPSILON` | Hệ số đơn giản hoá contour của `approxPolyDP` | `0.01` |
| `LABEL_MAP` | JSON đổi tên label khi trả về | `{}` |
| `TAXONOMY_JSON` | **Do `tools/deploy_nuclio.py` nhúng từ `taxonomy.yaml`.** Chứa `declared` + `coco_map` của task. Thiếu biến này function **không khởi động được** — đây là chủ ý. | *(không có)* |
