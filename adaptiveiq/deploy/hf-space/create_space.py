"""Creates the AdaptiveIQ model Space on Hugging Face and uploads Dockerfile + README.md.

Run from the adaptiveiq folder after `huggingface_hub` login (with a WRITE token):
    python deploy/hf-space/create_space.py

It asks for a READ token (stored only as the Space secret HF_TOKEN, so the Space can download your private
model), makes a random LLAMA_API_KEY, and prints that key ONCE: put it in backend/.env as MODEL_API_KEY.
Running it again is safe; it makes a new API key each time, so update backend/.env again if you do.
"""
import getpass
import secrets
from pathlib import Path

from huggingface_hub import HfApi, whoami

HERE = Path(__file__).resolve().parent
api = HfApi()
user = whoami()["name"]
model_repo = f"{user}/adaptiveiq-qwen7b-gguf"
space = f"{user}/adaptiveiq-model"

read_token = getpass.getpass("Paste your READ token (right-click, then Enter; it stays hidden): ").strip()
if not read_token.startswith("hf_"):
    raise SystemExit("That does not look like a Hugging Face token (it should start with hf_). Nothing was changed.")

api.create_repo(space, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
api.add_space_variable(space, "LLAMA_ARG_HF_REPO", model_repo)
api.add_space_variable(space, "LLAMA_ARG_HF_FILE", "qwen7b-mcq-Q4_K_M.gguf")
api.add_space_secret(space, "HF_TOKEN", read_token)
key = secrets.token_urlsafe(32)
api.add_space_secret(space, "LLAMA_API_KEY", key)
api.upload_folder(folder_path=str(HERE), repo_id=space, repo_type="space",
                  allow_patterns=["Dockerfile", "README.md"], commit_message="AdaptiveIQ model server")

host = f"https://{space.replace('/', '-').replace('_', '-').lower()}.hf.space"
print("\nDone. The Space is building now (first start takes several minutes).")
print("Space page:  https://huggingface.co/spaces/" + space)
print("Health:      " + host + "/health")
print("\nPut these two lines in backend/.env (do not share the key with anyone):")
print("MODEL_BASE_URL=" + host)
print("MODEL_API_KEY=" + key)
