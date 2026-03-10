import os
import sys
import types
import builtins
import importlib.util
from unittest.mock import MagicMock
import urllib.request
import traceback
import gc
import torch
import base64
import io

# --- WORKER v1.7.0-ULTRA (OMNILOADER) ---
# FIX: Handle remote URLs, local paths, and Base64 with detailed diagnostics

WORKER_VERSION = "1.8.0-ultra"

# 0. Stability Optimizations
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
os.environ["DIFFUSERS_NO_FLASH_ATTN"] = "1"
os.environ["USE_FLASH_ATTENTION"] = "0"

# Broad patching to ensure stability
try:
    torch.backends.cuda.enable_flash_sdp(False)
    torch.backends.cuda.enable_mem_efficient_sdp(False)
    torch.backends.cuda.enable_math_sdp(True)
    import torch.library
    def apply_patch(obj):
        if hasattr(obj, "infer_schema"):
            orig = obj.infer_schema
            def patched(*args, **kwargs):
                try: return orig(*args, **kwargs)
                except: return "() -> ()"
            obj.infer_schema = patched
    apply_patch(torch.library)
except: pass

import runpod
import requests
from PIL import Image

def robust_load_image(image_input):
    """Ultimate image loader for URLs, Paths, and Base64."""
    from diffusers.utils import load_image
    
    if not image_input:
        raise ValueError("Image input is empty")

    print(f"--- [ULTRA] Attempting to load image from: {str(image_input)[:100]}... ---")
    
    # 1. Handle non-strings (already a PIL image or similar)
    if not isinstance(image_input, str):
        return load_image(image_input).convert("RGB")
    
    # 2. Handle Base64
    if len(image_input) > 500 or image_input.startswith("iVBORw"):
        try:
            print("--- [DEBUG] Decoding Base64... ---")
            img_data = base64.b64decode(image_input)
            return Image.open(io.BytesIO(img_data)).convert("RGB")
        except Exception as e:
            print(f"--- [DEBUG] Base64 decode failed: {e} ---")

    # 3. Handle URLs or Local Paths
    try:
        # We manually use requests for better error reporting if it's a URL
        if image_input.startswith("http"):
            print("--- [DEBUG] Fetching remote image URL... ---")
            resp = requests.get(image_input, timeout=30)
            resp.raise_for_status()
            # Log content type
            print(f"--- [DEBUG] Content-Type: {resp.headers.get('Content-Type')} ---")
            if "text/html" in resp.headers.get('Content-Type', ''):
                print("--- [WARNING] Received HTML instead of image. URL might be a view link, not DL link. ---")
            return Image.open(io.BytesIO(resp.content)).convert("RGB")
        else:
            return load_image(image_input).convert("RGB")
    except Exception as e:
        print(f"--- [ERROR] robust_load_image failed for string input: {e} ---")
        raise e

