# Deploying AutoVerify NG to Render (so you can test on your phone)

This gets you a public HTTPS URL (e.g. `https://autoverify-ng.onrender.com`)
that you can open directly on your phone's browser — no need to be on the
same Wi-Fi as your laptop, and HTTPS means the camera + GPS features will
work (they require a "secure context").

A `Dockerfile` is already included in this project specifically so
Tesseract OCR (a system binary, not a Python package) installs correctly
during the build — this is more reliable on Render than its native Python
buildpack for apps with system-level dependencies like this one.

---

## 1. Push the project to GitHub

Render deploys from a Git repo (GitHub, GitLab, or Bitbucket). Easiest
path from VS Code:

1. Open the Source Control panel (left sidebar, the branch icon) or run
   in the integrated terminal:
   ```bash
   git init
   git add .
   git commit -m "Initial commit - AutoVerify NG"
   ```
2. Create a new repo on GitHub (github.com → "+" → "New repository"),
   then either:
   - Use VS Code's **"Publish to GitHub"** button in the Source Control
     panel (appears automatically after `git init`), or
   - Run manually:
     ```bash
     git remote add origin https://github.com/<your-username>/<repo-name>.git
     git branch -M main
     git push -u origin main
     ```

> `autoverify.db`, `alerts.log`, and uploaded photos are intentionally
> **not** committed (see `.gitignore`/`.dockerignore`) — they're
> regenerated automatically on first run.

## 2. Create the Web Service on Render

1. Go to https://render.com and sign in (GitHub sign-in is easiest — it
   lets Render list your repos directly).
2. Click **New +** → **Web Service**.
3. Connect the GitHub repo you just pushed.
4. Render should auto-detect the `Dockerfile` and set the environment to
   **Docker**. If it offers a choice, pick **Docker** explicitly rather
   than the native Python runtime — this is what makes Tesseract install
   correctly.
5. Instance type: **Free**.
6. Under **Environment Variables**, add:
   | Key | Value |
   |---|---|
   | `SECRET_KEY` | any long random string (e.g. generate one at https://randomkeygen.com) |
   | `FLASK_DEBUG` | `0` |
7. Click **Create Web Service**. The first build takes several minutes
   (installing OpenCV + Tesseract + TensorFlow). Watch the build log —
   Render shows live progress.
8. Once it says **Live**, you'll get a URL like
   `https://autoverify-ng-xxxx.onrender.com`. Open that directly on your
   phone's browser.

## 3. Test on your phone

Open the Render URL on your phone and it works exactly like localhost did:
- **Officer Login** → `officer1` / `officer123` (seeded automatically)
- **Admin** → `admin` / `admin123`
- Go to **Scan Vehicle**, tap **Start Camera**, grant camera + location
  permission when prompted, and capture a plate photo — this now uses
  your phone's actual rear camera.

---

## 4. Things to know about the free tier

**Cold starts.** Render's free web services spin down after 15 minutes
with no traffic. The next request wakes it back up, which takes roughly
30-60 seconds while it shows a loading page. For a defense/demo: open the
link a couple of minutes beforehand so it's already "warm."

**No persistent disk.** The free tier doesn't include persistent storage,
so the SQLite database and any uploaded photos can reset when the service
restarts or redeploys. This is actually fine for demo purposes because
`app.py` automatically re-seeds the demo admin/officer/owner accounts and
demo vehicles every time it starts up — so the app is always immediately
usable after a restart. Just know that anything you add *during* one
session (new registrations, stolen reports you filed, etc.) isn't
guaranteed to survive a cold restart between sessions. If you need data to
persist reliably (e.g. for a multi-day demo), the straightforward upgrade
path is Render's paid tier with a persistent disk, or switching to a
managed Postgres database — not necessary just to show the app working
on your phone.

**Build size/time.** TensorFlow is the heaviest dependency here and is
only actually used once you've trained a real vehicle classifier (see
`utils/train_classifier.py`). If you haven't trained one and want faster,
lighter builds, you can comment out `tensorflow-cpu` in `requirements.txt`
for deployment — `utils/recognition.py` already checks whether a trained
model file exists before ever importing TensorFlow, so removing the
package doesn't break anything; make/model recognition just stays on
placeholder values (colour detection still works for real either way).

**Every push redeploys.** Once connected, pushing to your GitHub branch
automatically triggers a new build/deploy on Render — handy if you keep
tweaking things.
