# Stage 1: Base image with common dependencies
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

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
    ffmpeg \
    && ln -sf /usr/bin/python3.10 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip

# Clean up to reduce image size
RUN apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Copy requirements file and runpod package
COPY runpod-1.7.8-CUSTOM.tar.gz /runpod.tar.gz
COPY requirements.txt /requirements.txt

# Install requirements, runpod, and comfy-cli
# https://stackoverflow.com/questions/62786028/importerror-libgthread-2-0-so-0-cannot-open-shared-object-file-no-such-file-o
RUN apt-get update
RUN apt-get install -y libglib2.0-0 libsm6 libxrender1 libxext6 # required for opencv 
RUN pip install --upgrade pip setuptools wheel
RUN pip install /runpod.tar.gz
RUN pip install -r /requirements.txt
RUN pip install comfy-cli

# Install ComfyUI
RUN /usr/bin/yes | comfy --workspace /comfyui install --cuda-version 11.8 --nvidia --version 0.3.26

# Change working directory to ComfyUI
WORKDIR /comfyui

# Create models directory structure
RUN mkdir -p models/vae models/unet models/text_encoders models/clip_vision models/checkpoints models/loras

# Copy local model files
# COPY models/loras/UltraRealPhoto.safetensors models/loras/ultra_real_photo.safetensors
# COPY models/loras/Phlux.safetensors models/loras/phlux.safetensors
# COPY models/loras/iphone-photo-V2-15000s.safetensors models/loras/iphone-photo-V2-15000s.safetensors
# COPY models/loras/amateurphoto-v6-forcu.safetensors models/loras/amateur_v6.safetensors
COPY models/unet/wan2.1_i2v_480p_14B_fp8_e4m3fn.safetensors models/unet/wan2.1_i2v_480p_14B_fp8_e4m3fn.safetensors
COPY models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors
COPY models/clip_vision/clip_vision_h.safetensors models/clip_vision/clip_vision_h.safetensors
COPY models/vae/wan_2.1_vae.safetensors models/vae/wan_2.1_vae.safetensors
# COPY models/text_encoders/t5xxl_fp16.safetensors models/text_encoders/t5xxl_fp16.safetensors
# COPY models/text_encoders/clip_l.safetensors models/text_encoders/clip_l.safetensors
# COPY models/unet/flux1-dev.safetensors models/unet/flux1-dev.safetensors
# COPY models/vae/ae.safetensors models/vae/flux-ae.safetensors
# COPY models/text_encoders/t5xxl_fp8_e4m3fn.safetensors models/text_encoders/t5xxl_fp8_e4m3fn.safetensors
# COPY models/unet/flux1-dev-fp8-e4m3fn.safetensors models/unet/flux1-dev-fp8-e4m3fn.safetensors
COPY models/loras/I2V-tittydrop-e26.safetensors models/loras/tittydrop.safetensors
COPY models/loras/wan_tittydrop_v1_t2v_14b.safetensors models/loras/wan_tittydrop_v1_t2v_14b.safetensors
COPY models/loras/pov_blowjob_v1.1.safetensors models/loras/pov_blowjob_v1.1.safetensors
COPY models/loras/wan_cowgirl_v1.2.safetensors models/loras/wan_cowgirl_v1.2.safetensors
COPY models/loras/wan_pov_missionary_i2v_v1.1.safetensors models/loras/wan_pov_missionary_i2v_v1.1.safetensors
COPY models/loras/facials_epoch_50.safetensors models/loras/facials_epoch_50.safetensors
COPY models/loras/wan_cumshot_i2v.safetensors models/loras/wan_cumshot_i2v.safetensors

# Install CUSTOM runpod & requests
RUN pip install requests

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
