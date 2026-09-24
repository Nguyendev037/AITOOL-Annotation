# Lane marking (Polyline) — trạng thái và cách chạy tiếp

Tài liệu này ghi lại chính xác chỗ đang dừng, để lần sau chạy tiếp không phải
suy đoán lại. Viết ngày 2026-09-18.

---

## 1. Đang dừng ở đâu

**Đã xong** — code viết rồi, build rồi, đo rồi:

| Việc | Trạng thái |
| --- | --- |
| `model-service/handlers/lane.py` | ✅ detector classical CV, CPU-only |
| Endpoint `POST /segment-lane` | ✅ trả HTTP 200, ~25 ms/ảnh |
| `nuclio/src/main.py` task `lane` | ✅ builder trả `type: "polyline"` |
| `nuclio/functions/lane.yaml` | ✅ (spec sinh từ `taxonomy.yaml`) |
| `taxonomy.yaml` nhóm `lane` | ✅ `supported: true`, 7 label |
| Payload `nuclio/build/smart-lane.json` | ✅ `tools/check_nuclio_payloads.py` pass |
| Image `cvat-smart-model-service:latest` | ✅ **11.3 GB, đã build, giữ trong Docker** |
| Docs (`nuclio/README.md`, `guideline/README.md`) | ✅ |

**Đã xong hết** — deploy và smoke test đã chạy thật:

> ✅ **`smart-lane` ở trạng thái `ready` trong nuclio và trả về `polyline` thật.**
> Smoke test trên `G01_B026.jpg`: 1 annotation, `type: polyline`,
> `label: lane/single yellow`, conf 0.6835, `points` là **mảng phẳng** bắt đầu
> tại `(306.0, 544.4)` — đúng như dự đoán ở mục 2.

> ⚠️ **Một regression đã tìm ra và sửa trong lần chạy này.** Khi bật nhóm `lane`,
> `taxonomy.json` không còn khoá `unsupported["lane"]`, nhưng
> `model-service/handlers/segment.py` đọc khoá đó ở **cấp module** →
> `KeyError: 'lane'` giết `/segment-semantic`, `/segment-drivable` và
> `/segment-auto`. Đã bỏ hẳn khối `lane_marking` vì nó chỉ *tái phát biểu* một
> sự thật mà `taxonomy.json` đã sở hữu (duplicate owner).
>
> **Bài học vận hành:** code được **nướng vào image** (`COPY . /opt/service/`),
> không mount. Sửa file trong `model-service/` xong **bắt buộc**
> `docker compose build model-service` rồi `up -d` lại — nếu không, container
> vẫn chạy code cũ và mọi test sẽ xanh một cách giả tạo. Kiểm tra nhanh:
> `docker exec cvat-smart-model grep -n unsupported /opt/service/handlers/segment.py`

---

## 2. Chạy tiếp — đúng thứ tự này

```powershell
# 1. Bật stack CVAT (compose có `name: cvat`, nên network là cvat_cvat)
cd D:\DockerData\Cvat\cvat-day2
docker compose up -d

# 2. Bật model-service (image đã build sẵn, KHÔNG cần --build)
cd D:\DockerData\Cvat\cvat-browser-agent_v2
docker compose up -d model-service
curl.exe http://127.0.0.1:8001/health      # cần status: ok

# 3. Deploy (payload đã sinh sẵn; bước python chỉ để chắc chắn còn đồng bộ)
python tools/deploy_nuclio.py --all
powershell -ExecutionPolicy Bypass -File tools\deploy_nuclio.ps1

# 4. Kiểm chứng
powershell -ExecutionPolicy Bypass -File tools\nuclio_status.ps1
python tools/smoke_nuclio.py --function smart-lane --image test/detect/G01_B026.jpg --dump
```

Kỳ vọng ở bước 4: `smart-lane` ở trạng thái `ready`, và smoke test trả về
**polyline** (`type: "polyline"`, `points` là mảng phẳng). Trên `G01_B026` nên
ra 1 polyline `lane/single yellow` quanh toạ độ `(306, 544)`.

Nếu `deploy_nuclio.ps1` báo `Could not resolve host: nuclio` → container
`nuclio` chưa lên, quay lại bước 1.

---

## 3. Lần sau muốn đo lại detector (không cần CVAT, không cần Docker)

```powershell
python work/lane_test/run_lane.py --preview     # bảng tổng hợp + ảnh overlay
python work/lane_test/diagnose.py G01_B026      # từng stage, lý do loại
python work/lane_test/probe.py G01_B026 --depth 5 9   # phổ score/ngưỡng
python work/lane_test/dump_bird.py G01_B026     # bird mask + profile theo depth
```

Ảnh overlay ghi vào `work/lane_test/out/`.

---

