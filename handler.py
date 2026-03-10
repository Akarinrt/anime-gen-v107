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

# --- BOOTING WORKER v1.6.6-ULTRA ---
# Focused on: Global Torch Stabilizer (Fix infer_schema) & Multi-Stage Video Gen

WORKER_VERSION = "1.6.6-ultra"

# 0. Global Memory Optimizations
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
os.environ["DIFFUSERS_NO_FLASH_ATTN"] = "1"
os.environ["USE_FLASH_ATTENTION"] = "0"

# 1. Broad Stealth Import Patching (Bypass Flash-Attn)
orig_find_spec = importlib.util.find_spec
def patched_find_spec(name, package=None):
    if name and ("flash_attn" in name or "flash-attn" in name):
        return None
    return orig_find_spec(name, package)
importlib.util.find_spec = patched_find_spec

# 2. NUCLEAR TORCH STABILIZER (Fixes Parameter q / infer_schema errors)
try:
    import torch.library
    def patch_module_infer_schema(mod):
        if hasattr(mod, "infer_schema"):
            orig = mod.infer_schema
            def patched(*args, **kwargs):
                try:
                    return orig(*args, **kwargs)
                except Exception as e:
                    # Return a generic schema instead of crashing
                    return "() -> ()"
            mod.infer_schema = patched
            return True
        return False

    # Patch common locations for this function
    patch_module_infer_schema(torch.library)
    try:
        import torch._library.infer_schema as internal_is
        patch_module_infer_schema(internal_is)
    except: pass
    
    # Even more aggressive: patch any function named infer_schema in sys.modules
    for mname, mod in list(sys.modules.items()):
        if "torch" in mname and mod:
            if hasattr(mod, "infer_schema"):
                patch_module_infer_schema(mod)

    print("--- [ULTRA] Nuclear Torch Stabilizer Applied ---")
except Exception as e:
    print(f"--- [ULTRA] Stabilizer Failed: {e} ---")

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
            print(f"--- [ULTRA] Loading FLUX.1 [schnell] with Sequential Offload ---")
            from diffusers import FluxPipeline
            from transformers import T5EncoderModel, BitsAndBytesConfig, AutoTokenizer
            token = os.getenv("HF_TOKEN") or os.getenv("RUNPOD_HF_TOKEN")
            quant_config = BitsAndBytesConfig(load_in_8bit=True)
            self.t5_tokenizer = AutoTokenizer.from_pretrained("black-forest-labs/FLUX.1-schnell", subfolder="tokenizer_2", token=token)
            self.t5_encoder = T5EncoderModel.from_pretrained(
                "black-forest-labs/FLUX.1-schnell",
                subfolder="text_encoder_2",
                quantization_config=quant_config,
                token=token,
                torch_dtype=torch.float16,
                device_map={"": "cpu"}
            )
            self.flux_pipe = FluxPipeline.from_pretrained(
                "black-forest-labs/FLUX.1-schnell", 
                text_encoder_2=None, 
                torch_dtype=torch.bfloat16,
                token=token
            )
            self.flux_pipe.enable_sequential_cpu_offload()
            print("--- [ULTRA] FLUX Sequential Offload Active ---")

    def load_video(self):
        if self.video_pipe is None:
            print(f"--- [ULTRA] Loading SVD XT with Sequential Offload ---")
            from diffusers import StableVideoDiffusionPipeline
            token = os.getenv("HF_TOKEN") or os.getenv("RUNPOD_HF_TOKEN")
            self.video_pipe = StableVideoDiffusionPipeline.from_pretrained(
                "stabilityai/stable-video-diffusion-img2vid-xt", 
                torch_dtype=torch.float16, variant="fp16",
                token=token
            )
            self.video_pipe.enable_sequential_cpu_offload()
            print("--- [ULTRA] SVD Sequential Offload Active ---")

    def upload_to_tmpfiles(self, file_path):
        print(f"--- [ULTRA] Uploading to tmpfiles.org ---")
        with open(file_path, 'rb') as f:
            r = requests.post('https://tmpfiles.org/api/v1/upload', files={'file': f}, timeout=60)
            return r.json()['data']['url'].replace('https://tmpfiles.org/', 'https://tmpfiles.org/dl/')

    def generate_image(self, prompt):
        try:
            self.load_flux()
            inputs = self.t5_tokenizer(prompt, return_tensors="pt", padding="max_length", max_length=512, truncation=True).to("cpu")
            with torch.no_grad():
                prompt_embeds = self.t5_encoder(inputs.input_ids).last_hidden_state
            del inputs
            image = self.flux_pipe(
                prompt_embeds=prompt_embeds.to(self.flux_pipe.dtype),
                num_inference_steps=4,
                guidance_scale=0.0,
                width=1024,
                height=576,
                generator=torch.Generator("cpu").manual_seed(42)
            ).images[0]
            del prompt_embeds
            temp_path = "/tmp/image.png"
            image.save(temp_path)
            return self.upload_to_tmpfiles(temp_path)
        except Exception as e:
            traceback.print_exc()
            raise e

    def animate_image(self, image_url, prompt):
        try:
            from diffusers.utils import load_image
            self.load_video()
            image = load_image(image_url).resize((1024, 576))
            print(f"--- [ULTRA] Animating Image with SVD ---")
            # Sequential offload handles device moves
            frames = self.video_pipe(image, decode_chunk_size=2, generator=torch.Generator("cpu").manual_seed(42)).frames[0]
            
            temp_path = "/tmp/video.mp4"
            from diffusers.utils import export_to_video
            export_to_video(frames, temp_path, fps=7)
            return self.upload_to_tmpfiles(temp_path)
        except Exception as e:
            traceback.print_exc()
            raise e

    def sync_lips(self, video_url, audio_url):
        print(f"--- [ULTRA] Syncing Lips (Mock Mode) ---")
        return video_url 

# Global instance
gen = None

def handler(event):
    global gen
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    if gen is None:
        gen = VideoGenerator()

    try:
        input_data = event.get('input', {})
        # Be loose with job type extraction
        job_type = input_data.get('type') or event.get('type')
        payload = input_data.get('payload', {}) or event.get('payload', {})
        
        print(f"--- [DEBUG] Handling job type: {job_type} ---")
        
        if job_type == "generate_image":
            url = gen.generate_image(payload.get('prompt'))
            return {"status": "success", "url": url}
            
        elif job_type == "generate_video":
            url = gen.animate_image(payload.get('image_url'), payload.get('prompt'))
            return {"status": "success", "url": url}

        elif job_type == "sync_lips":
            url = gen.sync_lips(payload.get('video_url'), payload.get('audio_url'))
            return {"status": "success", "url": url}
            
        return {"status": "error", "message": f"Worker {WORKER_VERSION}: Invalid job type '{job_type}'"}
    except Exception as e:
        return {"status": "error", "message": f"v1.6.6-ULTRA Crash: {str(e)}"}

print(f"--- RunPod Worker Ready ({WORKER_VERSION}) ---")
runpod.serverless.start({"handler": handler})
