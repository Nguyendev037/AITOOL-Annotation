# CVAT Smart Model Service — pre-annotation

Hệ thống **pre-annotation** chạy trong Docker + CUDA, sinh annotation gợi ý cho
CVAT theo đúng taxonomy trong guideline. Có 3 nhánh inference:

1. **Object Detection (BBox)** — YOLO26 (`yolo26m.pt`) qua `/detect`.
2. **Drivable area (Polygon)** — EoMT-DINOv3 COCO-panoptic qua `/segment-drivable` (xấp xỉ từ `road`/`pavement`).
3. **Segmentation** — Semantic (EoMT-DINOv3) qua `/segment-semantic` và SAM2 auto-mask qua `/segment-auto`.

> **Chạy kết quả chính thức chỉ với 2 lệnh** — xem ngay [Quick Start](#quick-start-chạy-kết-quả).
> Dùng model trong CVAT: [nuclio/README.md](nuclio/README.md) · Chi tiết: [docs/USAGE.md](docs/USAGE.md) · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/TRAINING.md](docs/TRAINING.md)

---

## Trạng thái hiện tại

| Thành phần                          | Trạng thái                                          |
| ----------------------------------- | --------------------------------------------------- |
| `/detect` — YOLO26 BBox              | ✅ Hoạt động (CUDA, đã test 25 ảnh)                 |
| `/segment-drivable` — EoMT Polygon   | ✅ Hoạt động (xấp xỉ `road`/`pavement`)             |
| `/segment-auto` — SAM2               | ✅ Hoạt động (CUDA)                                 |
| `/segment-semantic` — EoMT           | ✅ Hoạt động (COCO 133 → map 19 class, xấp xỉ)      |
| Lane marking (`lane/*`)              | ❌ Không khả thi với model COCO (limitation rõ ràng)|
| Nuclio functions cho CVAT            | ✅ `smart-bbox`, `smart-semantic`, `smart-drivable` |
| Full browser-agent / DeepSeek client | ❌ Đã gỡ bỏ (kiến trúc cũ)                          |

---

## Quick Start — chạy kết quả

### Bước 1: Khởi động model-service (một lần)

```powershell
cd D:\DockerData\Cvat\cvat-browser-agent_v2
docker compose up -d --build model-service
```

> Checkpoint SAM2 (898 MB) nằm ở `sam-service/checkpoints/` và được mount tự động vào `/models`.
> Build lần đầu tải torch cu124 + nhúng EoMT vào image (vài GB, mất thời gian).

Kiểm tra health:

```powershell
curl.exe http://127.0.0.1:8001/health
```

Cần thấy: `status: ok`, `device: cuda`, `cuda_available: true`, `checkpoint_exists: true`.

### Bước 2: Chạy kết quả chính thức (một lệnh)

```powershell
python run_results.py
```

