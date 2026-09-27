# Quick Render deployment steps (auto-generated)

1. Push your repo to GitHub (branch `main`).
2. In `render.yaml`, replace `repo:` with your repo URL and set `SECRET_KEY` to a secure value.
3. On Render: **New +** → **Web Service** → select **Deploy from Manifest** and point to your repo and `render.yaml`.
4. Render will use the included `Dockerfile` to build the image (Tesseract installed during the build). Add a Postgres service if you need persistent storage and set `DATABASE_URL` env var on the web service.

Commands to test locally with Docker (already present in repo):

```powershell
# Build image locally
docker build -t autoverify-ng:local .

# Run container (maps port 5000 inside container to 5000 on host)
docker run --rm -p 5000:5000 -e PORT=5000 -e SECRET_KEY="dev-secret" autoverify-ng:local
```

If you want me to run these build steps here, tell me and I will attempt a Docker build again (network access required).