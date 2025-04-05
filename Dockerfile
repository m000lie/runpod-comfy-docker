# Stage 1: Base image with common dependencies
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04 as base

# Prevents prompts from packages asking for user input during installation
ENV DEBIAN_FRONTEND=noninteractive
# Prefer binary wheels over source distributions for faster pip installations
ENV PIP_PREFER_BINARY=1
# Ensures output from python is printed immediately to the terminal without buffering
ENV PYTHONUNBUFFERED=1 
# Speed up some cmake builds
ENV CMAKE_BUILD_PARALLEL_LEVEL=8

# Install Python, git and other necessary tools
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    git \
    wget \
    libgl1 \
    && ln -sf /usr/bin/python3.10 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip

# Clean up to reduce image size
RUN apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Copy requirements file and runpod package
COPY requirements.txt /requirements.txt
COPY runpod-1.7.8-CUSTOM.tar.gz /runpod.tar.gz

# Install requirements, runpod, and comfy-cli
RUN pip install --upgrade pip setuptools wheel
RUN pip install /runpod.tar.gz
RUN pip install comfy-cli

# Install ComfyUI
RUN /usr/bin/yes | comfy --workspace /comfyui install --cuda-version 11.8 --nvidia --version 0.3.26

# Change working directory to ComfyUI
WORKDIR /comfyui

# Install CUSTOM runpod & requests
RUN pip install requests
RUN pip install -r requirements.txt

# Support for the network volume
ADD src/extra_model_paths.yaml ./

# Go back to the root
WORKDIR /

# Add scripts
ADD src/start.sh src/restore_snapshot.sh src/rp_handler.py test_input.json ./
RUN chmod +x /start.sh /restore_snapshot.sh

# Optionally copy the snapshot file
ADD *snapshot*.json /

# Restore the snapshot to install custom nodes
RUN /restore_snapshot.sh

# Start container
CMD ["/start.sh"]

# Stage 2: Download models
FROM base as downloader

# ARG HUGGINGFACE_ACCESS_TOKEN
# ARG MODEL_TYPE

# Change working directory to ComfyUI
WORKDIR /comfyui

# Create necessary directories
RUN mkdir -p models/vae models/unet models/text_encoders models/clip_vision models/checkpoints models/loras

# Copy local LORA files
RUN wget -O models/loras/ultra_realistic_v1.safetensors https://civitai.com/api/download/models/890545?type=Model&format=SafeTensor
RUN wget -O models/loras/phlux.safetensors https://civitai.com/api/download/models/753339?type=Model&format=SafeTensor
RUN wget -O models/loras/iphone_photo_v2_15000s.safetensors https://civitai.com/api/download/models/967140?type=Model&format=SafeTensor
# temporary link for amateur_v6
RUN wget -O models/loras/amateur_v6.safetensors https://l.station307.com/4oWYVDb5vJUh1C9T5xeyzo/amateurphoto-v6-forcu.safetensors

# Download checkpoints/vae/LoRA to include in image based on model type
RUN wget -O models/unet/wan2.1_i2v_480p_14B_fp8_e4m3fn.safetensors https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_i2v_480p_14B_fp8_e4m3fn.safetensors
RUN wget -O models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors
RUN wget -O models/clip_vision/clip_vision_h.safetensors https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors
RUN wget -O models/vae/wan_2.1_vae.safetensors https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors
# RUN wget -O models/checkpoints/RealVisXL_V5.0_Lightning_fp32.safetensors https://huggingface.co/SG161222/RealVisXL_V5.0_Lightning/resolve/main/RealVisXL_V5.0_Lightning_fp32.safetensors
# files for inference fp16
RUN wget -O models/text_encoders/t5xxl_fp16.safetensors https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors
RUN wget -O models/text_encoders/clip_l.safetensors https://huggingface.co/Comfy-Org/stable-diffusion-3.5-fp8/resolve/main/text_encoders/clip_l.safetensors
RUN wget -O models/unet/flux1-dev.safetensors https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors
RUN wget -O models/vae/flux-ae.safetensors https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/ae.safetensors 
# files for training lora fp8
RUN wget -O models/text_encoders/t5xxl_fp8_e4m3fn.safetensors https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors
RUN wget -O models/unet/flux1-dev-fp8-e4m3fn.safetensors https://huggingface.co/Kijai/flux-fp8/resolve/main/flux1-dev-fp8-e4m3fn.safetensors
# Stage 3: Final image
FROM base as final

# Copy models from stage 2 to the final image
COPY --from=downloader /comfyui/models /comfyui/models

# Start container
CMD ["/start.sh"]