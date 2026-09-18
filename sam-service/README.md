# SAM 2.1 Hiera Large service

Đây là service FastAPI chạy trong Docker. Service chỉ chịu trách nhiệm sinh **mask ứng viên**; việc chọn class semantic và quyết định mask thuộc pipeline DeepSeek ở thư mục gốc.

## API

- `GET /`: thông tin service.
- `GET /health`: kiểm tra CUDA, checkpoint và device.
- `POST /segment-auto`: nhận multipart field `image`, trả về kích thước ảnh và danh sách mask PNG base64.
- `POST /segment-semantic`: model semantic đang cấu hình (mặc định EoMT-DINOv3), sau đó SAM2 refine biên object.

## Build và chạy

Build image lần đầu:

```bash
docker build -t sam2-large-service ./sam-service
```

Chạy từ WSL tại thư mục dự án:

```bash
docker run --rm --gpus all -p 8001:8000 --name sam2-large \
	-v /mnt/d/DockerData/Cvat/cvat-browser-agent_v2/sam-service/checkpoints:/models:ro \
	-e SAM2_CONFIG=configs/sam2.1/sam2.1_hiera_l.yaml \
	sam2-large-service
```

Kiểm tra:

```powershell
curl.exe http://127.0.0.1:8001/health
```

## Checkpoint

File `sam2.1_hiera_large.pt` không commit vào image hoặc Git. Đặt file thật tại:

```text
sam-service/checkpoints/sam2.1_hiera_large.pt
```

Docker mount thư mục này thành `/models`. Nếu file thiếu, nhỏ bất thường hoặc hỏng, endpoint `/segment-auto` sẽ trả lỗi dù `/health` vẫn có thể trả `200`.

## Cấu hình

- `SAM2_CONFIG`: mặc định `configs/sam2.1/sam2.1_hiera_l.yaml`.
- `SAM2_CHECKPOINT`: mặc định `/models/sam2.1_hiera_large.pt`.
- `SAM2_DEVICE`: mặc định `cuda`, tự chuyển sang `cpu` nếu CUDA không khả dụng.
- `SEMANTIC_BACKEND`: `eomt` mặc định, `segformer` hoặc `mask2former`.
- `SEMANTIC_MODEL_ID`: model Hugging Face tương ứng; mặc định là `tue-mps/eomt-dinov3-coco-panoptic-large-640`.
- `SEMANTIC_LABELS`: danh sách nhãn phân tách bằng dấu phẩy; nếu bỏ trống, service đọc `id2label` từ checkpoint.

Ví dụ chạy EoMT-DINOv3 panoptic pretrained trên COCO:

```bash
docker run --rm --gpus all -p 8001:8000 --name eomt-service \
	-v "D:\\DockerData\\Cvat\\cvat-browser-agent_v2\\sam-service\\checkpoints:/models:ro" \
	-e SEMANTIC_BACKEND=eomt \
	-e SEMANTIC_MODEL_ID=tue-mps/eomt-dinov3-coco-panoptic-large-640 \
	-e SEMANTIC_REFINE=false \
	sam2-large-service
```

Checkpoint COCO chỉ tạo được các class COCO mà nó đã học. Để segment đủ 31 class của Job 1573, cần fine-tune EoMT với `data.yaml` của dataset và đặt `SEMANTIC_MODEL_ID` vào thư mục checkpoint đã fine-tune.

- `SEMANTIC_REFINE`: `true` để dùng SAM2 refine biên semantic.
- `SEMANTIC_REFINE_MIN_AREA`: diện tích tối thiểu của object để refine, mặc định `500` pixel.
- `SEMANTIC_REFINE_MIN_COVERAGE`: mức class mask phải nằm trong mask SAM, mặc định `0.85`.
- `SEMANTIC_REFINE_MIN_IOU`: IoU tối thiểu giữa class mask và mask SAM, mặc định `0.6`.

Luồng đầy đủ của service được mô tả tại [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).
