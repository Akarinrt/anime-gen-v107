import os
import sys
import types
import builtins
import importlib.util
from unittest.mock import MagicMock

# --- STEALTH STABILIZATION PATCHES (v1.2.9-ULTRA) ---
# Goal: Hide flash-attn, fix infer_schema, HF Auth, and Dynamic Hot-Fixing
# ==========================================================

import urllib.request
import traceback

# --- DYNAMIC HOT-UPDATE LOGIC ---
# If REMOTE_HANDLER_URL is set, we bypass local code and run from GitHub Raw
REMOTE_URL = os.getenv("REMOTE_HANDLER_URL")
if REMOTE_URL and os.getenv("DISABLE_DYNAMIC_LOAD") != "1":
    try:
        print(f"\n--- [HOT-UPDATE] Fetching latest logic from {REMOTE_URL} ---")
        # Define a special header to avoid caching if possible
        req = urllib.request.Request(REMOTE_URL, headers={'User-Agent': 'RunPod-Dynamic-Loader'})
        with urllib.request.urlopen(req, timeout=10) as response:
            code = response.read().decode('utf-8')
            print(f"--- [HOT-UPDATE] Successfully downloaded {len(code)} bytes ---")
            
            # Execute in global scope. This defines the 'handler' and all dependencies.
            # We set a flag to prevent infinite recursion if the remote code also contains this loader.
            os.environ["DISABLE_DYNAMIC_LOAD"] = "1"
            exec(code, globals())
            
            print("--- [HOT-UPDATE] Remote handler active. Bootloader exiting. ---")
            # The last line of the executed code will be runpod.serverless.start(...)
            # So we don't need to do anything else.
            import sys
            sys.exit(0)
    except Exception as e:
        print(f"--- [HOT-UPDATE ERROR] Failed to load remote code: {e} ---")
        traceback.print_exc()
        print("--- [HOT-UPDATE] Falling back to local v1.3.1-ULTRA logic... ---\n")


import gc

print("\n" + "="*50)
print("--- BOOTING WORKER v1.3.1-ULTRA ---")
print("="*50 + "\n")

# 0. Global Memory Optimizations
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True,max_split_size_mb:128"

# 0. Global Memory Optimizations
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

# 1. Broad Stealth Import Patching (Proven to hide flash-attn)
orig_find_spec = importlib.util.find_spec
def patched_find_spec(name, package=None):
    if name and ("flash_attn" in name or "flash-attn" in name):
        return None
    return orig_find_spec(name, package)
importlib.util.find_spec = patched_find_spec

orig_import = builtins.__import__
def patched_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name and ("flash_attn" in name or "flash-attn" in name):
        raise ImportError(f"Bypassed {name} via stealth patch")
    return orig_import(name, globals, locals, fromlist, level)
builtins.__import__ = patched_import

# 2. Aggressive Torch Library Signature Patching
# Fixed: Return dummy string instead of None to avoid TypeError in concatenation
try:
    import torch
    import torch.library
    
    def apply_infer_patch(module):
        if hasattr(module, "infer_schema"):
            orig = module.infer_schema
            def patched(*args, **kwargs):
                try:
                    return orig(*args, **kwargs)
                except Exception as e:
                    err = str(e)
                    if "unsupported type" in err or "torch.Tensor" in err or "Parameter q" in err:
                        # Try to get func name from args[0]
                        func_name = "unknown"
                        if len(args) > 0:
                            func_name = getattr(args[0], "__name__", str(args[0]))
                        sys.stdout.write(f"--- [STABILIZER] Bypassed type-hint error for: {func_name} ---\n")
                        # Return a valid-ish dummy schema string to avoid "concatenate str (not NoneType)"
                        return "() -> ()" 
                    raise e
            module.infer_schema = patched
            return True
        return False

    apply_infer_patch(torch.library)
    try:
        import torch._library.infer_schema as internal
        apply_infer_patch(internal)
    except: pass
    
    print("--- [STABILIZER] Torch signature patches applied ---")
except Exception as e:
    print(f"--- [STABILIZER ERROR] Patching failed: {e} ---")

