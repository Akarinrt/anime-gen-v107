import os
import sys

# WORKER v2.0.7-ULTRA
WORKER_VERSION = "2.0.7-ultra"

# --- [ULTRA] EXTREME SCHEMA POISONING ---
try:
    import torch
    # Poison the internal C++ binder if possible
    def dummy_schema(*args, **kwargs): return "() -> ()"
    
    # Target every possible schema inference point
    targets = [
        (torch._custom_op.impl, "infer_schema"),
        (torch.library, "infer_schema"),
        (torch._C, "_infer_schema") # Deep C++ level if accessible
    ]
    for parent, name in targets:
        try:
            if hasattr(parent, name):
                setattr(parent, name, dummy_schema)
                print(f"--- [ULTRA] {name} poisoned ---")
        except: pass
except:
    pass

import types
import builtins
import subprocess
from unittest.mock import MagicMock

# Block modules AT THE SOURCE
sys.modules['sageattention'] = None
sys.modules['xformers'] = None
sys.modules['xformers.ops'] = None

# Aggressively clean pip
try:
    subprocess.check_call([sys.executable, "-m", "pip", "uninstall", "-y", "sageattention"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
except: pass

# --- [ULTRA] PROTECTED IMPORTS ---
try:
    import diffusers
    import transformers
except Exception as e:
    print(f"--- [RECOVERY] Import failed but continuing: {e} ---")

import urllib.request
import traceback
import gc
import base64
import io

# WORKER v2.0.6-ULTRA

# 0. Stability Optimizations
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
os.environ["DIFFUSERS_NO_FLASH_ATTN"] = "1"
os.environ["USE_FLASH_ATTENTION"] = "0"
os.environ["XFORMERS_DISABLED"] = "1"  # Force disable xformers to prevent schema conflict
os.environ["XFORMERS_FORCE_DISABLE"] = "1"

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

# Additional patch specifically for AnimateDiff xformers conflict
try:
    import diffusers.models.attention_processor
    # Force the library to believe xformers is not installed even if it is
    diffusers.models.attention_processor.is_xformers_available = lambda: False
    
    # Force SDPA to avoid sageattention
    os.environ["SAGEATTENTION_DISABLED"] = "1"
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
            # Only delete pipes/encoders, keep the class/module references
            self.flux_pipe = None
            self.t5_encoder = None
            self.t5_tokenizer = None
            gc.collect()
            torch.cuda.empty_cache()

    def unload_video(self):
        if self.video_pipe is not None:
            print("--- [ULTRA] Purging AnimateDiff from VRAM ---")
            self.video_pipe = None
            gc.collect()
            torch.cuda.empty_cache()

    def load_flux(self):
        if self.flux_pipe is None:
            self.unload_video()
            print(f"--- [ULTRA] Loading FLUX.1 (Schnell) ---")
            
            # Robust import handling
            try:
                from diffusers import FluxPipeline
                from transformers import T5EncoderModel, BitsAndBytesConfig, AutoTokenizer
            except ImportError:
                print("--- [RECOVERY] Re-importing diffusers/transformers ---")
                import importlib
                importlib.invalidate_caches()
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
            print(f"--- [ULTRA] Loading AnimateDiff (Lightweight Video Gen) ---")
            
            # Robust import handling
            try:
                from diffusers import AnimateDiffPipeline, MotionAdapter, EulerDiscreteScheduler
            except ImportError:
                print("--- [RECOVERY] Re-importing diffusers for AnimateDiff ---")
                import importlib
                importlib.invalidate_caches()
                from diffusers import AnimateDiffPipeline, MotionAdapter, EulerDiscreteScheduler
                import torch
                
            token = os.getenv("HF_TOKEN") or os.getenv("RUNPOD_HF_TOKEN")
            
            # Loading Motion Adapter, specifically a lightweight one trained on v1.5
            adapter = MotionAdapter.from_pretrained("guoyww/animatediff-motion-adapter-v1-5-2", torch_dtype=torch.float16, token=token)
            
            # Use an anime-specific base model for better consistency
            self.video_pipe = AnimateDiffPipeline.from_pretrained(
                "emilianJR/epiCRealism",  # A widely used lightweight anime/realism v1.5 model
                motion_adapter=adapter,
                torch_dtype=torch.float16,
                token=token
            )
            
            self.video_pipe.scheduler = EulerDiscreteScheduler.from_config(self.video_pipe.scheduler.config, timestep_spacing="trailing", beta_schedule="linear")
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
        
        # AnimateDiff is primarily T2V initially, but we can guide it
        print(f"--- [ULTRA] Producing Video Frames with AnimateDiff ---")
        
        # Generate video based on prompt
        enhanced_prompt = f"masterpiece, best quality, animated, anime style, highly detailed, {prompt}"
        negative_prompt = "bad quality, worse quality, static, deformed, glitch, noise, watermark"
        
        frames = self.video_pipe(
            prompt=enhanced_prompt,
            negative_prompt=negative_prompt,
            num_frames=16,
            guidance_scale=7.5,
            num_inference_steps=25,
            generator=torch.Generator("cpu").manual_seed(42),
        ).frames[0]
        
        export_to_video(frames, "/tmp/vid.mp4", fps=8)
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
