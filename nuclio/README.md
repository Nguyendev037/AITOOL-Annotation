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
│  nuclio function  smart-bbox | smart-semantic | smart-drivable | smart-lane
│       │
│       │  POST /detect | /segment-semantic | /segment-drivable | /segment-lane
│       ▼
│  model-service (container `cvat-smart-model`, host port 8001, GPU cho 3 nhánh
│                 đầu — nhánh lane chạy CPU, không tốn VRAM)
│       │
│       ▼
│  YOLO26m  /  EoMT-DINOv3 COCO-panoptic  (+ SAM2 refine)  /  lane classical CV
```

**Vì sao cần 3 lớp?** nuclio function chỉ là adapter CPU mỏng: nó nhận ảnh
base64 từ CVAT, gọi model-service đang giữ GPU, rồi đổi kết quả sang hình học
CVAT (`rectangle` / `polygon` / `polyline`). Nhờ vậy ảnh không phải đi qua GPU
hai lần và function build rất nhanh.

---

## 2. Bốn function được triển khai

| Function | Nhóm guideline | Shape | Class |
| --- | --- | --- | --- |
| `smart-bbox` | Object instance | `rectangle` | 10 class: `pedestrian`, `rider`, `car`, `truck`, `bus`, `train`, `motorcycle`, `bicycle`, `traffic light`, `traffic sign` |
| `smart-semantic` | Semantic segmentation | `polygon` | 19 class Cityscapes |
| `smart-drivable` | Drivable area | `polygon` | `area/drivable`, `area/alternative` |
| `smart-lane` | Lane marking | `polyline` | 7 class `lane/*` |

Mỗi function khai báo label của mình trong `metadata.annotations.spec` của file
`nuclio/functions/*.yaml`. **CVAT đọc đúng danh sách này** để hiển thị và để
map label.

> Các khối `spec`, `help_message`, `description` và `name` trong 3 file yaml đó
> **được sinh tự động** từ `taxonomy.yaml` — đừng sửa tay. Xem mục 6.

Mỗi function còn **ghim cứng cổng host** trong `spec.triggers`: `smart-bbox`
9001, `smart-semantic` 9002, `smart-drivable` 9003, `smart-lane` 9004. Đây là
bản vá cho lỗi "khởi động lại Docker là CVAT không tìm được server" — xem mục 3b.

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

## 3b. ⚠️ Vì sao cổng host bị ghim cứng (`port` trong trigger)

Thuộc tính `port` của trigger HTTP: **để rỗng thì nuclio tự chọn một cổng trống
ngẫu nhiên**. Với Docker platform, cổng đó được publish ra host và được ghi vào
`status.httpPort` của function.

CVAT (mặc định `INVOKE_METHOD=direct`) đọc đúng giá trị đó rồi gọi thẳng cổng
đó — `cvat/apps/lambda_manager/views.py`:

```python
self.port = data["status"].get("httpPort")        # lấy từ nuclio dashboard
url = f"http://host.docker.internal:{func.port}"  # _invoke_directly
```

Hai con số chỉ khớp nhau **tại thời điểm deploy**. Mỗi lần container function
được tạo lại — hay gặp nhất là sau khi khởi động lại Docker Desktop — cổng
publish được chọn lại ngẫu nhiên, trong khi dashboard vẫn giữ `status.httpPort`
cũ. CVAT vì thế gọi vào một cổng không còn ai nghe:
`ConnectionRefusedError` / "không tìm được server".

Vì vậy 4 file `nuclio/functions/*.yaml` **ghim cứng** cổng host:

| Function | `attributes.port` |
| --- | --- |
| `smart-bbox` | 9001 |
| `smart-semantic` | 9002 |
| `smart-drivable` | 9003 |
| `smart-lane` | 9004 |

Cổng publish trên host, `status.httpPort`, và cổng CVAT gọi vì thế **luôn là
một hằng số** — không đổi qua bất kỳ lần restart nào. Đừng xoá `port` khỏi yaml
và đừng đổi số: đổi số thì phải deploy lại function đó. Bốn cổng này phải trống
trên host (`Get-NetTCPConnection -State Listen | Where-Object LocalPort -in 9001..9004`).

Lớp bảo vệ thứ hai nằm ở phía CVAT: đặt `CVAT_NUCLIO_INVOKE_METHOD=dashboard`
cho `cvat_server` và `cvat_worker_annotation` (trong checkout CVAT, ví dụ một
`docker-compose.override.yml`) để CVAT gọi function **qua dashboard theo tên**
(`POST /api/function_invocations`), không dùng cổng host nào nữa. Cách này chữa
luôn các model có sẵn của CVAT (`pth-mmpose-hrnet32`,
`pth-facebookresearch-sam-vit-h`) — cổng của chúng vẫn do nuclio chọn ngẫu nhiên
và không thuộc repo này.

Kiểm tra đối chiếu — `httpPort` **phải bằng** cổng trong `docker ps`:

```powershell
docker ps --format '{{.Names}}|{{.Ports}}' | Select-String nuclio-nuclio
docker exec nuclio wget -qO- http://127.0.0.1:8070/api/functions/smart-bbox
```

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
| `smart-lane` | **1 polyline** — `lane/single yellow` (conf 0.6835), bắt đầu tại `(306.0, 544.4)` |

Sau đó mở **http://localhost:8080/models** — cả bốn function `ready` sẽ nằm
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

### `smart-lane` — classical CV, không phải model học

Nhóm `lane/*` lấy từ BDD100K, nhưng **không có checkpoint công khai nào** dự
đoán 7 class này, và cả `train/1354` lẫn `train/1571` đều có **0 annotation**
lane. Không có dữ liệu thì không train được, nên `smart-lane` dùng detector
classical CV tất định trong `model-service/handlers/lane.py`.

Điểm cốt lõi: bài toán này **không phải bài toán pixel mà là bài toán đơn vị**.
Trong một khung hình dashcam, cùng một vạch 0.15 m rộng ~40 px ở cách 3 m và
~3 px ở cách 25 m — `dx/dX = f/Z` đổi hơn 10 lần. Một kernel pixel cố định vì
thế sai ở đâu đó **theo cấu trúc**: top-hat 21 px nằm lọt *bên trong* vạch gần
và trả về 0. Cách sửa không phải chỉnh tham số mà là đổi đơn vị: chiếu mặt
đường về raster "bird's-eye" theo **mét** (40 px/m) rồi mới làm top-hat,
connected-components và PCA ở đó. `f` triệt tiêu trong công thức `X`, nên đo
bề rộng chỉ cần chiều cao camera và hàng chân trời — không cần calibration.

Kết quả đo trên 25 ảnh `test/detect` (CPU, ~25 ms/ảnh, **0 MiB VRAM**):

| Class | marks | frames |
| --- | --- | --- |
| `lane/single white` | 38 | 17/25 |
| `lane/single yellow` | 11 | 6/25 |
| `lane/single other` | 7 | 6/25 |
| `lane/double white` | 0 | 0/25 |
| `lane/double yellow` | 0 | 0/25 |
| `lane/crosswalk` | 0 | 0/25 |
| `lane/road curb` | 0 | 0/25 (mặc định tắt) |

**Đây là công cụ hỗ trợ review, không phải ground truth.** Precision tốt hơn
recall: trên khung ban ngày có zebra, model trả về đúng 1 polyline bám vạch
trắng và không có false positive nào; nhưng nó **bỏ sót** zebra và nhiều vạch
rõ ràng khác. Ba hạn chế có thật, đã đo:

1. **Chỉ trace ~40% dưới khung.** `LANE_MAX_DEPTH_M=12`. Ở Z=20 m, bird raster
   upsample `(Z²/(f·h))·ppm ≈ 15` hàng bird cho mỗi hàng ảnh, biến một pixel
   nhiễu chân trời thành blob dài 1 m trông như vạch. Hạ depth cap 20→12 cắt
   phần lớn false positive đó, đổi lại mất vùng xa.
2. **`lane/double *` gần như không tách được.** Cặp vạch đôi rộng 0.45–0.55 m
   bị kênh top-hat thô (0.85 m) gộp thành một dải; đếm gờ trên kênh tinh chỉ
   còn vài chục pixel nên không đủ tin cậy. Vạch vàng đôi rõ trong `G01_B026`
   được trace **đúng hình học** nhưng gán `lane/single yellow`.
3. **`lane/crosswalk` chưa bắn.** Zebra có bars 0.4–0.6 m cách nhau 0.6–0.9 m;
   kênh tinh (0.30 m) triệt bars, kênh thô (0.85 m) lại gộp chúng. Cần một
   kênh trung gian ~0.65 m — chưa làm.

`lane/road curb` mặc định **tắt** (`LANE_CURB_ENABLED=false`): curb là biên độ
sâu chứ không phải vạch sáng, và detector gradient cho quá nhiều false
positive. Bật lên mà tự đánh giá.

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
| Auto-annotation báo `ConnectionRefusedError` tới `host.docker.internal:<cổng>`, và cổng đó **không có** trong `docker ps` | nuclio ghi `status.httpPort` lúc deploy, còn CVAT (`INVOKE_METHOD=direct`) gọi thẳng cổng đó; khi Docker tạo lại container function ở cổng ngẫu nhiên khác, dashboard vẫn giữ cổng cũ nên CVAT gọi vào cổng đã chết. Đã chữa tận gốc bằng cổng ghim trong `nuclio/functions/*.yaml` + `CVAT_NUCLIO_INVOKE_METHOD=dashboard` — xem mục 3b. Nếu vẫn lệch (function chưa deploy lại theo bản mới, hoặc model có sẵn của CVAT như `pth-*`): deploy lại function — `powershell -ExecutionPolicy Bypass -File tools/deploy_nuclio.ps1 -Name <tên>`. Đối chiếu: `docker exec nuclio wget -qO- http://127.0.0.1:8070/api/functions/<tên>` phải khớp cổng trong `docker ps`. |
| Auto-annotation trả về `exc_info` lỗi **nhưng shape vẫn được tạo ra** | Response đó là **bản ghi job cũ**. Job id cố định (`action=autoannotate&target=task&target_id=<id>`), nên POST lần sau trả lại kết quả hỏng đã lưu. Đừng tin `exc_info`; kiểm tra thật bằng `docker logs nuclio-nuclio-<tên> --tail 10` xem có dòng `produced N annotation(s)` không. |
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
│   └── main.py               ← adapter dùng chung cho cả 4 function (TASK env)
├── functions/
│   ├── bbox.yaml             ← env + trigger cho smart-bbox (spec: GENERATED)
│   ├── semantic.yaml         ← ... smart-semantic
│   ├── drivable.yaml         ← ... smart-drivable
│   └── lane.yaml             ← ... smart-lane (polyline, CPU)
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
