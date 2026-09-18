# Hướng dẫn sử dụng — chạy kết quả chính thức

Hướng dẫn chạy model-service (Docker + CUDA) và sinh kết quả pre-annotation.

> Kiến trúc: [ARCHITECTURE.md](ARCHITECTURE.md) · Train model: [TRAINING.md](TRAINING.md)

---

## 1. Yêu cầu môi trường

- **Windows** + PowerShell
- **Docker Desktop** (WSL2 backend) + **NVIDIA GPU** (driver CUDA 12.x)
- GPU đã xác nhận: **NVIDIA RTX 4060 Laptop GPU** (8 GB VRAM)
- Python 3.10+ (chỉ cần cho `run_results.py` và các script batch ở host; service chạy trong Docker)

---

## 2. Khởi động model-service

### 2.1. Build + chạy (lần đầu)

```powershell
cd D:\DockerData\Cvat\cvat-browser-agent_v2
docker compose up -d --build model-service
```

> Checkpoint SAM2 (`sam-service/checkpoints/`) được mount tự động vào `/models`. Build lần đầu tải torch cu124 + nhúng EoMT vào image (vài GB, mất thời gian).

### 2.2. Chạy lại (image đã build)

```powershell
docker compose up -d model-service
```

### 2.3. Kiểm tra health

```powershell
curl.exe http://127.0.0.1:8001/health
```

Kết quả cần có: `status: ok`, `device: cuda`, `cuda_available: true`, `checkpoint_exists: true`.

---

## 3. Chạy kết quả chính thức (batch)

Một lệnh duy nhất gọi `/detect` + `/segment-drivable` cho mọi ảnh trong thư mục:

```powershell
python run_results.py
```

Tùy chọn:

```powershell
python run_results.py --images "D:\duong_dan\den\anh"   # thư mục ảnh khác
python run_results.py --out results\run_cua_toi          # thư mục output riêng
python run_results.py --semantic                         # thu thập thêm /segment-semantic (raw JSON)
python run_results.py --conf 0.3 --iou 0.5               # chỉnh ngưỡng detection
```