## 4. Kết quả đo được (25 ảnh `test/detect`, ~25 ms/ảnh, 0 MiB VRAM)

| Class | marks | frames |
| --- | --- | --- |
| `lane/single white` | 38 | 17/25 |
| `lane/single yellow` | 11 | 6/25 |
| `lane/single other` | 7 | 6/25 |
| `lane/double white` | 0 | 0/25 |
| `lane/double yellow` | 0 | 0/25 |
| `lane/crosswalk` | 0 | 0/25 |
| `lane/road curb` | 0 | 0/25 (mặc định tắt) |

**Precision tốt hơn recall.** Trên khung ban ngày có zebra (`G01_B027`) model
trả về đúng **1** polyline bám vạch trắng, không false positive. Nhưng nó bỏ
sót zebra và nhiều vạch rõ ràng. Đây là công cụ hỗ trợ review, không phải
ground truth.

Ba hạn chế đã đo, ghi rõ trong `nuclio/README.md` mục 7:

1. **Chỉ trace ~40% dưới khung** (`LANE_MAX_DEPTH_M=12`).
2. **`lane/double *` gần như không tách được** — vạch vàng đôi trong `G01_B026`
   được trace *đúng hình học* nhưng gán `lane/single yellow`.
3. **`lane/crosswalk` chưa bắn** — cần thêm một kênh top-hat trung gian ~0.65 m
   (kênh tinh 0.30 m triệt bars, kênh thô 0.85 m gộp chúng lại).

---

## 5. Bài học kỹ thuật quan trọng nhất

**Đây không phải bài toán pixel mà là bài toán đơn vị.** Trong một khung hình
dashcam, cùng một vạch 0.15 m rộng ~40 px ở cách 3 m và ~3 px ở cách 25 m —
`dx/dX = f/Z` đổi hơn 10 lần. Top-hat 21 px **nằm lọt bên trong** vạch gần và
trả về 0, chẻ vạch thành mảnh vụn. Chỉnh ngưỡng không sửa được lỗi này.

Cách sửa: chiếu mặt đường về raster bird's-eye theo **mét** (40 px/m) rồi mới
làm morphology và hình học ở đó. Xem `model-service/handlers/lane.py`, docstring
đầu file.

Hệ quả kéo theo: **depth cap phải theo bird raster, không theo cảm giác.** Ở
Z=20 m, một hàng ảnh giãn thành `(Z²/(f·h))·ppm ≈ 15` hàng bird, biến một pixel
nhiễu chân trời thành blob dài 1 m trông như vạch. Hạ cap 20 → 12 cắt phần lớn
false positive đó.

---

## 6. Nút vặn khi cần chỉnh

Tất cả qua env, không cần sửa code (xem `LaneConfig.from_env`):

| Env | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `LANE_MAX_DEPTH_M` | `12.0` | Tăng → phủ xa hơn nhưng nhiều FP chân trời |
| `LANE_BIRD_PPM` | `40.0` | Độ phân giải bird raster |
| `LANE_CURB_ENABLED` | `false` | Bật detector curb (nhiều FP) |
| `LANE_HORIZON_RATIO` | `0.48` | Hàng chân trời / chiều cao ảnh |
| `LANE_CAMERA_HEIGHT_M` | `1.35` | Chiều cao camera — đo bề rộng chỉ cần số này |

Camera model **giả định**, không calibration: `f = 0.625·W`, `h = 1.35 m`,
chân trời ở `0.48·H`. Nếu ảnh của bạn khác (camera cao/thấp hơn, FOV khác),
chỉnh 3 số này trước tiên — chúng ảnh hưởng trực tiếp tới quyết định
single/double.

---

## 7. Việc còn lại

- [x] Deploy `smart-lane` (mục 2).
- [x] Smoke test qua nuclio, xác minh CVAT nhận `polyline`.
- [x] Thêm dòng `smart-lane` vào bảng smoke test trong `nuclio/README.md` mục 4.
- [x] (dọn dẹp) Xoá `version: "3.8"` khỏi `docker-compose.yml`.
- [ ] (tuỳ chọn) Thêm kênh top-hat ~0.65 m để `lane/crosswalk` bắn được.
- [ ] (tuỳ chọn) `lane_regions` trong `run_results.py` để preview lane trong
      báo cáo batch — hiện `run_results.py` chỉ có bbox + drivable.
- [ ] (kiểm chứng) Chạy auto-annotation thật trong CVAT UI trên một task có label
      `polyline`. Đây là mắt xích **duy nhất chưa chạy thật**; hiện chỉ được
      chứng minh bằng đọc source (`engine/serializers.py:4019` có nhánh POLYLINE
      riêng, và `lambda_manager/views.py:341` chấp nhận label `any` + `polyline`).
