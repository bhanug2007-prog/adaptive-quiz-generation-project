# Run the Qwen model on a free Kaggle GPU

Kaggle gives every verified account free GPU time: about **30 hours a week**, at most **12 hours per session**
(figures from November 2026; Kaggle can change them). No card is needed. The model runs on Kaggle's GPU, which is much
faster than your laptop's CPU. Your laptop still runs the backend and the website, but not the model.

What it cannot do: stay on all the time. It is for the times you use or demo the website. The web address and the
API key are new every session, so you update `backend\.env` each time.

Kaggle's terms allow personal, non-commercial use. A student project demo fits that; do not use it to serve other
people's apps.

## One-time setup

1. Create an account at https://www.kaggle.com and **verify your phone number** (Settings → Phone verification).
   Without it, notebooks cannot use the GPU or the internet.
2. On Kaggle: **Create → New Notebook**, then **File → Import Notebook** and upload
   `deploy\kaggle\adaptiveiq_model_server.ipynb` from this project.
3. In the notebook's right-hand panel:
   - **Settings → Accelerator → GPU T4 x2**
   - **Settings → Internet → On**
   - **Add-ons → Secrets → Add secret**: label `HF_TOKEN`, value = your Hugging Face **READ** token. Tick it so this
     notebook can use it.
4. Keep the notebook **Private**.

## Every time you want the model

1. Open the notebook and click **Run All**. The first run builds llama.cpp (about 5 to 15 minutes) and downloads the
   model (4.7 GB). A new session does both again; Kaggle does not keep them between sessions.
2. Cell 5 prints two lines. Put them in `backend\.env` on your laptop (replace the old two):
   ```
   MODEL_BASE_URL=https://something.trycloudflare.com
   MODEL_API_KEY=...
   ```
3. Restart the backend. Generate a quiz as usual.
4. Leave cell 6 running while you use the site and **keep the Kaggle tab open**. When you are done, click
   **Stop** (square button) and then **Stop session** (power icon), so the GPU stops using your weekly hours.

## Good to know

- Never click **Save Version** with outputs: that would store the printed API key in a saved copy.
- If cell 1 says there is no GPU: check the Accelerator setting. If it says `nvcc` is missing, send the message to
  Claude.
- If the website says "The AI model is not available": the Kaggle session ended (12-hour limit, or the tab was
  closed). Run All again and update `backend\.env`.
- The Cloudflare quick tunnel is free and needs no account. It has no uptime guarantee and allows up to 200 requests at
  the same time, far more than this project needs.
