# Use a newer RunPod PyTorch base image (PyTorch 2.4.0 + CUDA 12.4)
FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

# Set working directory
WORKDIR /

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsndfile1 \
    build-essential \
    python3-dev \
    git \
    -y && rm -rf /var/lib/apt/lists/*

# --- THE KEY FIX ---
# Uninstall flash-attn and force-remove any cached versions to avoid infer_schema conflict
RUN python3.11 -m pip uninstall flash-attn -y || true
RUN rm -rf /usr/local/lib/python3.11/dist-packages/flash_attn* || true
RUN python3.11 -m pip cache purge

# Copy requirements
COPY requirements.txt .

# Install dependencies
RUN python3.11 -m pip install --no-cache-dir --upgrade pip && \
    python3.11 -m pip install --no-cache-dir --prefer-binary -r requirements.txt

# Copy source code
COPY handler.py .

# Command to run using python3.11
CMD [ "python3.11", "-u", "handler.py" ]
