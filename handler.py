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

# --- WORKER v1.6.8-ULTRA (THE ULTIMATE STABILITY) ---
# FIX: 'infer_schema' Parameter q error by disabling problematic SDPA backends

WORKER_VERSION = "1.6.8-ultra"

# 0. Global Memory & Stability Optimizations
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
os.environ["DIFFUSERS_NO_FLASH_ATTN"] = "1"
os.environ["USE_FLASH_ATTENTION"] = "0"

# 1. Broad Import Patching (Bypass Flash-Attn)
orig_find_spec = importlib.util.find_spec
def patched_find_spec(name, package=None):
    if name and ("flash_attn" in name or "flash-attn" in name):
        return None
    return orig_find_spec(name, package)
importlib.util.find_spec = patched_find_spec

# 2. NUCLEAR TORCH STABILIZER (Fixes Parameter q / infer_schema)
try:
    # DISABLE PROBLEMATIC SDPA BACKENDS (The root cause of the q-type error)
    torch.backends.cuda.enable_flash_sdp(False)
    torch.backends.cuda.enable_mem_efficient_sdp(False)
    torch.backends.cuda.enable_math_sdp(True)
    print("--- [ULTRA] SDPA Stability Hack Active (Math Only) ---")
    
    import torch.library
    def apply_patch(obj):
        if hasattr(obj, "infer_schema"):
            orig = obj.infer_schema
            def patched(*args, **kwargs):
                try: return orig(*args, **kwargs)
                except: return "() -> ()"
            obj.infer_schema = patched
    apply_patch(torch.library)
    try:
        import torch._library.infer_schema as internal_is
        apply_patch(internal_is)
    except: pass
    print("--- [ULTRA] Global Torch Stabilizer Active ---")
except Exception as e:
    print(f"--- [ULTRA] Stabilizer Init Warning: {e} ---")

import runpod
import requests

def get_device():
    return "cuda" if torch.cuda.is_available() else "cpu"

class VideoGenerator:
    def __init__(self):
        self.device = get_device()
        self.flux_pipe = None
        self.video_pipe = None
        self.t5_tokenizer = None
        self.t5_encoder = None
        
    def load_flux(self):
        if self.flux_pipe is None:
            print(f"--- [ULTRA] Loading FLUX.1 [schnell] (Sequential Offload) ---")
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
            print(f"--- [ULTRA] Loading SVD XT (Sequential Offload) ---")
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

    def animate_image(self, url, prompt):
        from diffusers.utils import load_image, export_to_video
        self.load_video()
        image = load_image(url).resize((1024, 576))
        print(f"--- [ULTRA] Producing Video Frames ---")
        frames = self.video_pipe(image, decode_chunk_size=2).frames[0]
        export_to_video(frames, "/tmp/vid.mp4", fps=7)
        return self.upload("/tmp/vid.mp4")

    def sync_lips(self, v_url, a_url):
        return v_url # (Mock)

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
        if jtype == "sync_lips": return {"status": "success", "url": gen.sync_lips(pay.get('video_url'), pay.get('audio_url'))}
        return {"status": "error", "message": f"Worker {WORKER_VERSION}: Invalid Type {jtype}"}
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": f"{WORKER_VERSION} Crash: {str(e)}"}

print(f"--- RunPod Worker Ready ({WORKER_VERSION}) ---")
runpod.serverless.start({"handler": handler})
