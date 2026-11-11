# Run the Qwen model on Oracle Cloud Always Free

The free ARM server (2 OCPU, 12 GB RAM) runs `llama-server` with your fine-tuned Qwen 7B GGUF all the time. The
AdaptiveIQ backend calls it over HTTPS with an API key. CPU only, so generation is slow (similar to your laptop).

## 1. Create the account

1. Go to https://www.oracle.com/cloud/free/ and click **Start for free**.
2. Pick your **home region** carefully, it cannot be changed later (for India: Mumbai or Hyderabad).
3. A card is needed for verification only. Always Free resources are not charged.

## 2. Create the server

1. In the console: **Compute → Instances → Create instance**.
2. **Image:** click *Change image* → **Ubuntu** → *Canonical Ubuntu 24.04*.
3. **Shape:** *Change shape* → **Ampere** → `VM.Standard.A1.Flex`, **2 OCPUs, 12 GB memory**. It should say
   "Always Free-eligible".
4. **Networking:** keep the default new VCN and public subnet, and **Assign a public IPv4 address**.
5. **SSH keys:** choose *Generate a key pair for me* and click **Save private key**. Keep that `.key` file safe.
6. **Boot volume:** the default (about 47 to 50 GB) is enough.
7. Click **Create**. If it says *Out of capacity*, try another availability domain, or try again later.

## 3. Open ports 80 and 443

1. Open the instance → **Subnet** link → **Default Security List** → **Add Ingress Rules**.
2. Source CIDR `0.0.0.0/0`, IP protocol TCP, destination port `80`. Add another rule with port `443`.

(The script also opens them in the server's own firewall.)

## 4. Connect and run the setup script

From Windows Command Prompt, in the folder with the key file (`IP` is the instance's public IP):

```
scp -i ssh-key.key "C:\Users\bhanu\Downloads\adaptive quiz dl project\adaptiveiq\deploy\oracle\setup_model_server.sh" ubuntu@IP:~
ssh -i ssh-key.key ubuntu@IP
bash setup_model_server.sh banu1234
```

If Windows says the key's permissions are too open, right-click the key → Properties → Security → Advanced →
disable inheritance and leave only your own user.

The script asks for your Hugging Face **READ** token once (hidden), builds llama.cpp (10 to 20 minutes), downloads
the model (about 4.7 GB), starts the service and HTTPS, and prints:

```
MODEL_BASE_URL=https://<ip-with-dashes>.sslip.io
MODEL_API_KEY=...
```

## 5. Use it

1. Open `MODEL_BASE_URL/health` in your browser: `{"status":"ok"}` means ready.
2. Put the two lines in `backend\.env`, restart the backend, and generate a small quiz.

## Good to know

- Service commands on the server: `sudo systemctl status adaptiveiq-model`, `sudo journalctl -u adaptiveiq-model -n 50`.
- The key is in `/etc/adaptiveiq-model.env` on the server. Never put it in GitHub.
- Oracle may reclaim an Always Free instance that stays almost idle (CPU, network and memory all under 20%) for
  7 days. The loaded model keeps memory use above that, but check the instance now and then.
- The free allowance is 2 OCPU and 12 GB in total. Do not create a second A1 instance.
