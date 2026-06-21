# Facebook Marketplace Vehicle Monitoring

Automated Facebook Marketplace vehicle scanner with admin dashboard, filter matching, duplicate detection, and email alerts.

Facebook has no official API. This project uses Playwright (Chromium) to scrape listings after you log in manually once.

---

## Requirements

| Software | Version |
|----------|---------|
| Windows | 10/11 (batch scripts are Windows-only) |
| Python | 3.11+ |
| Node.js | 18+ (local frontend dev only) |
| Internet | Required for Facebook, SMTP, and first-time installs |

---

## First-Time Setup (One Time)

Run these steps once on a new PC.

### Step 1 — Backend environment

```bat
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `backend\.env`:

```env
ADMIN_EMAIL=your@email.com
ADMIN_PASSWORD=your-secure-password

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your-16-char-app-password
SMTP_FROM_EMAIL=your@gmail.com
SMTP_FROM_NAME=Marketplace Monitor
SMTP_USE_TLS=true
```

Login uses `ADMIN_EMAIL` and `ADMIN_PASSWORD` from this file.  
SMTP is configured here only — not in the dashboard UI.

### Step 2 — Install Chromium (one time)

Double-click:

```
install-chromium.bat
```

Chromium installs to `backend\playwright-browsers`.

### Step 3 — Vercel tunnel (live dashboard only)

If you use the hosted dashboard at `https://facebook-monitoring.vercel.app`:

1. Run `start-backend.bat` (see below).
2. Copy the `https://....loca.lt` URL from the **FB Monitor Tunnel** window.
3. In Vercel → Project → Settings → Environment Variables, set:
   - Name: `BACKEND_URL`
   - Value: the tunnel URL (no trailing slash)
4. Redeploy the frontend on Vercel.

---

## How to Run (Normal Daily Use — Windows)

### Start everything

Double-click:

```
start-backend.bat
```

This script:

1. Stops any old backend on port 8000
2. Creates `backend\venv` and `backend\.env` if missing
3. Opens **FB Monitor Backend** window → runs `python run.py` on `http://127.0.0.1:8000`
4. Opens **FB Monitor Tunnel** window → `localtunnel` on port 8000 for Vercel

Keep both CMD windows open while monitoring.

### Open dashboard

| Mode | URL |
|------|-----|
| Live (Vercel) | https://facebook-monitoring.vercel.app |
| Local dev | http://127.0.0.1:5173 (after `npm run dev`) |

### Login

Use the email and password from `backend\.env`.

If `.env` is empty, defaults are:

- Email: `admin@example.com`
- Password: `admin123`

### Stop everything

Double-click:

```
stop-backend.bat
```

This kills the backend PID and frees ports 8000 and 8001. Close the tunnel window manually.

---

## How to Run (Local Development — Frontend + Backend Separate)

### Terminal 1 — Backend

```bat
cd backend
venv\Scripts\activate
set PLAYWRIGHT_BROWSERS_PATH=%CD%\playwright-browsers
python run.py
```

Backend: `http://127.0.0.1:8000`  
API docs: `http://127.0.0.1:8000/docs`  
Health check: `http://127.0.0.1:8000/health`

### Terminal 2 — Frontend

```bat
cd frontend
npm install
npm run dev
```

Frontend: `http://127.0.0.1:5173`  
Vite proxies `/api` and `/health` to port 8000.

No tunnel needed for local dev.

---

## Monitoring — Exact Steps (What the Bot Does)

When you click **Start** on the dashboard, the backend runs a 7-stage Facebook flow.  
Every step is logged in **Logs** page with labels like `Stage 1/7`, `Stage 2/7`, etc.

### Before Start (you do this once)