Mặc định đọc ảnh từ `test\detect\*.jpg`, gọi `/detect` + `/segment-drivable` cho từng ảnh,
rồi ghi kết quả vào `results\`:

| File | Nội dung |
|---|---|
| `detect.json` / `drivable.json` | Toàn bộ kết quả BBox / drivable area |
| `summary.json` | Tóm tắt tổng hợp |
| `report.md` | Báo cáo + phân bố class |
| `previews/detect/*.jpg` | Preview BBox từng ảnh |
| `previews/drivable/*.jpg` | Preview drivable từng ảnh |
| `contact_sheet_detect.jpg` | Bảng tổng hợp BBox |
| `contact_sheet_drivable.jpg` | Bảng tổng hợp drivable |

Chạy trên thư mục ảnh khác:

```powershell
python run_results.py --images "D:\duong_dan\den\anh" --out results\run_cua_toi
python run_results.py --semantic    # thu thập thêm /segment-semantic (raw JSON)
```

---

## Dùng model trong CVAT (Automatic annotation)

Model được đóng gói thành **3 nuclio serverless function** và hiện trên trang
**Models** của CVAT localhost, dùng trực tiếp qua *Actions → Automatic annotation*.

```powershell
# 1. model-service phải đang chạy
docker compose up -d model-service

# 2. Deploy function lên nuclio
python tools/deploy_nuclio.py --all
powershell -ExecutionPolicy Bypass -File tools\deploy_nuclio.ps1

# 3. Kiểm tra
powershell -ExecutionPolicy Bypass -File tools\nuuclio_status.ps1 -Logs 30
python tools\smoke_nuclio.py --function smart-bbox --image test\detect\G01_B026.jpg --dump
```

| Function | Shape | Class |
| --- | --- | --- |
| `smart-bbox` | `rectangle` | 10 class guideline |
| `smart-semantic` | `polygon` | 19 class Cityscapes (map từ COCO) |
| `smart-drivable` | `polygon` | `area/drivable`, `area/alternative` |

> ⚠️ **Tên label của task phải trùng khít với label function khai báo.** CVAT map
> theo đúng tên chuỗi; lệch một ký tự (`traffic light` vs `traffic_light`) là
> không tạo được shape. Xem mục 6 của [nuclio/README.md](nuclio/README.md) để
> biết cách dùng `--label-map`.

> 🔁 **Đổi label?** Toàn bộ taxonomy nằm trong **một file duy nhất** —
> [`taxonomy.yaml`](taxonomy.yaml). Sửa file đó rồi chạy
> `python tools/sync_taxonomy.py --write` là mọi nơi (label spec của nuclio
> function, map COCO của model-service, màu preview) tự cập nhật. Kiểm tra lệch:
> `python tools/sync_taxonomy.py --check`. Quy trình đầy đủ:
> [nuclio/README.md mục 6b](nuclio/README.md#6b-đổi-label-sau-này--sửa-taxonomyyaml-không-sửa-code).

> 🔎 **Trước khi chạy auto-annotation**, kiểm tra task có label khớp model chưa —
> lệch tên là ra **0 shape mà không báo lỗi**:
>
> ```powershell
> python tools/cvat_labels.py check --verbose
> ```
>
> Kết quả `OK` / `MỘT PHẦN` / `HỎNG` cho từng model trên từng task.

Hướng dẫn đầy đủ — kiến trúc, giới hạn, xử lý sự cố: **[nuclio/README.md](nuclio/README.md)**

---

## Các endpoint

| Endpoint                 | Mô hình | Mục đích                          |
| ------------------------ | ------- | --------------------------------- |
| `GET /health`            | —       | Trạng thái service + CUDA         |
| `POST /detect`           | YOLO26  | BBox object detection             |
| `POST /segment-drivable` | EoMT    | Drivable area Polygon (xấp xỉ)    |
| `POST /segment-auto`     | SAM2    | Auto mask generation              |
| `POST /segment-semantic` | EoMT    | Semantic segmentation + SAM refine|
| `POST /keypoint`         | —       | Placeholder (501)                 |

### `/detect` — request & response

- **Request**: multipart `image` (file). Tùy chọn `conf` (default 0.25), `iou` (default 0.45).
- **Response**: `width`, `height`, `model`, `device`, `raw_count`, `detections[]` (`label`, `confidence`, `bbox[x1,y1,x2,y2]`, `raw_class`), `timing_ms`, `memory`.

---

## Taxonomy — COCO → guideline

Chỉ giữ các class được guideline BBox cho phép, còn lại bị lọc bỏ:

| COCO (YOLO26) | Guideline     |
| ------------- | ------------- |
| person        | pedestrian    |
| bicycle       | bicycle       |
| car           | car           |
| motorcycle    | motorcycle    |
| bus           | bus           |
| train         | train         |
| truck         | truck         |
| traffic light | traffic light |
| stop sign     | traffic sign  |

**Giới hạn đã biết:**

- `rider` chưa phân biệt được với `person` (COCO không có thuộc tính "đang cưỡi").
- `traffic sign` chỉ phủ được `stop sign`; các loại biển báo khác chưa được model nhận diện.

---

## Drivable area & lane marking (Polygon / Polyline)

`/segment-drivable` dùng EoMT-DINOv3 (COCO-panoptic) để xuất **Polygon drivable area**.
Vì COCO không có class BDD100K `area/*` và `lane/*`, mapping là **xấp xỉ có ghi chú**:

| COCO (EoMT)       | Guideline          | Ghi chú                          |
| ----------------- | ------------------ | -------------------------------- |
| `road`            | `area/drivable`    | Xấp xỉ — không tách drivable vs alternative |
| `pavement-merged` | `area/alternative` | Xấp xỉ (hè/lề đường)             |

**Lane marking (`lane/*`) — KHÔNG được sinh ra.** Không model COCO-panoptic nào biết 7 class
`lane/*` (crosswalk, double white/yellow, road curb, single other/white/yellow). Đây là
**limitation rõ ràng**, không tự bịa class.

> Muốn có lane marking đúng taxonomy: cần label `lane/*` (polyline) trong dữ liệu train để huấn luyện model riêng.

---

## Cấu trúc thư mục

```
cvat-browser-agent_v2/
├── taxonomy.yaml            # ⭐ NGUỒN SỰ THẬT DUY NHẤT cho label (4 nhóm guideline)
├── model-service/          # FastAPI inference server (code chính)
│   ├── app.py              # Routes + health
│   ├── handlers/detect.py  # YOLO26 detection (đọc taxonomy.json)
│   ├── handlers/segment.py # EoMT + SAM2 (đọc taxonomy.json)
│   ├── taxonomy.json       # GENERATED từ taxonomy.yaml (commit)
│   ├── enhancement.py      # Tiền xử lý ảnh
│   ├── guideline_agent.py  # (cũ) sinh label schema bằng LLM — không còn dùng
│   ├── Dockerfile          # CUDA 12.4 + torch cu124
│   └── requirements.txt
├── nuclio/                  # Adapter CVAT serverless
│   ├── src/main.py         # 1 adapter cho cả 3 function (TASK env)
│   ├── functions/*.yaml    # smart-bbox / smart-semantic / smart-drivable
│   └── build/              # Payload JSON sinh ra (gitignored)
├── sam-service/checkpoints/ # SAM2 checkpoint (898 MB, gitignored)
├── cvat-model-integrator/   # Skill tích hợp model vào CVAT
├── guildlline/              # PDF/DOCX guideline gốc (BBox + Semantic + Week2 Face/Pose)
├── guideline/               # Markdown guideline đã chuẩn hóa + generated/
├── rules/                   # ⭐ LUẬT annotation dạng dữ liệu (sửa ở đây để đổi hành vi)
├── browser_agent/           # ⭐ Lõi browser-agent: browser-use, vision, CVAT REST
│   ├── vision/             #   pipeline map landmark, worker MediaPipe/FaceMesh, rules.py
│   ├── cdp_ws.py           #   WebSocket tự viết (không cần gói ngoài)
│   └── geometry.py         #   Thứ tự điểm theo guideline (VF-50, pose-17)
├── ai/doc/                  # ⭐ Tài liệu hạng mục browser-agent
│   ├── TIEN-DO-BROWSER-AGENT.md      # Nhật ký kỹ thuật + bằng chứng
│   └── HUONG-DAN-BROWSER-AGENT.md    # Hướng dẫn sử dụng
├── train/                   # Dataset train (1354 = bbox, 1571 = segmentation)
├── test/detect/             # Ảnh test (25 ảnh)
├── results/                 # Kết quả batch test (gitignored)
├── tools/                   # sync_taxonomy / cvat_labels / deploy_nuclio / delete_nuclio / smoke
├── work/                    # Artifact debug + scripts (gitignored)
├── run_results.py           # ⭐ Entry point chạy kết quả chính thức
├── .env.example             # Template biến môi trường
└── docker-compose.yml
```

---

## Tuỳ chỉnh model (biến môi trường)

Copy `.env.example` thành `.env` rồi chỉnh:

| Biến                | Mặc định                                      | Mục đích                             |
| ------------------- | --------------------------------------------- | ------------------------------------ |
| `YOLO26_MODEL`      | `/weights/yolo26m.pt`                         | Weights YOLO26 (bind-mount read-only) |
| `YOLO26_CONF`       | `0.25`                                        | Ngưỡng confidence detection          |
| `YOLO26_IOU`        | `0.45`                                        | Ngưỡng NMS IoU                       |
| `SEMANTIC_BACKEND`  | `eomt`                                        | `segformer` / `mask2former` / `eomt` |
| `SEMANTIC_MODEL_ID` | `tue-mps/eomt-dinov3-coco-panoptic-large-640` | Model semantic                       |
| `SEMANTIC_REFINE`   | `true`                                        | Bật SAM2 refine biên                 |
| `SAM2_DEVICE`       | `cuda`                                        | Thiết bị chạy                        |
| `ENHANCE_ENABLED`   | `true`                                        | Tăng sáng ảnh tối                    |

---

## Xử lý lỗi thường gặp

| Triệu chứng                                   | Kiểm tra                                                                 |
| --------------------------------------------- | ------------------------------------------------------------------------ |
| `docker ps` báo permission denied             | Mở Docker Desktop, đảm bảo daemon chạy (service vẫn có thể phục vụ HTTP) |
| `/health` `cuda_available: false`             | Docker có GPU, `capabilities: [gpu]`, NVIDIA runtime                     |
| `checkpoint_exists: false`                    | Đảm bảo `sam-service/checkpoints/sam2.1_hiera_large.pt` tồn tại          |
| `/detect` treo > 1 phút, MỌI endpoint đều treo | Thiếu `model-service/weights/yolo26m.pt` → ultralytics tải 42 MB từ GitHub (~26 KB/s) và chặn event loop. Xem `docker logs cvat-smart-model` |
| `/detect` các lần sau                         | ~30-120 ms (model đã nạp vào VRAM)                                       |
| `/segment-drivable` lần đầu chậm              | Đang tải EoMT-DINOv3 vào VRAM lần đầu (~vài GB)                          |
| `/segment-drivable` không có lane             | Đúng giới hạn COCO — xem mục "Drivable area & lane marking"              |
| Chạy auto-annotation ra 0 shape               | `python tools/cvat_labels.py check --task <id> --verbose` — tên label task không khớp model |
| YOLO26 không tải được                         | `model-service/weights/yolo26m.pt` phải tồn tại trên host; mount read-only tại `/weights` |

---

## Phạm vi đã làm / chưa làm

**Đã làm:**

- YOLO26 BBox detection hoạt động trên CUDA, load model 1 lần, lọc class theo guideline.
- Batch test 25 ảnh → ~196 detection hợp lệ (car 140, traffic light 27, bus 10, truck 10, pedestrian 7, motorcycle 1, bicycle 1).
- SAM2 `/segment-auto` hoạt động.
- `/segment-semantic` (EoMT, 19 class) hoạt động.
- `/segment-drivable` (EoMT) xuất Polygon drivable area (xấp xỉ `road`/`pavement`).
- Fine-tune YOLO26 bbox trên `train/1354` (xem `docs/TRAINING.md`).
- 3 nuclio function (`smart-bbox` rectangle, `smart-semantic` polygon, `smart-drivable` polygon) hiện trên Models page của CVAT localhost.
- Taxonomy tập trung vào `taxonomy.yaml` + `tools/sync_taxonomy.py --check` phát hiện lệch.

**Chưa làm (giới hạn rõ ràng):**

- **Lane marking (`lane/*`)** — không khả thi với model COCO-panoptic; cần label polyline riêng để train.
- Khôi phục full browser-agent / DeepSeek client (kiến trúc cũ đã gỡ bỏ).
