#!/bin/bash
#SBATCH --job-name=vllm-serve
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --mem=48G
#SBATCH --cpus-per-task=8
#SBATCH --time=24:00:00
#SBATCH --account=project_pipeon
#SBATCH --output=logs/vllm_%j.out
#SBATCH --error=logs/vllm_%j.err
#SBATCH --mail-type=BEGIN,END,FAIL
# Set your own notification address before submitting:
#   export USER_EMAIL=you@example.com
#   sbatch --mail-user="$USER_EMAIL" slurm/serve_local_model.slurm
# (Leave commented if you don't want job-status emails.)
# #SBATCH --mail-user=you@example.com

# ── Model choice ──────────────────────────────────────────────────────────────
# Llama 3.1 8B  (~16 GB VRAM)  — fastest, good quality
# Gemma 2 9B    (~18 GB VRAM)  — good quality, slightly slower
# Gemma 2 27B   (~40 GB VRAM)  — best quality, needs A100
MODEL_NAME="meta-llama/Llama-3.1-8B-Instruct"
PORT=8000

# ── Environment ───────────────────────────────────────────────────────────────
module load rocky8-spack/master
module load cuda/12.6.3-gcc-10.3.0-2wtu
module load miniconda3/24.3.0-gcc-10.3.0-343s

conda activate hackathon   # <- the conda env with vllm installed

# Install vLLM if not already in the env
pip show vllm > /dev/null 2>&1 || pip install vllm

mkdir -p logs

echo "=== Starting vLLM server ==="
echo "Model  : $MODEL_NAME"
echo "Port   : $PORT"
echo "Node   : $(hostname)"
echo "GPU    : $(nvidia-smi --query-gpu=name --format=csv,noheader)"

# ── Serve with OpenAI-compatible API ─────────────────────────────────────────
python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL_NAME" \
    --port $PORT \
    --host 0.0.0.0 \
    --tensor-parallel-size 1 \
    --max-model-len 8192 \
    --dtype auto

# ── After the job starts, expose it publicly via ngrok ───────────────────────
# In a SEPARATE terminal on the login node:
#
#   ngrok http <NODE>:8000
#   # or if ngrok is installed on the compute node:
#   ngrok http 8000
#
# Copy the https://xxxx.ngrok-free.app URL, then:
# 1. Go to HuggingFace Space Settings → Repository secrets
# 2. Add  LOCAL_MODEL_URL = https://xxxx.ngrok-free.app
# 3. Add  LOCAL_MODEL_NAME = meta-llama/Llama-3.1-8B-Instruct
# 4. Restart the Space — the agent will now use your SLURM GPU for free!
#
# To revert to OpenAI API: delete LOCAL_MODEL_URL secret and restart Space.