1. Run `start-backend.bat` — backend must be running on port 8000.
2. Open dashboard and log in with `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `backend\.env`.
3. Go to **Filters** — at least one filter must be **Active**.
4. Click **Start** (Dashboard header).

---

### Stage 0/7 — Open browser

| What happens | Detail |
|--------------|--------|
| Chromium opens | Playwright Chromium window (visible by default) |
| Session loaded | If `backend\data\facebook_session.json` exists, cookies are restored |
| Reuse | If browser is already open from last run, same window is reused |

---

### Stage 1/7 — Open Facebook Marketplace

| What happens | Detail |
|--------------|--------|
| URL opened | `https://www.facebook.com/marketplace/` |
| Not logged in | Bot stays **completely idle** on Marketplace |
| Your action | Log in using **Email/Password in the top header** — not the login popup |
| Popup | If login popup appears, bot closes it once — use top header instead |

**If already logged in (saved session):** bot skips manual login and continues to Stage 2.

---

### Stage 2/7 — Check Facebook login

| Condition | What happens |
|-----------|--------------|
| **Not logged in** | Bot waits up to **15 minutes** for you to finish login + 2FA |
| **5 minutes, still not logged in** | Reminder email sent to `ADMIN_EMAIL` + active notification recipients |
| **Login complete** | Session saved → Marketplace reloads → bot continues |
| **Already logged in** | Session refreshed and saved → continues immediately |

Bot does **not** navigate away while you are on Facebook login/verification pages.

---

### Stage 3/7 — Marketplace → Vehicles page

| Step | What happens |
|------|--------------|
| 1 | Wait until Marketplace is fully loaded |
| 2 | Open Vehicles category URL: `https://www.facebook.com/marketplace/category/vehicles` |
| 3 | Refresh the Vehicles page |
| 4 | Wait until **Filters** sidebar is visible on the left |

Bot is now on the Facebook **Vehicles** page with the filter sidebar ready.

---

### Stage 4/7 — Set location (FIRST, before price)

Location comes from the **active filter** (city, country, radius km).

| Step | What happens |
|------|--------------|
| 1 | Read current location text in sidebar (e.g. `Zurich · Within 65 km`) |
| 2 | If location already matches filter → **skip** (no dialog opened) |
| 3 | If different → click location row under **Filters** |
| 4 | **Change location** dialog opens |
| 5 | Type location from filter (e.g. `Zurich, Switzerland`) |
| 6 | Select **first suggestion** from dropdown |
| 7 | Set **Radius** field to filter value in km |
| 8 | Click **Apply** |
| 9 | Confirm sidebar shows updated city + radius |

**Order is fixed:** location is always applied **before** price.

---

### Stage 5/7 — Set price filter (on Vehicles sidebar)

Price comes from the **active filter** (`price_min`, `price_max`).

| Step | What happens |
|------|--------------|
| 1 | Find **Min** and **Max** price inputs in Filters sidebar |
| 2 | Type min price → press Enter |
| 3 | Type max price → press Enter |
| 4 | Facebook reloads listings with price applied |

If filter has no price range set, this stage is skipped.

**Facebook applies:** location + price  
**Backend applies later:** brand, model, mileage, year, fuel, transmission, keywords, match score

---

### Stage 6/7 — Read listings from Vehicles page

| Step | What happens |
|------|--------------|
| 1 | Scroll Vehicles page to load listing cards |
| 2 | Read all `/marketplace/item/` links from the grid |
| 3 | If filter has brands/models → only listings with a brand/model **hint** on the main page are checked further |
| 4 | For those hints → bot opens each listing detail page, reads title/price/description/mileage |
| 5 | Returns to Vehicles list URL |

Listings without brand/model hints on the main page are not opened in detail (unless filter has no brands/models set).

---

### Stage 7/7 — Match, save, notify (backend)

For each listing checked:

| Step | What happens |
|------|--------------|
| 1 | Run matching engine against full filter criteria |
| 2 | Score 0–100; exclude keywords = instant reject |
| 3 | Must pass **min match score** (default 80) |
| 4 | Duplicate check by listing ID + content hash → skip if already seen |
| 5 | Save new match to database |
| 6 | Send HTML email to active notification recipients (if notifications enabled) |

---

### Repeat cycles (monitoring stays ON)

After the first pass, location and price are **not re-applied** every time if nothing changed.