class VideoGenerator:
    def __init__(self):
        self.flux_pipe = None
        self.video_pipe = None
        self.t5_tokenizer = None
        self.t5_encoder = None
        
    def unload_flux(self):
        if self.flux_pipe is not None:
            print("--- [ULTRA] Purging FLUX from VRAM ---")
            del self.flux_pipe
            del self.t5_encoder
            del self.t5_tokenizer
            self.flux_pipe = None
            self.t5_encoder = None
            self.t5_tokenizer = None
            gc.collect()
            torch.cuda.empty_cache()

    def unload_video(self):
        if self.video_pipe is not None:
            print("--- [ULTRA] Purging SVD from VRAM ---")
            del self.video_pipe
            self.video_pipe = None
            gc.collect()
            torch.cuda.empty_cache()

    def load_flux(self):
        if self.flux_pipe is None:
            self.unload_video()
            print(f"--- [ULTRA] Loading FLUX.1 (Schnell) ---")
            from diffusers import FluxPipeline
            from transformers import T5EncoderModel, BitsAndBytesConfig, AutoTokenizer
            token = os.getenv("HF_TOKEN") or os.getenv("RUNPOD_HF_TOKEN")
            quant_config = BitsAndBytesConfig(load_in_8bit=True)
            self.t5_tokenizer = AutoTokenizer.from_pretrained("black-forest-labs/FLUX.1-schnell", subfolder="tokenizer_2", token=token)
            self.t5_encoder = T5EncoderModel.from_pretrained(
                "black-forest-labs/FLUX.1-schnell", subfolder="text_encoder_2",
                quantization_config=quant_config, token=token, torch_dtype=torch.float16, device_map={"": "cpu"}
            )
            self.flux_pipe = FluxPipeline.from_pretrained("black-forest-labs/FLUX.1-schnell", text_encoder_2=None, torch_dtype=torch.bfloat16, token=token)
            self.flux_pipe.enable_sequential_cpu_offload()

    def load_video(self):
        if self.video_pipe is None:
            self.unload_flux()
            print(f"--- [ULTRA] Loading SVD XT ---")
            from diffusers import StableVideoDiffusionPipeline
            token = os.getenv("HF_TOKEN") or os.getenv("RUNPOD_HF_TOKEN")
            self.video_pipe = StableVideoDiffusionPipeline.from_pretrained("stabilityai/stable-video-diffusion-img2vid-xt", torch_dtype=torch.float16, variant="fp16", token=token)
            self.video_pipe.enable_sequential_cpu_offload()

    def upload(self, path):
        with open(path, 'rb') as f:
            res = requests.post('https://tmpfiles.org/api/v1/upload', files={'file': f}, timeout=60).json()
            return res['data']['url'].replace('https://tmpfiles.org/', 'https://tmpfiles.org/dl/')

    def generate_image(self, prompt):
        self.load_flux()
        tokens = self.t5_tokenizer(prompt, return_tensors="pt", padding="max_length", max_length=512, truncation=True).to("cpu")
        with torch.no_grad(): embeds = self.t5_encoder(tokens.input_ids).last_hidden_state
        img = self.flux_pipe(prompt_embeds=embeds.to(self.flux_pipe.dtype), num_inference_steps=4, guidance_scale=0.0, width=1024, height=576).images[0]
        img.save("/tmp/img.png")
        return self.upload("/tmp/img.png")

    def animate_image(self, input_data, prompt):
        from diffusers.utils import export_to_video
        self.load_video()
        image = robust_load_image(input_data).resize((1024, 576))
        print(f"--- [ULTRA] Producing Video Frames (Safe Mode) ---")
        # Use decode_chunk_size=1 and slightly lower motion bucket for stability
        frames = self.video_pipe(image, decode_chunk_size=1, motion_bucket_id=100, noise_aug_strength=0.1).frames[0]
        export_to_video(frames, "/tmp/vid.mp4", fps=7)
        return self.upload("/tmp/vid.mp4")


gen = None
def handler(event):
    global gen
    gc.collect()
    if torch.cuda.is_available(): torch.cuda.empty_cache()
    if gen is None: gen = VideoGenerator()
    try:
        inp = event.get('input', {})
        jtype = inp.get('type') or event.get('type')
        pay = inp.get('payload', {}) or event.get('payload', {})
        print(f"--- [DEBUG] Job type: {jtype} ({WORKER_VERSION}) ---")
        if jtype == "generate_image": return {"status": "success", "url": gen.generate_image(pay.get('prompt'))}
        if jtype == "generate_video": return {"status": "success", "url": gen.animate_image(pay.get('image_url'), pay.get('prompt'))}
        return {"status": "error", "message": f"Worker {WORKER_VERSION}: Invalid Type {jtype}"}
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": f"{WORKER_VERSION} Crash: {str(e)}"}

print(f"--- RunPod Worker Ready ({WORKER_VERSION}) ---")
runpod.serverless.start({"handler": handler})
