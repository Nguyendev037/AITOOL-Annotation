# Quy trình train model (segmentation + bbox detection)

## Mục tiêu

Dùng dataset segmentation của từng batch/project để fine-tune model semantic chính. Không phụ thuộc một ảnh cố định, một Job cố định hoặc mapping Cityscapes mặc định.

Luồng chuẩn:

```text
Dataset YOLO segmentation
        -> kiểm tra data.yaml và class order
        -> rasterize polygon thành semantic mask
        -> chia train/validation/test theo sequence hoặc scene
        -> fine-tune EoMT-DINOv3 / SegFormer / Mask2Former
        -> đánh giá mIoU/per-class IoU
        -> export checkpoint
        -> service semantic model
        -> SAM2 refine biên object
```

## 1. Chuẩn bị dataset

Dataset phải có:

```text
dataset/
  data.yaml
  train.txt
  images/train/...
  labels/train/...
  images/val/...
  labels/val/...
```

`data.yaml` là nguồn sự thật cho class name và class ID. Không tự áp thứ tự Cityscapes. Dataset hiện tại của Job 1573 có 31 class, gồm object, vùng đường và lane marking.

Mỗi file YOLO segmentation có dạng:

```text
<class_id> x1 y1 x2 y2 ... xn yn
```

Tọa độ được chuẩn hóa trong khoảng `0..1`. Polygon phải được rasterize theo đúng kích thước ảnh trước khi train.

## 2. Quy tắc chia dữ liệu

Không chia ngẫu nhiên các frame liền nhau giữa train và validation nếu chúng thuộc cùng một đoạn video. Cách khuyến nghị:

- train: 70%
- validation: 20%
- test: 10%

Chia theo sequence/scene/camera trước, rồi mới lấy ảnh. Giữ test set không đụng vào trong quá trình train.

Nếu chỉ có một batch nhỏ, dùng validation để phát hiện lỗi mapping nhưng không xem đó là chất lượng tổng quát. Cần bổ sung nhiều scene, thời tiết, góc camera và mật độ giao thông.

## 3. Chọn model

### SegFormer

Dùng khi cần model semantic gọn, inference nhanh và mỗi pixel thuộc một class. Đây là lựa chọn mặc định cho service hiện tại.

- Model khởi đầu: `nvidia/segformer-b5-finetuned-cityscapes-1024-1024`
- Thay classification head bằng số class trong `data.yaml`.
- Không giữ nguyên `id2label` Cityscapes nếu class order của dataset khác.

### Mask2Former

Dùng khi cần biên và vùng phức tạp tốt hơn, chấp nhận VRAM và thời gian inference cao hơn.

- Model khởi đầu phải hỗ trợ semantic segmentation.
- Thay head theo đúng số class dataset.
- Kiểm tra `post_process_semantic_segmentation` trả class ID đúng mapping.

### EoMT-DINOv3

EoMT dùng `AutoModelForUniversalSegmentation` và có thể fine-tune từ checkpoint
panoptic COCO. Trainer trong `sam-service/train_eomt.py` đọc trực tiếp polygon
YOLO, gom polygon cùng class thành một mask và xuất checkpoint tương thích với
service.

Kiểm tra dữ liệu trước khi train:

```powershell
python sam-service/train_eomt.py `
  --dataset datasets/job_1573/reference `
  --output work/models/job_1573-eomt `
  --dry-run
```

Môi trường training cần thêm các package trong
`sam-service/training-requirements.txt`. Với GPU NVIDIA, cài PyTorch theo
CUDA version của máy thay vì dùng wheel CPU mặc định:

```powershell
python -m pip install -r sam-service/training-requirements.txt
```

Huấn luyện sau khi đã có đủ annotation:

```powershell
python sam-service/train_eomt.py `
  --dataset datasets/job_1573/reference `
  --output work/models/job_1573-eomt `
  --base-model tue-mps/eomt-dinov3-coco-panoptic-large-640 `
  --epochs 30 `
  --batch-size 1
```

Không coi checkpoint đạt chất lượng khi chỉ có một vài ảnh hoặc chỉ có train
loss. Cần giữ validation theo scene/sequence và xem mIoU từng class trước khi
đưa checkpoint vào service.

## 4. Train

Việc train phải chạy trong môi trường có PyTorch, Transformers và GPU. Không train bằng checkpoint SAM2; SAM2 là model refine/prompt, không phải semantic classifier của dataset.

Các giá trị khởi đầu nên thử:

```text
learning_rate: 5e-5
batch_size: 2-8 tùy VRAM
epochs: 20-80
image_size: giữ tỉ lệ, tối đa theo VRAM
weight_decay: 0.01
mixed_precision: fp16 hoặc bf16 nếu GPU hỗ trợ
```

Theo dõi:

- validation loss
- mean IoU
- IoU từng class
- pixel accuracy
- confusion matrix

Không chọn checkpoint chỉ theo loss. Với bài toán này, cần xem riêng `car`, `pedestrian/person`, `road`, `sidewalk`, lane classes và object nhỏ.

## 5. Đánh giá trước khi đưa vào service