| Cycle | What happens |
|-------|--------------|
| First pass | Stages 0 → 7 full flow (login → Marketplace → Vehicles → location → price → scrape → match) |
| Next passes | Browser stays open → **refresh** same Vehicles URL → scrape new listings → match → notify |
| Interval | Next scan scheduled in **30–45 seconds** (change on Monitoring page, minimum 30s) |
| Scheduler | Backend checks every 60 seconds if next scan is due |

If you change filter location or price, bot detects the change and re-runs Stage 4 + 5 on next pass.

---

### Stop monitoring

Click **Stop** on dashboard:

1. Monitoring flag set to OFF
2. Chromium window closes
3. Facebook session cookies saved to `backend\data\facebook_session.json`
4. Next **Start** reuses saved login if session is still valid

**Clear session:** Settings → **Clear browser session** → wipes cookies and profile → next Start requires fresh Facebook login.

---

### Monitoring flow diagram

```
Dashboard → Start
    │
    ▼
Stage 0: Open Chromium
    │
    ▼
Stage 1: https://www.facebook.com/marketplace/
    │
    ├── Not logged in? → YOU log in (top header) → bot waits (max 15 min)
    │                      └── 5 min idle → login reminder email
    │
    ▼
Stage 2: Confirm login → save session
    │
    ▼
Stage 3: /marketplace/category/vehicles → refresh → Filters sidebar ready
    │
    ▼
Stage 4: Set location (city + radius from filter) → Apply
    │
    ▼
Stage 5: Set Min/Max price (from filter) → Enter
    │
    ▼
Stage 6: Scroll → read listings → open detail pages for brand/model hints
    │
    ▼
Stage 7: Match → save → email alert
    │
    ▼
Wait 30–45s → refresh Vehicles page → Stage 6 + 7 again (loop until Stop)
```

After backend restart: if monitoring was ON, it resumes automatically from saved session.

---

## Dashboard — What Each Page Does

| Page | Route | Function |
|------|-------|----------|
| Dashboard | `/` | Stats, charts, Start/Stop monitoring |
| Filters | `/filters` | Create, edit, delete search filters |
| Listings | `/listings` | View matched vehicles, export CSV, delete |
| Listing detail | `/listings/:id` | Full listing data and match score |
| Monitoring | `/monitoring` | Scan interval (min/max seconds, minimum 30s) |
| Notifications | `/notifications` | Sent email history |
| Logs | `/logs` | System activity log, export CSV, clear |
| Settings | `/settings` | Password, notification recipients, browser mode, clear Facebook session |
| Help | `/help` | Usage help |
| Login | `/login` | Admin authentication |

### Settings page — exact controls

| Control | What it does |
|---------|--------------|
| Notification recipients | Emails that receive match alerts |
| Send test email | Verifies SMTP from `backend\.env` |
| Send login reminder test | Sends sample Facebook login reminder email |
| Visible browser / Headless | Visible = Chromium window on Start (required for first Facebook login). Headless = hidden browser |
| Clear browser session | Wipes Facebook cookies/profile; next Start opens fresh login |
| Change password | Updates dashboard login password |
| Notifications on/off | Enables or disables email alerts for new matches |

---

## Filter System

Each filter defines what vehicles to find.

| Field | Purpose |
|-------|---------|
| Location (city, country, radius km) | Facebook Marketplace search area |
| Brands / Models | Allowed makes and models (OR within each field) |
| Price min / max | Applied on Facebook Vehicles page during scrape |
| Mileage min / max | Post-scrape matching |
| Year min / max | Post-scrape matching |
| Fuel / Transmission | Post-scrape matching |
| Include keywords | Listing must contain at least one |
| Exclude keywords | Listing rejected immediately |
| Min match score | Default 80 — listing must reach this score to save and notify |
| Active | Only active filters are used during scans |

### Default seeded filter (first run)

| Setting | Value |
|---------|-------|
| Name | Zurich Vehicle Search |
| Location | Zurich, Switzerland, 65 km |
| Price | CHF 3,000 – 7,000 |
| Min match score | 80 |
| Exclude keywords | Motorschaden, Defekt, Bastlerfahrzeug, Export, Unfallfahrzeug, Kein MFK, Ersatzteile, Schlachtfahrzeug |

Edit or add filters from **Filters** page. No code changes needed.