Kết quả → `results\`:

| File | Nội dung |
|---|---|
| `detect.json` / `drivable.json` | Toàn bộ kết quả BBox / drivable area |
| `summary.json` | Tóm tắt tổng hợp |
| `report.md` | Báo cáo + phân bố class |
| `previews/detect/*.jpg` | Preview BBox từng ảnh |
| `previews/drivable/*.jpg` | Preview drivable từng ảnh |
| `contact_sheet_detect.jpg` | Bảng tổng hợp BBox |
| `contact_sheet_drivable.jpg` | Bảng tổng hợp drivable |

---

## 4. Test từng endpoint (curl)

### 4.1. Detection (YOLO26 BBox)

```powershell
curl.exe -F "image=@test\detect\G01_B028.jpg" http://127.0.0.1:8001/detect
```

Tham số tùy chọn (multipart form): `conf` (0.25), `iou` (0.45).

Response (rút gọn):

```json
{
  "width": 1280, "height": 720,
  "model": "yolo26m.pt", "device": "cuda",
  "raw_count": 7,
  "detections": [
    { "label": "car", "confidence": 0.9386, "bbox": [0.8, 398.9, 239.3, 571.5], "raw_class": "car" }
  ],
  "timing_ms": { "preprocess": 0.17, "inference": 244.33, "postprocess": 2.6 },
  "memory": { "allocated_mib": 153.11, "max_allocated_mib": 202.92, "reserved_mib": 258.0 }
}
```

### 4.2. Drivable area (EoMT → Polygon)

```powershell
curl.exe -F "image=@test\detect\G01_B028.jpg" http://127.0.0.1:8001/segment-drivable
```

Response (rút gọn):

```json
{
  "width": 1280, "height": 720,
  "backend": "eomt", "raw_segment_count": 18,
  "drivable": [
    { "label": "area/drivable", "coco_source": "road", "confidence": 0.93, "area_px": 284000,
      "polygons": [[110.0, 400.5, 210.0, 398.0, "..."]]
    }
  ],
  "lane_marking": {
    "supported": false,
    "reason": "COCO panoptic models do not contain the BDD100K lane/* classes."
  }
}
```

> **Drivable area** được xấp xỉ từ COCO: `road` → `area/drivable`, `pavement-merged` → `area/alternative`. **Lane marking không được sinh ra** (COCO không có class `lane/*`) — limitation rõ ràng.

### 4.3. SAM2 auto mask

```powershell
curl.exe -F "image=@test\detect\G01_B028.jpg" http://127.0.0.1:8001/segment-auto
```

### 4.4. Semantic (EoMT, 19 class)

```powershell
curl.exe -F "image=@test\detect\G01_B028.jpg" http://127.0.0.1:8001/segment-semantic
```

---

## 5. Taxonomy — COCO → guideline

> Sinh tự động từ **`taxonomy.yaml`**. Đổi label thì sửa file đó rồi chạy
> `python tools/sync_taxonomy.py --write` (và `--check` để kiểm tra lệch).
> Bảng dưới đây là bản xem nhanh, không phải nguồn sự thật.

Chỉ giữ class được guideline BBox cho phép:

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
- `rider` chưa phân biệt được với `person`.
- `traffic sign` chỉ phủ `stop sign`.

---

## 6. Tuỳ chỉnh model (biến môi trường)

Copy `.env.example` thành `.env` rồi chỉnh (Docker Compose tự đọc):

| Biến | Mặc định | Mục đích |
|---|---|---|
| `YOLO26_MODEL` | `yolo26m.pt` | Weights YOLO26 (`yolo26m` / `yolo26s` nếu OOM) |
| `YOLO26_CONF` | `0.25` | Ngưỡng confidence |
| `YOLO26_IOU` | `0.45` | Ngưỡng NMS |
| `SEMANTIC_BACKEND` | `eomt` | `segformer` / `mask2former` / `eomt` |
| `SEMANTIC_MODEL_ID` | `tue-mps/eomt-dinov3-coco-panoptic-large-640` | Model semantic |
| `SEMANTIC_REFINE` | `true` | SAM2 refine biên |
| `SEMANTIC_SPLIT_INSTANCES` | `true` | Tách instance cùng class |
| `SEMANTIC_MIN_COMPONENT_AREA` | `100` | Diện tích tối thiểu mỗi instance |
| `SAM2_DEVICE` | `cuda` | Thiết bị chạy |
| `ENHANCE_ENABLED` | `true` | Tăng sáng ảnh tối |
| `ENHANCE_DARK_REGIONS` | `true` | Tăng sáng vùng tối |
| `ENHANCE_MOTION_BLUR` | `false` | Khử mờ chuyển động |

---

## 7. VRAM (đã đo thực tế trên RTX 4060 Laptop)

| Model | Peak allocated (MiB) |
|---|---:|
| YOLO26m (detect, 1 ảnh 1280×720) | ~203 |
| EoMT-DINOv3 (drivable/semantic) | ~2611 (allocated ~1211) |

Cả hai đều nằm gọn trong 8 GB, **không OOM**.

---

## 8. Xử lý lỗi

| Triệu chứng | Kiểm tra |
|---|---|
| `docker ps` permission denied | Mở Docker Desktop, daemon đang chạy |
| `/health` `cuda_available: false` | Docker có GPU + NVIDIA runtime |
| `checkpoint_exists: false` | Đảm bảo `sam-service/checkpoints/sam2.1_hiera_large.pt` tồn tại |
| `/detect` lần đầu chậm | Đang tải `yolo26m.pt`; lần sau ~30-120 ms |
| `/segment-drivable` lần đầu chậm | Đang tải EoMT-DINOv3 vào VRAM lần đầu |
| `/segment-drivable` không có lane | Đúng giới hạn COCO (xem mục 4.2) |
| YOLO26 không tải | Kiểm tra mạng khi build, volume `model-ultralytics` |
