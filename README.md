# Apply Assist — Backend

A real, deployable FastAPI backend for the Apply Assist dashboard:
real job listings (Adzuna API), a database, Claude-powered resume
parsing/tailoring/interview-prep, a scheduler for daily job refresh +
weekly digest emails, and CORS wired for your frontend.

## 1. Get your API keys

- **Anthropic**: https://console.anthropic.com/ → API Keys
- **Adzuna** (free tier): https://developer.adzuna.com/ → register an app → app_id + app_key
- **Email**: if using Gmail, create an App Password at
  https://myaccount.google.com/apppasswords (needs 2FA enabled on the account)

## 2. Local setup

```bash
cd apply-assist-backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# now edit .env and fill in your real keys
```

## 3. Run it

```bash
uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000/docs` for interactive Swagger docs of every
endpoint. On first boot, if the jobs table is empty, it auto-fetches an
initial batch from Adzuna.

## 4. Connect the frontend

In your React dashboard, replace the `MOCK_JOBS` array and the direct
`callClaude()` fetch to `api.anthropic.com` with calls to this backend
instead, e.g.:

```js
const API_BASE = "http://localhost:8000"; // or your deployed URL

async function loadJobs() {
  const res = await fetch(`${API_BASE}/api/jobs`);
  return res.json();
}

async function parseResume(resumeText) {
  const res = await fetch(`${API_BASE}/api/profile/parse-resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resumeText }),
  });
  return res.json();
}
```

Do this for every place the original artifact called `callClaude()`
directly or used `window.storage` — those become `/api/...` calls to
this backend. Full endpoint list below.

## 5. Deploy

### Render (easiest)
1. Push this folder to a GitHub repo.
2. New → Web Service → connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add all the `.env` variables under Environment → Environment Variables.
6. Set `FRONTEND_ORIGIN` to your deployed frontend's URL.

### Railway
1. New Project → Deploy from GitHub repo.
2. Railway auto-detects Python; add a `Procfile` if needed:
   `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. Add env vars in the Railway dashboard's Variables tab.

### Any VPS (DigitalOcean, EC2, etc.)
```bash
git clone <your-repo>
cd apply-assist-backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys
# Run behind a process manager:
pip install gunicorn
gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```
Put nginx in front for TLS, or use `certbot` directly.

> **SQLite note**: fine for a single-user tool like this. If you deploy on
> a platform with an ephemeral filesystem (some free tiers wipe disk on
> redeploy), switch `DATABASE_URL` in `.env` to a Postgres connection
> string (Render/Railway both offer a free Postgres add-on) — no code
> changes needed since SQLAlchemy handles both.

## 6. Endpoints

| Method | Path | What it does |
|---|---|---|
| GET | `/api/profile` | Get saved resume text, parsed profile, prefs |
| PUT | `/api/profile` | Save resume text / prefs |
| POST | `/api/profile/parse-resume` | Claude parses resume text into structured JSON |
| GET | `/api/jobs` | List cached jobs, scored against your resume keywords |
| POST | `/api/jobs/refresh` | Fetch fresh listings from Adzuna right now |
| POST | `/api/jobs/{id}/tailor` | Claude generates tailored bullets + cover letter |
| POST | `/api/jobs/{id}/interview-prep` | Claude generates likely interview Qs |
| GET | `/api/tracker` | List tracked applications |
| POST | `/api/tracker` | Add/update a job's tracker status |
| DELETE | `/api/tracker/{id}` | Remove a tracker entry |
| GET | `/api/digest` | Preview the current digest text |
| POST | `/api/digest/send` | Send the digest email right now |
| GET | `/api/health` | Health check |

## 7. Scheduler

Runs inside the same process via APScheduler — no separate cron service
needed:
- **Daily** at `JOB_FETCH_CRON_HOUR` (default 6am server time): refreshes
  job listings from Adzuna based on your saved role/location prefs.
- **Weekly** on `DIGEST_CRON_DAY_OF_WEEK` at `DIGEST_CRON_HOUR` (default
  Monday 9am): emails your tracker digest.

Note: on serverless/auto-sleeping platforms, background schedulers only
run while the process is alive — if your host spins the app down when
idle (e.g. Render free tier), the cron won't fire on schedule. For those,
use the platform's own Cron Job feature to hit `/api/jobs/refresh` and
`/api/digest/send` on a schedule instead.