---

## Match Scoring

Listings are scored 0–100 on:

- Brand, model, price, mileage, year
- Fuel type and transmission (with aliases, e.g. TDI → diesel)
- Include / exclude keywords in title and description

Excluded keyword = score 0, no notification.  
Duplicate listings are detected by content hash and not notified twice.

---

## Email Setup (Gmail)

1. Enable 2-Factor Authentication on your Google account.
2. Google Account → Security → App Passwords → create password for Mail.
3. Put values in `backend\.env`:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
SMTP_FROM_EMAIL=your@gmail.com
SMTP_USE_TLS=true
```

4. Restart backend (`stop-backend.bat` → `start-backend.bat`).
5. Dashboard → Settings → add notification recipient → **Send test email**.

---

## Configuration Reference

### `backend\.env`

| Variable | Purpose | Default |
|----------|---------|---------|
| `ADMIN_EMAIL` | Dashboard login email | `admin@example.com` |
| `ADMIN_PASSWORD` | Dashboard login password | `admin123` |
| `SECRET_KEY` | JWT token signing | must change in production |
| `DATABASE_URL` | SQLite or PostgreSQL | `sqlite:///./marketplace_monitor.db` |
| `API_PORT` | Backend port | `8000` |
| `CORS_ORIGINS` | Allowed frontend origins | localhost:5173 |
| `SMTP_*` | Email sending | see above |

PostgreSQL example:

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/neondb?sslmode=require
```

### `backend\app\config.py` (Facebook paths)

| Setting | Path |
|---------|------|
| Session file | `backend\data\facebook_session.json` |
| Chrome profile | `backend\data\facebook_chrome_profile` |
| Playwright browsers | `backend\playwright-browsers` |

---

## Project Structure

```
Facebook monitoring/
├── start-backend.bat       Start backend + tunnel
├── stop-backend.bat        Stop backend
├── install-chromium.bat    One-time Chromium install
├── backend/
│   ├── run.py              Backend entry point
│   ├── .env                Secrets and config
│   ├── app/
│   │   ├── api/            REST routes
│   │   ├── models/         Database tables
│   │   ├── services/       Monitoring, matching, email, scheduler
│   │   ├── sources/        Scrapers (Facebook active; others placeholder)
│   │   └── seeds/          Default admin + filter on first run
│   └── data/               Database, Facebook session, PID file
└── frontend/
    └── src/
        ├── pages/          Dashboard pages
        ├── components/     UI
        ├── contexts/       Auth, monitoring, theme
        └── lib/            API client
```

---

## API Endpoints

Base URL: `http://127.0.0.1:8000/api`

| Group | Examples |
|-------|----------|
| Auth | `POST /auth/login`, `GET /auth/me` |
| Filters | `GET/POST/PUT/DELETE /filters` |
| Listings | `GET /listings`, `GET /listings/{id}`, export CSV |
| Monitoring | `POST /monitoring/start`, `POST /monitoring/stop`, settings |
| Dashboard | `GET /dashboard/stats`, `GET /dashboard/charts` |
| Notifications | recipients CRUD, test email, history |
| Logs | list, export, delete |

Interactive docs: `http://127.0.0.1:8000/docs`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Login fails on Vercel | Run `start-backend.bat`, verify tunnel URL in Vercel `BACKEND_URL`, redeploy |
| "Backend not reachable" | Run `start-backend.bat`, wait for "Application ready" in backend window |
| "Database still connecting" | Wait 30 seconds, retry login |
| Port 8000 in use | Run `stop-backend.bat`, close old backend CMD windows |
| Chromium missing | Run `install-chromium.bat` |
| Facebook not scanning | Log in manually in Chromium window; check filter is **Active** |
| No emails | Set SMTP in `backend\.env`, add recipient in Settings, send test email |
| Wrong Facebook account | Settings → Clear browser session → Start again → log in fresh |

---

## Important Notes

- Backend and Playwright must run on your PC. Vercel hosts only the frontend UI.
- Facebook UI changes may break scraping and require code updates.
- Change default admin password before production use.
- Do not commit `backend\.env` — it contains passwords.
