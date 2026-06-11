# Attendance Dashboard Backend

## Phase 1

This backend provides:
- Supabase authentication integration
- JWT token validation
- Role-based access control for CEO and Employee dashboards
- Protected routes via FastAPI
- User profile verification using the `profiles` table

## Install

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run locally

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Required environment variables

Create a `.env` file in `backend/` with:

```text
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
JWT_SECRET=
CORS_ORIGINS=http://localhost:5173
```

## API Endpoints

- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/ceo/dashboard`
- `GET /api/employee/dashboard`