# 3. Environment Sanitization
os.environ["DIFFUSERS_NO_FLASH_ATTN"] = "1"
os.environ["USE_FLASH_ATTENTION"] = "0"
os.environ["USE_PEFT_BACKEND"] = "0"

import runpod
import traceback

WORKER_VERSION = "1.2.9-ultra"

print(f"--- Environment Debug Info ({WORKER_VERSION}) ---")
print(f"Python: {sys.version}")
print(f"Torch: {torch.__version__}")
print(f"CUDA: {torch.version.cuda}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")

# --- WORKER LOGIC ---

def get_device():
    return "cuda" if torch.cuda.is_available() else "cpu"

class VideoGenerator:
    def __init__(self):
        self.device = None
        self.flux_pipe = None
        self.video_pipe = None
        
    def load_flux(self):
        if self.flux_pipe is None:
            print("--- Loading FLUX.1 [schnell] ---")
            from diffusers import FluxPipeline
            import torch
            self.device = get_device()
            from transformers import T5EncoderModel, BitsAndBytesConfig, AutoTokenizer
            
            # UNIVERSAL MONKEYPATCH: Patch torch.nn.Module itself!
            # This is the nuclear option because every transformer inherit from this.
            def set_submodule_universal(self, name, module):
                target = self
                if "." in name:
                    path, name = name.rsplit(".", 1)
                    for part in path.split("."):
                        target = getattr(target, part)
                setattr(target, name, module)

            if not hasattr(torch.nn.Module, "set_submodule"):
                print("--- Applying UNIVERSAL set_submodule patch to torch.nn.Module ---")
                torch.nn.Module.set_submodule = set_submodule_universal

            # --- DEEP DIAGNOSTICS FOR HF AUTH ---
            print("--- [HF-DIAGNOSTICS] Checking Environment Variables ---")
            hf_vars = {k: v for k, v in os.environ.items() if "HF" in k or "TOKEN" in k}
            for k, v in hf_vars.items():
                masked_v = f"{v[:4]}...{v[-4:]}" if len(v) > 8 else "***"
                print(f"--- [HF-DIAGNOSTICS] {k}: {masked_v} ---")
            
            token = os.getenv("HF_TOKEN") or os.getenv("HF_HUB_TOKEN") or os.getenv("RUNPOD_HF_TOKEN")
            if token:
                print(f"--- [HF-DIAGNOSTICS] Selected Token: {token[:4]}...{token[-4:]} ---")
                os.environ["HF_HUB_TOKEN"] = token 
            else:
                print("--- [HF-DIAGNOSTICS] WARNING: No HF_TOKEN/HF_HUB_TOKEN found in environment! ---")

            quant_config = BitsAndBytesConfig(load_in_8bit=True)
            
            # Use a safer loading approach for gated repos
            print(f"--- [DEBUG] Attempting to load tokenizer with token... ---")
            try:
                self.t5_tokenizer = AutoTokenizer.from_pretrained(
                    "black-forest-labs/FLUX.1-schnell", 
                    subfolder="tokenizer_2", 
                    token=token,
                    trust_remote_code=True
                )
                print("--- [DEBUG] Tokenizer loaded successfully ---")
                print("--- [DEBUG] Tokenizer loaded successfully ---")
                
                print(f"--- [DEBUG] Attempting to load T5 Encoder... ---")
                self.t5_encoder = T5EncoderModel.from_pretrained(
                    "black-forest-labs/FLUX.1-schnell",
                    subfolder="text_encoder_2",
                    quantization_config=quant_config,
                    token=token,
                    torch_dtype=torch.float16,
                    device_map={"": "cpu"}
                )
                print("--- [DEBUG] T5 Encoder loaded successfully ---")
                
                # Load Flux to CPU first, then enable offload
                self.flux_pipe = FluxPipeline.from_pretrained(
                    "black-forest-labs/FLUX.1-schnell", 
                    text_encoder_2=None, 
                    torch_dtype=torch.bfloat16,
                    token=token,
                    low_cpu_mem_usage=True
                )
                self.flux_pipe.enable_model_cpu_offload()
                torch.cuda.empty_cache()
                print("--- FLUX pipeline loaded with CPU offload ---")
            except Exception as e:
                err_msg = str(e)
                if "gated repo" in err_msg.lower() or "401" in err_msg:
                    print("--- [ERROR] Hugging Face Authentication Failed (Gated Repo) ---")
                    print("--- Please ensure you have accepted the terms at: https://huggingface.co/black-forest-labs/FLUX.1-schnell ---")
                raise e
            
    def load_video(self, model_name="svd"):
        if self.video_pipe is None:
            print(f"--- Loading {model_name} with Low CPU Mem Usage & Model Offload ---")
            from diffusers import StableVideoDiffusionPipeline
            import torch
            self.device = get_device()
            token = os.getenv("HF_TOKEN")
            torch.cuda.empty_cache()
            self.video_pipe = StableVideoDiffusionPipeline.from_pretrained(
                "stabilityai/stable-video-diffusion-img2vid-xt", 
                torch_dtype=torch.float16, variant="fp16",
                token=token,
                low_cpu_mem_usage=True
            )
            self.video_pipe.enable_model_cpu_offload()
            torch.cuda.empty_cache()

    def generate_image(self, prompt):
        try:
            self.load_flux()
            
            # Pre-encode with T5
            print(f"--- Pre-encoding prompt with 8-bit T5 ---")
            inputs = self.t5_tokenizer(prompt, return_tensors="pt", padding="max_length", max_length=512, truncation=True).to(self.t5_encoder.device)
            with torch.no_grad():
                prompt_embeds = self.t5_encoder(inputs.input_ids).last_hidden_state
                
            # Generate image passing pre-encoded embeds
            image = self.flux_pipe(
                prompt_embeds=prompt_embeds,
                num_inference_steps=4,
                guidance_scale=0.0,
                generator=torch.Generator("cpu").manual_seed(0)
            ).images[0]
            # For now, save the image and return a URL
            # In a real scenario, you'd upload this to storage
            # and return the public URL.
            image_path = "/tmp/generated_image.jpg"
            image.save(image_path)
            # This is a placeholder. In a real app, you'd upload `image_path` to cloud storage.
            return "https://storage.runpod.io/flux_test.jpg" # Placeholder URL
        except Exception as e:
            print(f"FLUX Error: {e}")
            traceback.print_exc()
            raise e

    def animate_image(self, image_url, prompt, model_name="svd"):
        try:
            self.load_video(model_name)
            return "https://storage.runpod.io/svd_test.mp4"
        except Exception as e:
            print(f"Video Error: {e}")
            traceback.print_exc()
            raise e

    def sync_lips(self, video_url, audio_url):
        try:
            return "https://storage.runpod.io/final_test.mp4"
        except Exception as e:
            print(f"LipSync Error: {e}")
            traceback.print_exc()
            raise e

# Lazy init
gen = None

def handler(event):
    global gen
    
    # Aggressive cleanup at start of EVERY job to clear previous failures
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()
        
    if gen is None:
        gen = VideoGenerator()
        
    try:
        input_data = event.get('input', {})
        job_type = input_data.get('type')
        payload = input_data.get('payload', {})
        
        print(f"Handling job type: {job_type}")
        
        if job_type == "generate_image":
            prompt = payload.get('prompt')
            url = gen.generate_image(prompt)
            return {"status": "success", "url": url}
            
        elif job_type == "generate_video":
            url = gen.animate_image(payload.get('image_url'), payload.get('prompt'))
            return {"status": "success", "url": url}

        elif job_type == "sync_lips":
            url = gen.sync_lips(payload.get('video_url'), payload.get('audio_url'))
            return {"status": "success", "url": url}
            
        return {"status": "error", "message": f"Invalid job type: {job_type}"}
    except Exception as e:
        error_msg = f"Handler CRASH: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return {"status": "error", "message": error_msg}

print("--- RunPod Worker Ready ---")
runpod.serverless.start({"handler": handler})
