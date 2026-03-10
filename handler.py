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

# --- BOOTING WORKER v1.6.0-ULTRA ---
# Focused on: Extreme Memory Efficiency & Device Mismatch Fixes

WORKER_VERSION = "1.6.0-ultra"

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

# 2. Aggressive Torch Library Signature Patching
try:
    import torch.library
    def apply_infer_patch(module):
        if hasattr(module, "infer_schema"):
            orig = module.infer_schema
            def patched(*args, **kwargs):
                try:
                    return orig(*args, **kwargs)
                except Exception as e:
                    if "unsupported type" in str(e):
                        return "() -> ()"
                    raise e
            module.infer_schema = patched
    apply_infer_patch(torch.library)
except: pass

import runpod

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
            
            # Load T5 on CPU with 8-bit quantization
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
            
            # Load FLUX Pipeline
            self.flux_pipe = FluxPipeline.from_pretrained(
                "black-forest-labs/FLUX.1-schnell", 
                text_encoder_2=None, # We use our local one
                torch_dtype=torch.bfloat16,
                token=token
            )
            
            # NUCLEAR OPTION: Sequential CPU Offload (Layer by Layer)
            # This is slower than enable_model_cpu_offload but MUCH safer for OOM
            self.flux_pipe.enable_sequential_cpu_offload()
            print("--- [ULTRA] FLUX Sequential Offload Active ---")

    def generate_image(self, prompt):
        try:
            self.load_flux()
            
            # Ensure T5 is ready and inputs are on CPU
            print(f"--- [ULTRA] Encoding prompt: {prompt[:50]}... ---")
            inputs = self.t5_tokenizer(prompt, return_tensors="pt", padding="max_length", max_length=512, truncation=True).to("cpu")
            
            with torch.no_grad():
                # T5 remains on CPU
                prompt_embeds = self.t5_encoder(inputs.input_ids).last_hidden_state
                
            # IMPORTANT: Delete inputs to save CPU RAM
            del inputs
            
            print(f"--- [ULTRA] Generating HD Image (16:9 Inference) ---")
            # Device check: pipe will handle moving embeds to GPU when needed 
            # but we can help by ensuring it's at least not on a locked device
            
            image = self.flux_pipe(
                prompt_embeds=prompt_embeds.to(self.flux_pipe.dtype), # Match pipeline dtype
                num_inference_steps=4,
                guidance_scale=0.0,
                width=1024, # HD 16:9approx
                height=576,
                generator=torch.Generator("cpu").manual_seed(42)
            ).images[0]
            
            # Cleanup embeds
            del prompt_embeds
            
            # Catbox/Tmpfiles selection logic (Simplified for handler)
            import requests
            temp_path = "/tmp/image.png"
            image.save(temp_path)
            
            print(f"--- [ULTRA] Uploading to tmpfiles.org ---")
            with open(temp_path, 'rb') as f:
                r = requests.post('https://tmpfiles.org/api/v1/upload', files={'file': f})
                url = r.json()['data']['url'].replace('https://tmpfiles.org/', 'https://tmpfiles.org/dl/')
            
            return url
        except Exception as e:
            print(f"--- [ULTRA ERROR] FLUX: {e} ---")
            traceback.print_exc()
            raise e

    def animate_image(self, image_url, prompt):
        # Implementation for SVD...
        return "https://tmpfiles.org/dl/placeholder_video.mp4"

# Global instance
gen = None

def handler(event):
    global gen
    # Clean cache every job
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    if gen is None:
        gen = VideoGenerator()

    try:
        input_data = event.get('input', {})
        job_type = input_data.get('type', 'generate_image')
        payload = input_data.get('payload', {})
        
        if job_type == "generate_image":
            url = gen.generate_image(payload.get('prompt'))
            return {"status": "success", "url": url}
        
        # Add other types as needed
        return {"status": "error", "message": "Invalid job type"}
    except Exception as e:
        return {"status": "error", "message": f"v1.6.0-ULTRA Crash: {str(e)}"}

print(f"--- RunPod Worker Ready ({WORKER_VERSION}) ---")
runpod.serverless.start({"handler": handler})
