# MediAI Platform — AI Healthcare Assistant

Full-stack healthcare demo with multi-agent AI chat, doctor booking, lab report analysis, patient dashboard, and admin panel.

| Layer | Tech |
|-------|------|
| Frontend | React 18, TypeScript, Vite |
| Backend | FastAPI, Python 3.12 |
| Database | PostgreSQL 16 + pgvector |
| Cache | Redis |
| Storage | MinIO (S3-compatible) |
| AI | Google Gemini / Groq LLM |

---

## Quick start (Docker — recommended)

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows / Mac / Linux)
- At least one LLM API key: [Groq](https://console.groq.com/) or [Gemini](https://aistudio.google.com/apikey)

### 1. Clone the repository

```bash
git clone <your-github-repo-url>
cd Medical_healthcare_chatbot_AI
```

### 2. Create environment file

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

```bash
# Mac / Linux
cp .env.example .env
```

Edit `.env` and set **at least one** API key:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key_here
```

Or:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
```

> **Never commit `.env` to GitHub.** It contains secrets.

### 3. Start all services

**Windows:**

```powershell
.\start.ps1
```
**Restart from scratch:**
```powershell
docker compose down
docker compose build api --no-cache
.\start.ps1
```

**Mac / Linux:**

```bash
docker compose up --build
```

First run may take 5–15 minutes (image download + build).

### 4. Open the app

| URL | Purpose |
|-----|---------|
| http://localhost:5173 | Web application |
| http://localhost:8000/docs | API documentation (Swagger) |
| http://localhost:8000/health | API health check |
| http://localhost:9001 | MinIO console (optional) |

### 5. Stop

Press `Ctrl+C`, then:

```bash
docker compose down
```

Full reset (wipes database):

```bash
docker compose down -v
```

---

## Demo accounts

Created automatically on first startup (`seed.py`):

| Role | Email | Password |
|------|-------|----------|
| Patient | `john@test.com` | `Patient@12345` |
| Patient | `jane@test.com` | `Patient@12345` |
| Doctor | `dr.sharma@clinic.com` | `Doctor@12345` |
| Admin | `admin@clinic.com` | `Admin@12345` |

After login:

- Patient → `/dashboard`
- Doctor → `/doctor`
- Admin → `/admin`

---

## Features

- **Landing page** with guest chat and OTP signup
- **AI consultation** — symptom triage, specialist recommendation, in-chat booking
- **Find doctors** — browse doctors, calendar slots, book appointments
- **My appointments** — view and cancel bookings
- **My reports** — upload lab reports, AI analysis, health vitals on dashboard
- **Admin panel** — manage patients/doctors, reset demo data
- **Doctor portal** — doctor dashboard and schedule

---

## Project structure

```
Medical_healthcare_chatbot_AI/
├── start.ps1              # Windows one-click start
├── docker-compose.yml     # Postgres, Redis, MinIO, API, Web
├── .env.example           # Environment template (copy to .env)
├── setup.txt              # Detailed setup guide for colleagues
├── backend/
│   ├── app/               # FastAPI application
│   │   ├── multi_agent/   # Supervisor + specialist agents
│   │   ├── routes/        # API endpoints
│   │   └── services/      # Business logic
│   ├── alembic/           # Database migrations
│   ├── seed.py            # Demo data
│   ├── entrypoint.py      # Docker startup
│   └── Dockerfile
└── frontend/
    ├── src/
    │   ├── pages/patient/ # Dashboard, Chat, Doctors, Reports, …
    │   ├── pages/admin/   # Admin panel
    │   └── components/
    └── Dockerfile
```

---

## Multi-agent architecture

```
Patient → Supervisor → Specialist Agent → Tools → PostgreSQL
                ↓
         Safety Agent (emergency / crisis)
```

| Agent | Role |
|-------|------|
| **Supervisor** | Routes to the right specialist, tracks care goals |
| **Safety** | Emergency and mental health crisis detection |
| **Education** | Health Q&A and general medical information |
| **Triage** | Symptom assessment and specialist recommendation |
| **Scheduling** | Book, cancel, reschedule; doctor and slot search |
| **Report** | Lab report upload and AI analysis |
| **Follow-up** | Post-visit recovery check-ins |
| **Refill** | Prescription refill requests |

---

## Environment variables

Copy `.env.example` to `.env`. Key settings:

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | One of Groq/Gemini | Groq API key |
| `GEMINI_API_KEY` | One of Groq/Gemini | Google Gemini API key |
| `LLM_PROVIDER` | No | `groq` or `gemini` (default: groq in Docker) |
| `JWT_SECRET` | No | Change for production |
| `SMTP_HOST` | No | Leave empty for dev (OTP in API logs); use `sandbox.smtp.mailtrap.io` for Mailtrap Sandbox |
| `SMTP_USER` / `SMTP_PASSWORD` | No | Sandbox: inbox credentials from Mailtrap; Live: user `api`, password = API token |
| `SMTP_FROM` | No | Sender shown in test emails (sandbox); live sending requires a verified domain |
| `DEV_OTP` | No | `true` shows OTP in chat/login UI; set `false` when using SMTP/Mailtrap (default) |

Docker Compose reads `.env` from the project root for LLM keys. Database, Redis, and MinIO URLs are set inside `docker-compose.yml` for containers.

---

## Useful commands

```bash
# View logs
docker compose logs -f api
docker compose logs -f web

# Restart API after .env change
docker compose restart api

# Reset patient data, keep doctors
docker compose exec api python truncate_keep_doctors.py

# Re-run database seed
docker compose exec api python seed.py
```

---

## Setting up on another machine

1. Install **Docker Desktop**
2. Clone this repo from GitHub
3. Copy `.env.example` → `.env` and add your LLM API key
4. Run `.\start.ps1` (Windows) or `docker compose up --build`
5. Open http://localhost:5173

See **`setup.txt`** for a full step-by-step guide, troubleshooting, and optional local (non-Docker) development.

---

## What not to commit

Do **not** push these to GitHub:

- `.env` — API keys and secrets
- `venv/`, `node_modules/` — dependencies (reinstalled by Docker)
- `testcredential.txt` — local credential notes
- `reports/` — uploaded sample medical files
- Docker volume data (`pgdata/`, `miniodata/`)

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Port already in use | Stop other apps on 5173, 8000, 5433, 6379 |
| AI chat errors | Verify `GROQ_API_KEY` or `GEMINI_API_KEY` in `.env`, restart API |
| Login fails | Run `docker compose down -v` then `docker compose up --build` |
| OTP not received | Check Mailtrap sandbox inbox; or set `DEV_OTP=true` to show codes in chat, or check `docker compose logs api` |
| UI not updating | Hard refresh: `Ctrl+Shift+R` |

---

## License

Demo / educational project. Not intended for production medical use without proper compliance review.
