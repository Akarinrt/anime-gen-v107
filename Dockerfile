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

# --- PRE-CACHE MODELS AT BUILD TIME ---
# To prevent "No space left on device" or "Background writer closed" during runtime,
# we download the models directly into the Docker image.
# We use build arguments for HF_TOKEN to allow access to gated models (like FLUX-schnell).
ARG HF_TOKEN
ENV HF_TOKEN=$HF_TOKEN
ENV HF_HUB_ENABLE_HF_TRANSFER=1

# Install hf_transfer for much faster and more reliable downloads
RUN python3.11 -m pip install hf_transfer

# Pre-download FLUX.1-schnell
RUN huggingface-cli download black-forest-labs/FLUX.1-schnell --token $HF_TOKEN || echo "Failed to cache FLUX, will try at runtime."

# Pre-download Stable Video Diffusion XT
RUN huggingface-cli download stabilityai/stable-video-diffusion-img2vid-xt-1-1 --token $HF_TOKEN || echo "Failed to cache SVD, will try at runtime."

# Pre-download T5 Encoder explicitly (often the cause of writer errors)
RUN huggingface-cli download google/t5-v1_1-xxl --token $HF_TOKEN || echo "Failed to cache T5, will try at runtime."

# Command to run using python3.11
CMD [ "python3.11", "-u", "handler.py" ]
