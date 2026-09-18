FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache \
    SAM2_DEVICE=cuda \
    SAM2_CONFIG=configs/sam2.1/sam2.1_hiera_l.yaml \
    SAM2_CHECKPOINT=/models/sam2.1_hiera_large.pt \
    SEMANTIC_BACKEND=eomt \
    SEMANTIC_MODEL_ID=tue-mps/eomt-dinov3-coco-panoptic-large-640 \
    SEMANTIC_REFINE=true \
    SEMANTIC_REFINE_MIN_AREA=500 \
    SEMANTIC_REFINE_MIN_COVERAGE=0.85 \
    SEMANTIC_REFINE_MIN_IOU=0.6 \
    SEMANTIC_SPLIT_INSTANCES=true \
    SEMANTIC_MIN_COMPONENT_AREA=100

RUN sed -i 's|http://archive.ubuntu.com/ubuntu|https://archive.ubuntu.com/ubuntu|g' /etc/apt/sources.list \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && apt-get update -o Acquire::Retries=5 \
    && apt-get install -y --no-install-recommends \
    git python3 python3-pip python3-dev libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/sam2
RUN git clone --depth 1 https://github.com/facebookresearch/sam2.git .

# Layer riêng cho PyTorch: nặng (~5GB) và ít khi đổi, nhờ vậy các lần rebuild sau
# chỉ phải cài lại dependencies của service thay vì tải lại toàn bộ PyTorch.
RUN python3 -m pip install --upgrade pip setuptools wheel \
    && python3 -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124

# Layer riêng cho SAM2 + service requirements. Đặt SAU PyTorch và SAU khi COPY
# requirements.txt để mọi thay đổi requirements đều buộc cài lại đầy đủ.
COPY requirements.txt /opt/service-requirements.txt
RUN python3 -m pip install --retries 10 --timeout 120 --no-build-isolation . \
    && python3 -m pip install --retries 10 --timeout 120 -r /opt/service-requirements.txt \
    && python3 -c "import importlib.util as u, sys; missing=[m for m in ('scipy','numpy','torch','fastapi','uvicorn','PIL','multipart','transformers','sam2') if u.find_spec(m) is None]; sys.exit('THIEU THU VIEN: ' + ', '.join(missing)) if missing else print('OK: tat ca thu vien bat buoc deu co mat')"

COPY app.py /opt/service/app.py
COPY train_eomt.py /opt/service/train_eomt.py

# Nhúng sẵn model semantic (EoMT-DINOv3) vào image để chạy OFFLINE hoàn toàn.
# Mọi thứ được tải vào HF_HOME=/opt/hf-cache ngay lúc build; khi chạy container
# không cần internet, chỉ cần đặt HF_HUB_OFFLINE=1 / TRANSFORMERS_OFFLINE=1.
# Đặt SAU layer requirements để đổi model không phải cài lại thư viện.
ARG SEMANTIC_MODEL_ID=tue-mps/eomt-dinov3-coco-panoptic-large-640
RUN python3 -c "import os; from transformers import AutoImageProcessor, AutoModelForUniversalSegmentation as M; \
    mid = os.getenv('SEMANTIC_MODEL_ID') or 'tue-mps/eomt-dinov3-coco-panoptic-large-640'; \
    print('Dang nhung model semantic:', mid); \
    p = AutoImageProcessor.from_pretrained(mid); \
    m = M.from_pretrained(mid); \
    print('OK: model semantic da nam trong image | so tham so: %.0fM | so class: %d' % (sum(t.numel() for t in m.parameters())/1e6, len(m.config.id2label)))" \
    && du -sh /opt/hf-cache \
    && test -d /opt/hf-cache/hub

WORKDIR /opt/service

EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
