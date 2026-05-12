<div align="center">

# 🏢 Employee Attendance Tracking System

**Enterprise-grade attendance management with biometric synchronization, real-time analytics, and role-based access control.**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.3-61DAFB?style=flat-square&logo=react)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql)](https://www.postgresql.org/)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?style=flat-square&logo=supabase)](https://supabase.com/)
[![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?style=flat-square&logo=render)](https://render.com/)
[![Vercel](https://img.shields.io/badge/Deploy-Vercel-000000?style=flat-square&logo=vercel)](https://vercel.com/)

[Live Demo](#) · [API Docs](#api-documentation) · [Report Bug](#) · [Architecture Overview](#architecture)

</div>

---

## 📋 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Authentication System](#authentication-system)
- [Biometric Integration](#biometric-integration)
- [Dashboard Overview](#dashboard-overview)
- [Database Design](#database-design)
- [Project Structure](#project-structure)
- [Local Setup](#local-setup)
- [Deployment Guide](#deployment-guide)
- [API Documentation](#api-documentation)
- [Environment Variables](#environment-variables)

---

## Overview

The **Employee Attendance Tracking System** is a full-stack enterprise application that automates workforce attendance management. It replaces manual HR processes with a real-time, data-driven platform that integrates directly with Matrix COSEC biometric devices.

### Business Problem Solved

| Before | After |
|--------|-------|
| Manual CSV exports from biometric devices | Automated API synchronization every 15 minutes |
| No real-time visibility | Live attendance dashboards per employee and team |
| No accountability metrics | Attendance scores with late-arrival weighting |
| Flat access — everyone sees everything | Role-based access: Employee / Manager / Admin |
| Manual data corrections overwritten | `MANUAL_CSV` provenance protects corrected records |

---

## Key Features

### 🔐 Enterprise Authentication
- Custom `employee_code + password` login flow (migrated from Google OAuth)
- **Brute-force protection**: Account lockout after 5 failed attempts (configurable)
- **Mandatory first-login password change** enforced via `password_reset_required` flag
- Admin password reset with forced change on next login
- `bcrypt` password hashing (12 rounds)

### 📊 Attendance Analytics
- **Attendance Score**: `(Present + Late × 0.65) / WorkingDays × 100`
- **Consistency Score**: Based on standard deviation of login times (0 = erratic, 100 = perfectly consistent)
- **Monthly Present %**: Tracks actual attendance rate excluding Sundays and holidays
- Rule-based **Insights Engine**: Dynamic alerts for absences, late patterns, and work-hour trends
- Work Hours trend chart (last 30 days)
- Heatmap calendar visualization

### 📡 Biometric Synchronization (Matrix COSEC)
- Automated **APScheduler** runs 3-phase sync cycle every 15 minutes:
  1. `sync_users()` — Pull employee master from COSEC → `employees` table
  2. `sync_daily()` — Pull daily punch data → `attendance_logs` table
  3. `sync_monthly()` — Pull monthly summaries → `attendance_monthly` table
- **Provenance protection**: Records marked `MANUAL_CSV` are never overwritten by API sync
- Full sync audit trail in `sync_logs` table
- Admin-triggerable manual sync via `/admin/sync` API

### 👥 Team Hierarchy & Manager Views
- Recursive CTE-based org chart traversal (`WITH RECURSIVE subordinates`)
- Managers see attendance for their entire downstream team
- `Team Attendance Rate` KPI for manager dashboards
- Access-scoped: employees cannot view team data

### 📤 Bulk Data Management
- Admin CSV upload for bulk attendance and employee data
- Strict validation with per-row error reporting
- Post-upload re-aggregation of only affected months (efficient)
- Post-upload Redis cache invalidation

### ⚡ Performance & Caching
- **SWR (Stale-While-Revalidate)** cache in `cache.js`: instant load from `localStorage`, background refresh
- **30s cooldown** guard prevents infinite polling loops
- In-flight request deduplication — no concurrent fetches for same key
- Redis server-side cache with pattern-based invalidation after sync
- `attendance_monthly` aggregation table avoids runtime `SUM` on millions of log rows

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Vercel)                       │
│   React + Vite + Tailwind CSS + Recharts                       │
│                                                                │
│   LoginPage → AuthContext → JWT stored in localStorage        │
│       ↓                                                        │
│   EmployeeDashboard / ManagerDashboard / AdminPanel            │
│       ↓                                                        │
│   useCachedFetch (SWR) → axios client → /api/*                │
└────────────────────────┬───────────────────────────────────────┘
                         │ HTTPS / REST
┌────────────────────────▼───────────────────────────────────────┐
│                     BACKEND (Render)                           │
│   FastAPI + SQLAlchemy (async) + APScheduler                  │
│                                                                │
│   Routers: /auth /attendance /hierarchy /admin/csv /admin/sync │
│       ↓                                                        │
│   Services: insights.py → aggregation.py → cache.py           │
│       ↓                          ↑                             │
│   sync_orchestrator.py ──────────┘                            │
│       ↑                                                        │
│   biometric_client.py → Matrix COSEC API (HTTP/POST)          │
└──────────────┬────────────────────────┬───────────────────────┘
               │                        │
┌──────────────▼──────┐    ┌────────────▼──────────────────────┐
│  PostgreSQL          │    │  Redis                            │
│  (Supabase)          │    │  (Render / Upstash)               │
│                      │    │                                   │
│  employees           │    │  dashboard:{employee_id}:*        │
│  attendance_logs     │    │  attendance:today:{code}:{date}   │
│  attendance_monthly  │    │                                   │
│  sync_logs           │    └───────────────────────────────────┘
└─────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend Framework** | React 18 + Vite | SPA with fast HMR |
| **Styling** | Tailwind CSS 3 | Utility-first CSS |
| **Charts** | Recharts | Work hours trend, heatmap |
| **HTTP Client** | Axios | API calls with JWT interceptor |
| **Backend Framework** | FastAPI 0.115 | Async REST API |
| **ORM** | SQLAlchemy 2.0 (async) | Database access layer |
| **Database** | PostgreSQL 16 (Supabase) | Primary data store |
| **Caching** | Redis + in-memory SWR | Dashboard performance |
| **Background Tasks** | APScheduler 3.10 | Biometric sync scheduler |
| **Authentication** | python-jose (JWT) + passlib (bcrypt) | Secure enterprise auth |
| **Biometric API** | Matrix COSEC REST API | Punch data source |
| **Containerization** | Docker + Docker Compose | Local dev environment |
| **Deployment** | Render (backend) + Vercel (frontend) + Supabase (DB) | Production |

---

## Authentication System

```
Employee enters employee_code + password
        ↓
POST /auth/login
        ↓
1. Normalize employee_code (strip + uppercase)
2. Lookup active employee in DB
3. Check account lockout (account_locked_until > now)
4. Verify bcrypt password hash
5. On failure: increment failed_login_attempts
   → Lock account at MAX_LOGIN_ATTEMPTS (default: 5)
6. On success: reset failure count, update last_login
7. Issue JWT: { sub: email, employee_id, role, exp }
        ↓
Frontend: store token → AuthContext → role-based routing
        ↓
If password_reset_required == true → PasswordChangeModal (mandatory)
```

**RBAC Roles:**
| Role | Access |
|------|--------|
| `EMPLOYEE` | Own dashboard only |
| `MANAGER` | Own dashboard + Team dashboard for subordinates |
| `ADMIN` | All dashboards + CSV upload + Sync management + Password reset |

---

## Biometric Integration

The system integrates with **Matrix COSEC** biometric devices via their Web API.

### Sync Architecture
```
APScheduler (every 15 min)
    ↓
BiometricClient.run_full_sync()
    ↓
Phase 1: sync_users()
    COSEC /api.svc/v2/user → employees table
    → Resolves manager hierarchy (2-pass algorithm)

Phase 2: sync_daily()
    COSEC /api.svc/v2/attendance-daily → attendance_logs
    → Auto-detects XML or JSON response format
    → Protects MANUAL_CSV records from overwrite
    → Triggers monthly re-aggregation for affected months

Phase 3: sync_monthly()
    COSEC /api.svc/v2/attendance-monthly → attendance_monthly
    → Invalidates Redis dashboard caches
    ↓
SyncLog entry: RUNNING → SUCCESS/FAILED (with counts + errors)
```

**To enable biometric sync**, set in `backend/.env`:
```env
BIOMETRIC_SYNC_ENABLED=true
MATRIX_COSEC_BASE_URL=https://cosec.yourcompany.com/cosec
MATRIX_COSEC_USERNAME=SA
MATRIX_COSEC_PASSWORD=your_password
```

---

## Dashboard Overview

### Employee Dashboard (`/`)
- **Attendance Score**: Weighted formula `(Present + Late×0.65) / WorkingDays × 100`
- **Today Status**: Live PRESENT / ABSENT / LATE / ON_LEAVE badge
- **Work Hours Today**: Parsed from `gross_work_hrs` interval field
- **Monthly Present %**: With trend indicator (↑/↓ vs previous period)
- **Work Hours Trend Chart**: 30-day line chart (Recharts)
- **Attendance Heatmap**: Calendar-style density visualization
- **Monthly Summary Cards**: Present / Absent / Late / Leave counts
- **Insights Panel**: Rule-based alerts (perfect attendance, late warnings, absence flags)
- **Attendance Logs Table**: Last 30 days with status badges

### Manager Dashboard (`/team`)
- **Team Attendance Rate**: Aggregate across all subordinates
- **Team Member List**: Individual attendance for direct and indirect reports
- **Recursive Hierarchy**: Fetches entire org tree via PostgreSQL `WITH RECURSIVE`

### Admin Panel (`/admin`)
- **CSV Upload**: Bulk attendance import with row-level validation
- **Sync Management**: Trigger manual biometric sync, view sync logs
- **Password Reset**: Reset any employee's password to system default

---

## Database Design

### Core Tables

```sql
-- Employee master with hierarchy
CREATE TABLE employees (
    id                      SERIAL PRIMARY KEY,
    employee_code           VARCHAR(20) UNIQUE NOT NULL,
    email                   VARCHAR(255) UNIQUE NOT NULL,
    full_name               VARCHAR(255),
    role                    VARCHAR(20) DEFAULT 'EMPLOYEE',  -- EMPLOYEE|MANAGER|ADMIN
    department              VARCHAR(100),
    manager_id              INTEGER REFERENCES employees(id),
    password_hash           VARCHAR(255),
    password_reset_required BOOLEAN DEFAULT TRUE,
    failed_login_attempts   INTEGER DEFAULT 0,
    account_locked_until    TIMESTAMPTZ,
    is_active               BOOLEAN DEFAULT TRUE
);

-- Daily punch records
CREATE TABLE attendance_logs (
    id              SERIAL PRIMARY KEY,
    employee_id     INTEGER REFERENCES employees(id) ON DELETE CASCADE,
    log_date        DATE NOT NULL,
    first_in        TIMESTAMPTZ,
    last_out        TIMESTAMPTZ,
    gross_work_hrs  INTERVAL,
    net_work_hrs    INTERVAL,
    status          VARCHAR(30),   -- PRESENT|ABSENT|LATE|HALF_DAY|ON_LEAVE|WEEKEND
    is_late         BOOLEAN DEFAULT FALSE,
    data_source     VARCHAR(20),   -- API|MANUAL_CSV|AGGREGATED
    raw_payload     JSONB,
    UNIQUE(employee_id, log_date)  -- One record per employee per day
);

-- Pre-aggregated monthly summaries (avoids runtime GROUP BY on logs)
CREATE TABLE attendance_monthly (
    id              SERIAL PRIMARY KEY,
    employee_id     INTEGER REFERENCES employees(id) ON DELETE CASCADE,
    month           INTEGER NOT NULL,
    year            INTEGER NOT NULL,
    total_present   INTEGER DEFAULT 0,
    total_absent    INTEGER DEFAULT 0,
    total_late      INTEGER DEFAULT 0,
    total_half_day  INTEGER DEFAULT 0,
    total_leave     INTEGER DEFAULT 0,
    avg_work_hrs    INTERVAL,
    data_source     VARCHAR(20),
    UNIQUE(employee_id, month, year)
);

-- Biometric sync audit trail
CREATE TABLE sync_logs (
    id                  SERIAL PRIMARY KEY,
    sync_type           VARCHAR(20),   -- USER|DAILY|MONTHLY
    status              VARCHAR(20),   -- RUNNING|SUCCESS|FAILED
    triggered_by        VARCHAR(50),   -- SCHEDULER|MANUAL
    started_at          TIMESTAMPTZ DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    duration_seconds    INTEGER,
    records_fetched     INTEGER,
    records_inserted    INTEGER,
    records_updated     INTEGER,
    records_skipped     INTEGER,
    records_errors      INTEGER,
    error_log           JSONB,
    metadata_payload    JSONB
);
```

---

## Project Structure

```
prag_project/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app factory + lifespan
│   │   ├── config.py                # Pydantic settings from env vars
│   │   ├── database.py              # SQLAlchemy async engine + session
│   │   ├── models/
│   │   │   ├── employee.py          # Employee ORM model
│   │   │   ├── attendance.py        # AttendanceLog + AttendanceMonthly
│   │   │   └── sync_log.py          # SyncLog ORM model
│   │   ├── routers/
│   │   │   ├── auth.py              # POST /auth/login, /auth/me, /auth/change-password
│   │   │   ├── attendance.py        # GET /attendance/me/dashboard, /team
│   │   │   ├── hierarchy.py         # GET /hierarchy/tree, /team/dashboard
│   │   │   ├── admin_csv.py         # POST /admin/csv/upload
│   │   │   └── admin_sync.py        # POST /admin/sync/trigger, GET /admin/sync/logs
│   │   ├── services/
│   │   │   ├── insights.py          # Attendance score + insights engine
│   │   │   ├── aggregation.py       # Monthly rollup (idempotent)
│   │   │   ├── hierarchy.py         # Recursive CTE subordinate queries
│   │   │   ├── biometric_client.py  # Unified COSEC API facade
│   │   │   ├── sync_orchestrator.py # 3-phase sync lifecycle manager
│   │   │   ├── sync_scheduler.py    # APScheduler setup
│   │   │   ├── matrix_daily.py      # Daily Attendance API service
│   │   │   ├── matrix_monthly.py    # Monthly Attendance API service
│   │   │   ├── matrix_user_master.py# User Master API service
│   │   │   ├── csv_parser.py        # CSV upload validation + ingestion
│   │   │   └── cache.py             # Redis cache + invalidation
│   │   ├── schemas/                 # Pydantic request/response schemas
│   │   └── utils/
│   │       ├── security.py          # JWT creation/verification, bcrypt
│   │       └── logging_setup.py     # Structured JSON logging
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example                 # ← Copy to .env and fill in values
│
├── frontend/
│   ├── src/
│   │   ├── api/client.js            # Axios instance + JWT interceptor
│   │   ├── auth/
│   │   │   ├── AuthContext.jsx      # Global auth state + JWT lifecycle
│   │   │   └── RoleGuard.jsx        # Role-based route protection
│   │   ├── pages/
│   │   │   ├── LoginPage.jsx        # Enterprise login form
│   │   │   ├── EmployeeDashboard.jsx# Personal attendance KPIs + charts
│   │   │   ├── ManagerDashboard.jsx # Team attendance overview
│   │   │   └── AdminPanel.jsx       # CSV upload + sync management
│   │   ├── components/
│   │   │   ├── Layout/Layout.jsx    # Sidebar + topbar shell
│   │   │   ├── dashboard/           # StatCard, TrendChart, HeatmapCalendar, etc.
│   │   │   └── ui/                  # Badge, Card, Skeleton, Alert, etc.
│   │   └── lib/
│   │       ├── cache.js             # SWR cache (memory + localStorage)
│   │       └── ThemeProvider.jsx    # Dark/light theme context
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── .env.example                 # ← Copy to .env and fill in values
│
├── db/
│   ├── init.sql                     # Full schema initialization
│   ├── supabase_schema.sql          # Supabase-specific schema
│   └── migration_*.sql              # Incremental migration scripts
│
├── docker-compose.yml               # Full local stack (Postgres + Redis + Backend + Frontend)
├── render.yaml                      # Render deployment blueprint (IaC)
├── .gitignore
├── .env.example                     # Root-level env reference
└── README.md
```

---

## Local Setup

### Prerequisites
- Python 3.10+
- Node.js 20+
- PostgreSQL 16 (or Docker)
- Redis (or Docker)

### Option A: Docker Compose (Recommended)
```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/employee-attendance-system.git
cd employee-attendance-system

# 2. Copy and configure environment variables
cp backend/.env.example backend/.env
# Edit backend/.env with your values (see Environment Variables section)

# 3. Start the full stack
docker compose up --build

# Access:
# Frontend: http://localhost:5173
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

### Option B: Manual Setup

**Backend:**
```bash
cd backend

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — set DATABASE_URL and JWT_SECRET_KEY at minimum

# Run the development server
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend

# Install dependencies
npm install

# Configure environment (for local dev, no changes needed — Vite proxy handles API routing)
cp .env.example .env

# Start the development server
npm run dev
# → http://localhost:5173
```

### Initial Data Setup

After the backend starts, the database tables are auto-created. To import employees:

1. **Via Admin Panel**: Navigate to `/admin` and upload a CSV file.
2. **Via Biometric Sync**: Enable `BIOMETRIC_SYNC_ENABLED=true` in `.env` and configure COSEC credentials.
3. **Via SQL**: Run `db/init.sql` against your PostgreSQL instance.

---

## Deployment Guide

### Production Stack: Render + Vercel + Supabase

#### 1. Supabase (Database)
1. Create a new Supabase project.
2. Run `db/supabase_schema.sql` in the SQL Editor.
3. Copy the **Transaction** connection string from: `Settings → Database → Connection String → Transaction (port 6543)`.

#### 2. Render (Backend)
```bash
# Option A: Auto-deploy via render.yaml (recommended)
# Connect your GitHub repo to Render — it detects render.yaml automatically.

# Option B: Manual web service
# Runtime: Python
# Root Directory: backend
# Build Command: pip install -r requirements.txt
# Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**Required environment variables in Render dashboard:**
| Variable | Value |
|----------|-------|
| `DATABASE_URL` | Supabase transaction pooler URL |
| `JWT_SECRET_KEY` | Generate via `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FRONTEND_URL` | Your Vercel app URL |
| `MATRIX_COSEC_BASE_URL` | Your COSEC appliance URL (or leave blank) |
| `BIOMETRIC_SYNC_ENABLED` | `true` or `false` |
| `REDIS_URL` | Auto-linked from Render Redis service |

#### 3. Vercel (Frontend)
```bash
# Install Vercel CLI
npm i -g vercel

# Deploy from frontend directory
cd frontend
vercel --prod

# Set environment variable in Vercel dashboard:
# VITE_API_BASE_URL = https://your-backend.onrender.com
```

---

## API Documentation

When the backend is running, interactive API docs are available at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Key Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/auth/login` | None | Login with employee_code + password |
| `GET` | `/auth/me` | JWT | Get current user profile |
| `POST` | `/auth/change-password` | JWT | Change own password |
| `POST` | `/auth/reset-password` | ADMIN | Reset another user's password |
| `GET` | `/attendance/me/dashboard` | JWT | Full employee dashboard data |
| `GET` | `/hierarchy/team/dashboard` | MANAGER+ | Team attendance summary |
| `POST` | `/admin/csv/upload` | ADMIN | Upload attendance CSV |
| `POST` | `/admin/sync/trigger` | ADMIN | Trigger manual biometric sync |
| `GET` | `/admin/sync/logs` | ADMIN | View sync history |
| `GET` | `/health` | None | Health check (DB + Redis) |

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | ✅ | SQLite | PostgreSQL connection string |
| `JWT_SECRET_KEY` | ✅ | dev-key | Secret for JWT signing |
| `FRONTEND_URL` | ✅ | localhost:5173 | CORS allowed origin |
| `DEFAULT_ADMIN_PASSWORD` | ✅ | Admin@123 | Initial employee password |
| `REDIS_URL` | Recommended | localhost:6379 | Redis connection string |
| `MATRIX_COSEC_BASE_URL` | Optional | (empty) | COSEC appliance base URL |
| `MATRIX_COSEC_USERNAME` | Optional | SA | COSEC admin username |
| `MATRIX_COSEC_PASSWORD` | Optional | (empty) | COSEC admin password |
| `BIOMETRIC_SYNC_ENABLED` | Optional | false | Enable background scheduler |
| `SYNC_INTERVAL_MINUTES` | Optional | 15 | Sync frequency |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Optional | 120 | JWT expiry |
| `MAX_LOGIN_ATTEMPTS` | Optional | 5 | Brute-force lockout threshold |
| `ACCOUNT_LOCKOUT_MINUTES` | Optional | 15 | Lockout duration |

### Frontend (`frontend/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_API_BASE_URL` | Production only | Backend API URL (leave blank for local dev) |

---

## Key Design Decisions

1. **FastAPI over Django/Flask**: Native async support critical for concurrent biometric API calls and PostgreSQL pool management.
2. **`attendance_monthly` aggregation table**: Eliminates expensive `GROUP BY` queries on `attendance_logs` at dashboard load time. Monthly data is pre-computed on every sync/upload.
3. **Idempotent aggregation**: The aggregation service can be re-run any number of times safely — it always produces the same result.
4. **SWR cache with cooldown**: The frontend serves stale data instantly while refreshing in the background. A 30-second cooldown prevents infinite polling loops.
5. **MANUAL_CSV provenance**: Records uploaded manually by admins are tagged `data_source='MANUAL_CSV'`. The biometric sync engine never overwrites these, preserving HR corrections.
6. **Recursive CTE for hierarchy**: Avoids the N+1 problem when fetching team data across deep org trees. A single SQL query returns the entire subtree.
7. **APScheduler over Celery (for sync)**: Runs in-process, eliminating the need for a separate worker service for the scheduler. Celery is retained for heavy background jobs.

---

## Security Considerations

- ✅ All secrets managed via environment variables (never hardcoded)
- ✅ Passwords hashed with bcrypt (never stored in plaintext)
- ✅ JWT tokens expire after 120 minutes
- ✅ Brute-force protection with account lockout
- ✅ CORS restricted to configured `FRONTEND_URL`
- ✅ MANUAL_CSV records protected from API overwrites
- ✅ Role-based access control on all team/admin endpoints
- ✅ Structured JSON logging (no sensitive data in logs)

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'feat: add your feature'`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

---

<div align="center">

Built with ❤️ for enterprise HR operations

</div>
