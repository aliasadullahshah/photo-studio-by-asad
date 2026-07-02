# Hosting the web edition

The web app is a FastAPI server (`webapp/server.py`) + a single-page frontend.
All AI runs on the server's CPU — visitors' browsers need nothing special.

> **Privacy note:** hosted publicly, visitors' photos are uploaded to *your*
> server for processing (nothing goes to any third party). Run locally or on
> your LAN if photos must never leave the building.

## 1. Run on your own PC (simplest)

```bat
run_web.bat
```

Opens http://127.0.0.1:8317. First launch downloads the AI model (~176 MB) once.

## 2. Share on your home/office network

Phones on the same Wi-Fi can use it directly — handy since photos start there:

```bat
python -m uvicorn webapp.server:app --host 0.0.0.0 --port 8317
```

Find your PC's IP with `ipconfig` (e.g. 192.168.1.20), allow the port once in
Windows Firewall, then open `http://192.168.1.20:8317` on the phone.

## 3. Host on the internet

The server needs ~2 GB RAM (the segmentation model); processing a photo takes
2–10 s of CPU. The included `Dockerfile` works on any Docker host and honors
the `PORT` env var. Model weights are baked into the image at build time.

### Option A — Hugging Face Spaces (free)

1. Create a Space at huggingface.co/new-space → SDK: **Docker** → CPU basic (free).
2. Push this repo to the Space:
   ```
   git remote add space https://huggingface.co/spaces/<you>/photo-studio
   git push space master:main
   ```
3. In the Space settings nothing else is needed — Spaces sets `PORT`.
   Free CPU Spaces sleep after inactivity; first hit after a sleep is slow.

### Option B — Render / Railway (one-click Docker)

1. Push the repo to GitHub (already done).
2. render.com → New → Web Service → connect the GitHub repo. Render detects
   the Dockerfile automatically.
3. Pick an instance with **at least 2 GB RAM** (free 512 MB tier is too small
   for the model — it will be OOM-killed). Railway: same flow at railway.app.

### Option C — Any VPS (Hetzner, Lightsail, DigitalOcean, ~$5–8/mo)

```bash
git clone https://github.com/aliasadullahshah/photo-studio-by-asad
cd photo-studio-by-asad
docker build -t photo-studio .
docker run -d --restart unless-stopped -p 80:8000 photo-studio
```

For HTTPS put Caddy in front (`caddy reverse-proxy --from yourdomain.com --to :8000`).

### Not suitable

- GitHub Pages / Netlify / Vercel static hosting — this app needs a Python
  server; static hosts can't run it.
- Serverless functions — the 176 MB model + several-second CPU inference
  exceeds most function limits.