> Ghi chú: client `app.main` (kiến trúc cũ) đã bị gỡ bỏ. Việc đánh giá IoU hiện thực hiện bằng script riêng đối chiếu polygon YOLO trong `datasets/job_1573/reference` với mask từ `/segment-semantic` (hoặc detection từ `/detect`) — không còn lệnh `--evaluate-dataset`.

Evaluator cần:

- kiểm tra ảnh reference có trùng ảnh CVAT bằng hash;
- đọc class từ `data.yaml`;
- rasterize polygon YOLO;
- tính IoU theo class;
- không dùng mapping Cityscapes để đánh giá.

Chỉ thay model service khi:

- class mapping đúng;
- test image/label pair đúng;
- không có class bị lệch ID;
- mIoU và IoU các class quan trọng đạt ngưỡng do batch đặt ra;
- đã xem trực quan các mask ở nhiều ảnh.

## 6. Đưa checkpoint vào service

Checkpoint semantic phải được tách khỏi image Docker, tương tự checkpoint SAM2:

```text
models/
  semantic/
    config.json
    model.safetensors hoặc pytorch_model.bin
```

Cấu hình service:

```dotenv
SEMANTIC_BACKEND=segformer
SEMANTIC_MODEL_ID=/models/semantic/job_1573
SEMANTIC_REFINE=true
```

Với checkpoint EoMT đã fine-tune:

```dotenv
SEMANTIC_BACKEND=eomt
SEMANTIC_MODEL_ID=/models/semantic/job_1573-eomt
SEMANTIC_REFINE=false
```

Nếu train lại batch khác, chỉ đổi `SEMANTIC_MODEL_ID` và class metadata tương ứng; không sửa code theo từng ảnh.

## 7. Vai trò của SAM2 và DeepSeek

- SegFormer/Mask2Former: tạo class cho từng pixel.
- SAM2: refine biên object khi prompt và điều kiện tin cậy đủ tốt.
- DeepSeek: tùy chọn review semantic, giải thích vùng mơ hồ, phát hiện mask sai class hoặc reflection/shadow.
- Browser-use: điều khiển CVAT, refresh và xác nhận trực quan.

DeepSeek không nên là model tạo pixel mask chính. Token/vision reasoning có thể giúp chọn và kiểm tra, nhưng không đảm bảo boundary pixel-level ổn định như model segmentation chuyên dụng.

Bật review DeepSeek:

```dotenv
DEEPSEEK_SEGMENT_REVIEW=true
```

Tắt để chạy deterministic, tiết kiệm token:

```dotenv
DEEPSEEK_SEGMENT_REVIEW=false
```

## 8. Dataset cho project bất kỳ

Mỗi project/batch nên có thư mục riêng:

```text
datasets/
  project_a/
    reference/
    model/
  project_b/
    reference/
    model/
```

Không đặt class list cố định trong code. Service cần đọc metadata class cùng checkpoint. Nếu dataset có class khác, phải train head mới hoặc dùng checkpoint đã fine-tune cho đúng dataset.

---

## 9. Fine-tune YOLO26 cho BBox detection

Fine-tune YOLO26 (object detection) tách biệt hoàn toàn với pipeline segmentation. Script đặt tại `work/bbox_train/`:

```text
work/bbox_train/
  prepare_dataset.py        # chuẩn hoá label bbox -> 10 class guideline, chia train/val
  train_yolo26.py           # gọi ultralytics model.train trên GPU
  run_test_inference.py     # inference so sánh base vs fine-tuned trên test/detect
  outputs/yolo26m_bbox_1354_best.pt
```

Luồng:

```powershell
# 1. Chuẩn hoá dataset (remap alias 29->8, 30->9 về class guideline)
python work/bbox_train/prepare_dataset.py

# 2. Đưa vào container và train (Docker + CUDA)
docker cp work/bbox_train/dataset cvat-smart-model:/opt/bbox_train/dataset
docker cp work/bbox_train/train_yolo26.py cvat-smart-model:/opt/bbox_train/train_yolo26.py
docker exec cvat-smart-model python3 /opt/bbox_train/train_yolo26.py

# 3. Lấy weights về
docker cp cvat-smart-model:/opt/bbox_train/runs/yolo26m_bbox_1354/weights/best.pt work/bbox_train/outputs/yolo26m_bbox_1354_best.pt
```

Lưu ý:

- **10 class guideline** (không phải 80 class COCO): `pedestrian, rider, car, truck, bus, train, motorcycle, bicycle, traffic light, traffic sign`.
- Base weights `yolo26m.pt` đã cache tại `/opt/service/yolo26m.pt` trong container.
- Dùng `workers=0` nếu container có `/dev/shm` nhỏ (64 MB) để tránh lỗi shared memory của DataLoader.
- Với dataset nhỏ (vài chục ảnh), model dễ overfit sau vài epoch — dùng `patience` và theo dõi mAP validation. Kết quả thực tế trên `train/1354` (25 ảnh): best epoch 4, mAP50 ≈ 0.40, model fine-tune **không vượt** base pretrained về recall (xem `results/bbox_finetune_report.md`).

`handlers/detect.py` đã hỗ trợ cả 2 dạng class đầu ra (COCO → map guideline, hoặc guideline trực tiếp từ model fine-tune), nên có thể chuyển bằng biến môi trường `YOLO26_MODEL` mà không sửa code.
