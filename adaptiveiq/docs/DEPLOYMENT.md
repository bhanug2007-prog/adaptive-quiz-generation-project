# Deployment

AdaptiveIQ is three services: the React site, the FastAPI backend with PostgreSQL, and the model server (llama.cpp `llama-server` with the GGUF model). The browser only ever talks to the site and the backend.

## Production checklist

The backend refuses to start in `ENVIRONMENT=production` unless these hold:

- `SECRET_KEY` is a random value of at least 32 characters (not the development or placeholder value).
- `COOKIE_SECURE=true`, so the site is served over HTTPS.
- `DATABASE_URL` is PostgreSQL (SQLite is refused).
- If `REQUIRE_EMAIL_VERIFICATION=true`, `SMTP_HOST` and `SMTP_FROM` are set.

Also set `FRONTEND_URL` and `ALLOWED_ORIGINS` to the public site address, and `LECTURER_INVITE_CODE` to a code you share privately (or leave it empty and create lecturer accounts another way).

Run **one** backend process (`uvicorn app.main:app`, no `--workers`): the generation queue and the sign-in rate limiter live in that process.

Back up the PostgreSQL database regularly (`pg_dump`).

## Option A: Docker Compose (written, not yet built in this project)

```bash
cp backend/.env.example backend/.env      # set SECRET_KEY, LECTURER_INVITE_CODE, SMTP_*, ENVIRONMENT
docker compose up --build                 # site on http://localhost:8088
```

Compose runs PostgreSQL, the backend (which applies migrations on start) and an nginx container that serves the built site and forwards `/api` to the backend. The model server runs outside Compose; set `MODEL_BASE_URL` (default `http://host.docker.internal:8080`, the host machine). Put a TLS-terminating proxy (Caddy, nginx, a cloud load balancer) in front for HTTPS.

## Option B: one Linux server by hand

```bash
# PostgreSQL
sudo -u postgres createuser adaptiveiq -P && sudo -u postgres createdb adaptiveiq -O adaptiveiq
# backend
cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env && nano .env         # production values
python -m alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers
# frontend
cd ../frontend && npm ci && npm run build # serve frontend/dist with nginx, using frontend/nginx.conf as a template
```

Run the backend and `llama-server` under systemd so they restart after a reboot.

## The model server

```bash
llama-server -m qwen7b-mcq-Q4_K_M.gguf -c 4096 --host 127.0.0.1 --port 8080            # same machine
llama-server -m qwen7b-mcq-Q4_K_M.gguf -c 4096 --host 0.0.0.0 --port 8080 --api-key SECRET -ngl 99   # GPU host
```

If the model runs on another machine, give it an API key, put it behind HTTPS or a private network, and set `MODEL_BASE_URL` and `MODEL_API_KEY` in the backend. The key never reaches the browser. A temporary notebook tunnel (Colab, Kaggle) is for development only: it stops after a few hours.

Without the model the site still works (courses, quizzes, attempts, analytics); only generation is unavailable, and the portal shows the model as offline.
