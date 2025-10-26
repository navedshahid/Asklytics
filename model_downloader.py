import os
import subprocess
from huggingface_hub import snapshot_download

# === CONFIG ===
MODEL_REPO = "defog/sqlcoder-7b-2"
MODEL_DIR = "models/sqlcoder-7b-2"
GGUF_OUTPUT_DIR = "models"
GGUF_NAME = "sqlcoder-7b-2.q8_0.gguf"  # ✅ Fixed output name
CONVERT_SCRIPT = "E:/Official/GenDS/llama.cpp/convert_hf_to_gguf.py"

CONVERT_ARGS = [
    "--outfile", GGUF_NAME,
    "--outtype", "q8_0",  # ✅ Fixed outtype
    "--output_dir", GGUF_OUTPUT_DIR
]

# === STEP 1: Download model from Hugging Face ===
print(f"📥 Downloading model from: {MODEL_REPO}")
snapshot_download(repo_id=MODEL_REPO, local_dir=MODEL_DIR, local_dir_use_symlinks=False)

# === STEP 2: Find model file (.safetensors or .bin) ===
model_file = None
for file in os.listdir(MODEL_DIR):
    if file.endswith(".safetensors") or file.endswith(".bin"):
        model_file = os.path.join(MODEL_DIR, file)
        break

if not model_file:
    raise FileNotFoundError("❌ Could not find a model checkpoint (.safetensors or .bin)")

print(f"✅ Found model file: {model_file}")

# === STEP 3: Convert model to GGUF ===
os.makedirs(GGUF_OUTPUT_DIR, exist_ok=True)
print("⚙️ Converting to GGUF format...")

cmd = [
    "E:/Official/GenDS/.venv/Scripts/python.exe",
    CONVERT_SCRIPT,
    MODEL_DIR,  # ✅ Positional model path, not --model_path
    "--outfile", GGUF_NAME,
    "--outtype", "q8_0"
]

print("🔧 Running command:\n", " ".join(cmd))
# Set PYTHONPATH so that the module mistral_common can be found (if it's in llama.cpp)
env = os.environ.copy()
env["PYTHONPATH"] = os.path.join(os.getcwd(), "llama.cpp")
subprocess.run(cmd, env=env, check=True)
print(f"✅ GGUF model saved to: {os.path.join(GGUF_OUTPUT_DIR, GGUF_NAME)}")