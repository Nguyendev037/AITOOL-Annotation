# CVAT Browser Agent v2

Hệ thống tự động hóa **semantic segmentation** cho CVAT. Kết hợp model semantic (SegFormer/Mask2Former/EoMT), SAM 2.1 Hiera Large, DeepSeek Vision và browser-use agent để tạo, review và upload mask annotation.

> **Tài liệu chi tiết**: [docs/USAGE.md](docs/USAGE.md) · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/TRAINING.md](docs/TRAINING.md)

---

## Quick Start — Dùng lại vào lần sau

> Mục này dành cho khi đã cài đặt xong từ trước. Nếu chưa cài, xem [Cài đặt lần đầu](#cài-đặt-lần-đầu).

### Bước 1: Khởi động SAM/Semantic service

```powershell
docker run --rm --gpus all -p 8001:8000 --name sam2-large `
  -v "D:\DockerData\Cvat\cvat-browser-agent_v2\sam-service\checkpoints:/models:ro" `
  -e SAM2_CONFIG=configs/sam2.1/sam2.1_hiera_l.yaml `
  -e SEMANTIC_BACKEND=eomt `
  -e SEMANTIC_MODEL_ID=tue-mps/eomt-dinov3-coco-panoptic-large-640 `
  -e SEMANTIC_REFINE=true `
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 `
  sam2-large-service
```

Model EoMT-DINOv3 (1.17 GB) đã được nhúng sẵn trong image tại `/opt/hf-cache`, nên
service chạy được **hoàn toàn offline**. Hai biến `HF_HUB_OFFLINE=1` và
`TRANSFORMERS_OFFLINE=1` buộc thư viện dùng cache trong image thay vì gọi mạng.

> Không mount đè lên `/opt/hf-cache`, nếu không cache EoMT nhúng sẵn sẽ bị che mất.

Giữ terminal này mở. Kiểm tra từ terminal khác:

```powershell
curl.exe http://127.0.0.1:8001/health
```

### Bước 2: Mở Chrome CDP + đăng nhập CVAT

```powershell
& 'C:\Program Files\Google\Chrome\Application\chrome.exe' `
  --remote-debugging-port=9222 `
  --user-data-dir='D:\browser-user\chrome-cvat-profile'
```

Đăng nhập CVAT → mở Job → chọn **frame chưa hoàn tất**. Nếu đổi Job mới, sửa `.env` trước.

### Bước 3: Chạy (chọn 1 trong 3 cách)

**Cách A — Web UI** (khuyến nghị cho hầu hết trường hợp):

```powershell
.\run_console.ps1
# Mở http://127.0.0.1:8765, nhập frame ID, click Preview hoặc Run
```

**Cách B — CLI thử 1 frame** (không upload):

```powershell
& 'D:\browser-user\.venv\Scripts\python.exe' -m app.main `
  --no-browser --frame 26 --no-write `
  --guideline-file 'guideline\semantic_segmentation.md'
```

**Cách C — Browser agent tự động**:

```powershell
& 'D:\browser-user\.venv\Scripts\python.exe' -m app.main
```

### Bước 4: Kiểm tra kết quả

```powershell
# Xem state hiện tại
Get-Content work\state.json

# Xem artifact frame 26
Get-Content work\job_1573\frame_26\selected.json
Start-Process work\job_1573\frame_26\preview.jpg
```

---

## Cài đặt lần đầu

### 1. Yêu cầu

- Windows + PowerShell
- Python 3.10+ (venv tại `D:\browser-user\.venv`)
- Docker Desktop (WSL2 backend, NVIDIA GPU)
- CVAT đang chạy, có quyền truy cập Job
- DeepSeek API key
- Checkpoint `sam2.1_hiera_large.pt`

### 2. Cài dependencies

```powershell
cd D:\DockerData\Cvat\cvat-browser-agent_v2
& 'D:\browser-user\.venv\Scripts\python.exe' -m pip install -r requirements.txt
& 'D:\browser-user\.venv\Scripts\python.exe' -m pytest -q app/test_pipeline.py
```

### 3. Cấu hình `.env`

File `.env` đã có trong dự án. Ứng dụng tự đọc file này. **Không** mở bằng `Get-Content`, `cat`, `type`, không copy nội dung vào ticket/log và không đưa `.env` vào Git.

Kiểm tra an toàn:

```powershell
& 'D:\browser-user\.venv\Scripts\python.exe' -m app.main --check-config
```

Tối thiểu cần có:

```dotenv
CVAT_URL=http://127.0.0.1:8080
CVAT_TOKEN=your_cvat_personal_access_token
DEEPSEEK_API_KEY=your_deepseek_api_key
CVAT_JOB_ID=1573
CVAT_START_FRAME=25
CVAT_STOP_FRAME=49
```

Xem danh sách đầy đủ các biến trong [docs/USAGE.md](docs/USAGE.md#33-cấu-hình-env).

### 4. Chuẩn bị checkpoint SAM2

```powershell
New-Item -ItemType Directory -Force sam-service\checkpoints | Out-Null
Test-Path sam-service\checkpoints\sam2.1_hiera_large.pt   # Phải trả True
```

### 5. Đồng bộ labels và guideline

```powershell
# Tạo labels.json từ 19 class guideline + CVAT Job IDs
& 'D:\browser-user\.venv\Scripts\python.exe' -m app.main --sync-labels

# (Tùy chọn) Cập nhật guideline Markdown từ PDF/DOCX gốc
& 'D:\browser-user\.venv\Scripts\python.exe' -m app.main --sync-guidelines
```

### 6. Build Docker image cho SAM service

```bash
cd /mnt/d/DockerData/Cvat/cvat-browser-agent_v2
docker build -t sam2-large-service ./sam-service
```

Sau khi build xong, chạy lại theo [Quick Start](#quick-start--dùng-lại-vào-lần-sau).

---

## Tổng quan kiến trúc

```
PDF/DOCX gốc  →  guideline_sync.py  →  Markdown guideline
                                              ↓
CVAT frame  →  Image Enhancement  →  Semantic Model  →  SAM2 Refine
                                              ↓
                    DeepSeek Review (tùy chọn)  →  CVAT Native Mask
                                                        ↓
                                    Browser Agent  →  Xác nhận trực quan
```

**19 semantic classes**: road, sidewalk, building, wall, fence, pole, traffic_light, traffic_sign, vegetation, terrain, sky, person, rider, car, truck, bus, train, motorcycle, bicycle.

---

## Tất cả các lệnh

| Lệnh                                | Mục đích                                                 |
| ----------------------------------- | -------------------------------------------------------- |
| `--check-config`                    | Hiển thị trạng thái cấu hình (không lộ secret)           |
| `--sync-labels`                     | Đồng bộ 19 label từ guideline + CVAT Job → `labels.json` |
| `--sync-guidelines`                 | PDF/DOCX → DeepSeek → Markdown guideline                 |
| `--no-browser --frame N --no-write` | Smoke test 1 frame, không upload                         |
| `--no-browser --frame N`            | Chạy pipeline + upload 1 frame qua API                   |
| `--frame N --upload-selected ID...` | Upload mask đã review                                    |
| `--evaluate-dataset --frame N`      | So sánh với ground truth YOLO                            |
| `python -m app.web_ui`              | Web console tại port 8765                                |
| `python -m app.main` (không flag)   | Browser agent tự động                                    |

---

## State machine

| Trạng thái               | Ý nghĩa                      | Cách tiếp tục                                 |
| ------------------------ | ---------------------------- | --------------------------------------------- |
| `generated` / `selected` | Đã tạo mask; chưa ghi CVAT   | Kiểm tra artifacts rồi chạy lại nếu cần       |
| `uploaded`               | API đã ghi; UI chưa xác nhận | Refresh CVAT, xem mask → đánh dấu `completed` |
| `partial_uploaded`       | Một số mask đã ghi           | Dùng `--upload-selected` cho nhãn chưa ghi    |
| `completed`              | Đã xác nhận trực quan        | Mở frame tiếp; pipeline từ chối xử lý lại     |

---

## Xử lý lỗi thường gặp

| Triệu chứng                             | Kiểm tra                                           |
| --------------------------------------- | -------------------------------------------------- |
| `CVAT_URL and CVAT_TOKEN are required`  | `.env` ở thư mục project và token còn hiệu lực     |
| `DEEPSEEK_API_KEY is required`          | Đã khai báo key; không để rỗng                     |
| `SAM2 checkpoint not found`             | File checkpoint đúng tên và mount vào `/models`    |
| SAM health `device=cpu`                 | Docker có GPU, `--gpus all`, NVIDIA runtime        |
| `Label ... is missing from labels.json` | Chạy `--sync-labels`                               |
| `Frame ... outside Job range`           | Sửa frame hoặc `.env`                              |
| Browser không thấy CVAT                 | Kiểm tra CDP `9222`, URL Job, đăng nhập            |
| Docker image not found                  | `docker build -t sam2-large-service ./sam-service` |

Giữ `work/` khi đang debug hoặc tiếp tục Job. Khi lỗi SAM2, xem log Docker. Khi lỗi DeepSeek, kiểm tra API key/model. Không bỏ qua lỗi bằng cách tự động chuyển frame.

---

## Tuỳ chỉnh thông số model

Xem hướng dẫn đầy đủ tại **[docs/USAGE.md — Mục 9](docs/USAGE.md)**. Tóm tắt nhanh:

### Biến `.env` (client)

| Biến | Mặc định | Tác dụng |
|---|:---:|---|
| `DEEPSEEK_SEGMENT_REVIEW` | `false` | DeepSeek review mask trước khi upload |
| `ANNOTATION_FORMAT` | `mask` | `mask` hoặc `polygon` |
| `POLYGON_EPSILON` | `0.01` | Độ chi tiết polygon (nhỏ hơn = nhiều đỉnh hơn) |
| `AUTO_BRIGHTEN_DARK_IMAGES` | `true` | Tăng sáng vùng tối trước khi segment |

### Biến Docker `-e` (SAM service)

| Biến Docker | Mặc định | Tác dụng |
|---|:---:|---|
| `SEMANTIC_BACKEND` | `segformer` | `segformer` / `mask2former` / `eomt` |
| `SEMANTIC_MODEL_ID` | *(HuggingFace ID)* | Đổi model cụ thể |
| `SEMANTIC_REFINE` | `true` | SAM2 tinh chỉnh biên |
| `SEMANTIC_REFINE_MIN_AREA` | `500` | Diện tích object tối thiểu để refine |
| `SEMANTIC_REFINE_MIN_IOU` | `0.6` | IoU tối thiểu để chấp nhận SAM refine |
| `SEMANTIC_SPLIT_INSTANCES` | `true` | **Tách các vật thể cùng class thành mask riêng biệt** |
| `SEMANTIC_MIN_COMPONENT_AREA` | `100` | Diện tích tối thiểu (px) cho mỗi vật thể tách ra |

> [!NOTE]
> **Browser agent** được cấu hình chỉ gọi tool calls — không tự reload hoặc chuyển hướng trang. Điều này đảm bảo Web Console tại `http://127.0.0.1:8765` không bị gián đoạn khi chạy browser workflow.
