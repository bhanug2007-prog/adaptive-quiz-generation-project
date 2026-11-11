---
title: AdaptiveIQ Model
emoji: 🧠
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

Model server for AdaptiveIQ: llama.cpp `llama-server` with the fine-tuned Qwen2.5-7B GGUF (Q4_K_M), CPU only.
It is called by the AdaptiveIQ backend, not by people. Every request except `/health` needs the API key.
