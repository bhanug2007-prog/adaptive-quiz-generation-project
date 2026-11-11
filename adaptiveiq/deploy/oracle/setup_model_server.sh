#!/usr/bin/env bash
# AdaptiveIQ model server on an Oracle Cloud Always Free ARM instance (Ubuntu 24.04, VM.Standard.A1.Flex,
# 2 OCPU / 12 GB). It builds llama.cpp, downloads the fine-tuned Qwen 7B GGUF from your PRIVATE Hugging Face
# repo, runs llama-server as a service with an API key, and puts Caddy in front for HTTPS (free certificate,
# address <your-ip>.sslip.io). Run it ON THE SERVER as the ubuntu user:
#
#     bash setup_model_server.sh YOUR-HF-USERNAME
#
# It asks for a Hugging Face READ token (hidden, used once to download, not saved) and prints the two lines
# for backend/.env at the end. Running it again is safe: it keeps the model and the API key it already made.
set -euo pipefail

HF_USER="${1:?Usage: bash setup_model_server.sh YOUR-HF-USERNAME}"
REPO="$HF_USER/adaptiveiq-qwen7b-gguf"
FILE="qwen7b-mcq-Q4_K_M.gguf"
APP=/opt/adaptiveiq-model
MODEL="$APP/models/$FILE"

echo "== 1/6 Packages"
sudo apt-get update -y
sudo apt-get install -y build-essential cmake git curl libcurl4-openssl-dev python3-venv caddy netfilter-persistent

echo "== 2/6 Build llama.cpp (about 10-20 minutes on 2 cores)"
sudo mkdir -p "$APP/models"
sudo chown -R "$USER":"$USER" "$APP"
if [ ! -d "$APP/llama.cpp" ]; then
  git clone --depth 1 https://github.com/ggml-org/llama.cpp "$APP/llama.cpp"
fi
cmake -S "$APP/llama.cpp" -B "$APP/llama.cpp/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$APP/llama.cpp/build" --target llama-server -j 2

echo "== 3/6 Download the model from $REPO"
if [ ! -s "$MODEL" ]; then
  python3 -m venv "$APP/venv"
  "$APP/venv/bin/pip" install -q "huggingface_hub<1.0"
  read -rsp "Paste your Hugging Face READ token, then Enter (hidden): " HF_TOKEN; echo
  HF_TOKEN="$HF_TOKEN" "$APP/venv/bin/python" - "$REPO" "$FILE" "$APP/models" <<'PY'
import os, sys
from huggingface_hub import hf_hub_download
repo, name, out = sys.argv[1:4]
print(hf_hub_download(repo, name, local_dir=out, token=os.environ["HF_TOKEN"]))
PY
  unset HF_TOKEN
fi
ls -lh "$MODEL"

echo "== 4/6 llama-server service (only reachable from this machine; Caddy is the way in)"
if [ ! -f /etc/adaptiveiq-model.env ]; then
  echo "LLAMA_API_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" | sudo tee /etc/adaptiveiq-model.env >/dev/null
  sudo chmod 600 /etc/adaptiveiq-model.env
fi
sudo tee /etc/systemd/system/adaptiveiq-model.service >/dev/null <<UNIT
[Unit]
Description=AdaptiveIQ model server (llama.cpp llama-server, Qwen 7B GGUF)
After=network-online.target

[Service]
User=$USER
EnvironmentFile=/etc/adaptiveiq-model.env
ExecStart=$APP/llama.cpp/build/bin/llama-server -m $MODEL -c 4096 -t 2 --host 127.0.0.1 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now adaptiveiq-model
sudo systemctl restart adaptiveiq-model

echo "== 5/6 HTTPS with Caddy"
IP="$(curl -fsS https://api.ipify.org)"
HOST="${IP//./-}.sslip.io"
sudo tee /etc/caddy/Caddyfile >/dev/null <<CADDY
$HOST {
    reverse_proxy 127.0.0.1:8080
}
CADDY
# Oracle's Ubuntu images block every port except SSH in iptables; open 80 (certificate) and 443 (HTTPS).
for p in 80 443; do
  sudo iptables -C INPUT -p tcp --dport $p -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 1 -p tcp --dport $p -j ACCEPT
done
sudo netfilter-persistent save
sudo systemctl restart caddy

echo "== 6/6 Waiting for the model to load"
for _ in $(seq 120); do
  if curl -fsS http://127.0.0.1:8080/health >/dev/null 2>&1; then break; fi
  sleep 5
done
curl -sS http://127.0.0.1:8080/health; echo
KEY="$(sudo sed -n 's/^LLAMA_API_KEY=//p' /etc/adaptiveiq-model.env)"
echo
echo "Done. Check from your laptop's browser: https://$HOST/health  (should say {\"status\":\"ok\"})"
echo "If it does not open, add ingress rules for TCP 80 and 443 in the Oracle console (see the guide)."
echo
echo "Put these two lines in backend/.env (keep the key private):"
echo "MODEL_BASE_URL=https://$HOST"
echo "MODEL_API_KEY=$KEY"
