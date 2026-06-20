# Facebook Marketplace Vehicle Monitoring System

Production-ready monitoring platform for Facebook Marketplace vehicle listings with admin dashboard, email notifications, and intelligent filtering.

## Quick Start (Local Development)

### Prerequisites
- Python 3.11+
- Node.js 18+
- Playwright Chromium (installed automatically)

### 1. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
playwright install chromium
copy .env.example .env       # Edit SMTP credentials
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

### 3. Login

Open http://localhost:5173

- **Email:** admin@example.com
- **Password:** admin123

Change credentials immediately in production.

## SMTP Setup (Gmail App Password)

1. Enable 2-Factor Authentication on your Google account
2. Go to Google Account → Security → App Passwords
3. Create an app password for "Mail"
4. In Dashboard → Settings → SMTP Configuration:
   - SMTP Host: `smtp.gmail.com`
   - SMTP Port: `587`
   - Email: your Gmail address
   - App Password: the 16-character app password

## Default Client Filters (Pre-seeded)

- Location: Zurich, Switzerland (65km radius)
- Brands: Volkswagen, Audi, Seat, Skoda
- Models: Golf, Passat, Touran, A3, A4, Octavia, Superb, Leon
- Price: CHF 3,000 – 7,000
- Mileage: Below 180,000 km
- Include keywords: DSG, Serviceheft gepflegt, 2.0 TDI, etc.
- Exclude keywords: Motorschaden, Unfallfahrzeug, etc.

## Architecture

```
backend/
  app/
    api/          # REST API routes
    models/       # SQLAlchemy database models
    services/     # Business logic (matching, email, monitoring)
    sources/      # Marketplace scrapers (facebook, autoscout24, tutti...)
    repositories/ # Data access layer
    seeds/        # Default data seeding

frontend/
  src/
    pages/        # Dashboard pages
    components/   # Reusable UI components
    contexts/     # Auth, theme, toast
    lib/          # API client, utilities
```

## API Documentation

When backend is running: http://127.0.0.1:8000/docs

## Features

- 24/7 Facebook Marketplace monitoring
- Advanced filtering (location, brand, model, price, mileage, keywords)
- Intelligent match scoring (0-100)
- Duplicate detection (persists across restarts)
- HTML email notifications via SMTP
- Full admin dashboard (no code changes needed)
- Activity logging
- Multi-platform ready architecture
- Dark/Light mode

## Project Deliverables

- Complete source code with full ownership
- Web-based admin dashboard
- Marketplace monitoring and filtering system
- Email notification system (SMTP App Password)
- Duplicate detection functionality
- Setup documentation (this file)

## Notes

Facebook Marketplace has no official API. The system uses automated monitoring via Playwright and may require maintenance if Facebook changes its platform.
