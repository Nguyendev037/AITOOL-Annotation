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
    SEMANTIC_MIN_COMPONENT_AREA=100 \
    ENHANCE_ENABLED=true \
    ENHANCE_DARK_REGIONS=true \
    ENHANCE_MOTION_BLUR=false \
    # Absolute path into the read-only bind mount defined in docker-compose.yml.
    # A bare relative name ("yolo26m.pt") resolves against WORKDIR and therefore
    # lives in the ephemeral writable layer: it is silently lost on every
    # container recreate, which triggers a 42 MB runtime GitHub download that
    # blocks the whole service. Keep this in sync with docker-compose.yml.
    YOLO26_MODEL=/weights/yolo26m.pt \
    YOLO26_CONF=0.25 \
    YOLO26_IOU=0.45 \
    YOLO_CONFIG_DIR=/opt/ultralytics

RUN sed -i 's|http://archive.ubuntu.com/ubuntu|https://archive.ubuntu.com/ubuntu|g' /etc/apt/sources.list \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && apt-get update -o Acquire::Retries=5 \
    && apt-get install -y --no-install-recommends \
    git python3 python3-pip python3-dev libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/sam2
RUN git clone --depth 1 https://github.com/facebookresearch/sam2.git .

# PyTorch layer (heavy, cached)
RUN python3 -m pip install --upgrade pip setuptools wheel \
    && python3 -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124

# Service dependencies
COPY requirements.txt /opt/service-requirements.txt
RUN python3 -m pip install --retries 10 --timeout 120 --no-build-isolation . \
    && python3 -m pip install --retries 10 --timeout 120 -r /opt/service-requirements.txt

# Copy service code
COPY . /opt/service/

# Pre-download semantic model into image
ARG SEMANTIC_MODEL_ID=tue-mps/eomt-dinov3-coco-panoptic-large-640
RUN python3 -c "import os; from transformers import AutoImageProcessor, AutoModelForUniversalSegmentation as M; \
    mid = os.getenv('SEMANTIC_MODEL_ID') or 'tue-mps/eomt-dinov3-coco-panoptic-large-640'; \
    print('Embedding semantic model:', mid); \
    p = AutoImageProcessor.from_pretrained(mid); \
    m = M.from_pretrained(mid); \
    print('OK: params=%.0fM classes=%d' % (sum(t.numel() for t in m.parameters())/1e6, len(m.config.id2label)))" \
    && du -sh /opt/hf-cache \
    && test -d /opt/hf-cache/hub

WORKDIR /opt/service

EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
