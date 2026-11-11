# AdaptiveIQ model server for a Hugging Face Docker Space (free "CPU basic": 2 vCPU, 16 GB RAM).
# It runs llama.cpp's llama-server with the fine-tuned Qwen 7B GGUF, downloaded from your model repo at start.
#
# Set in the Space's Settings -> Variables and secrets (nothing secret is written in this file):
#   Variable LLAMA_ARG_HF_REPO  your model repo, e.g. your-name/adaptiveiq-qwen7b-gguf
#   Variable LLAMA_ARG_HF_FILE  qwen7b-mcq-Q4_K_M.gguf
#   Secret   HF_TOKEN           a READ token (needed because the model repo is private)
#   Secret   LLAMA_API_KEY      a long random password; the backend sends it as MODEL_API_KEY
FROM ghcr.io/ggml-org/llama.cpp:server

ENV LLAMA_CACHE=/tmp/llama-cache \
    LLAMA_ARG_HOST=0.0.0.0 \
    LLAMA_ARG_PORT=7860 \
    LLAMA_ARG_CTX_SIZE=4096 \
    LLAMA_ARG_THREADS=2

EXPOSE 7860
