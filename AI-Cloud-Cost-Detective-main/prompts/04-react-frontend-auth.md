# Prompt 4: React Frontend + Custom JWT Auth

Create the React frontend in a `frontend/` folder with custom JWT authentication.

## What to build

### Setup

- Use Vite + React + TypeScript.
- Use Tailwind CSS for styling. Clean, modern, dark-themed UI.

### Auth (Custom JWT)

- Add auth endpoints to the FastAPI backend:
  - `POST /api/auth/signup` — accepts email + password, hashes password with bcrypt, stores in `users` table, returns JWT.
  - `POST /api/auth/login` — validates credentials, returns JWT.
- Use `PyJWT` and `bcrypt` on the backend. Store `JWT_SECRET` in `.env`.
- On the frontend, store JWT in localStorage. Include it in all API requests via `Authorization: Bearer <token>` header.
- Redirect to login page if not authenticated.

### Pages

1. **Login / Signup** — Clean auth forms with email and password.
2. **Dashboard** — Multi-select for AWS regions (us-east-1, us-west-2, eu-west-1, etc.), multi-select for services (EC2, RDS, S3, Lambda, etc.), a "Run Analysis" button, and a progress section showing live status.
3. **Analysis Report** — Displays the AI analysis: summary card with total resources scanned, issues found, and estimated monthly savings; issues list with resource name, service type, severity badge (red/yellow/green), explanation, and fix command in a copyable code block.
4. **History** — Lists past analyses from `GET /api/history` with regions scanned, services analyzed, date, issues found, and estimated savings. Clicking one opens the full report.

### Project structure

```
frontend/
├── src/
│   ├── App.tsx
│   ├── main.tsx
│   ├── pages/
│   │   ├── Login.tsx
│   │   ├── Signup.tsx
│   │   ├── Dashboard.tsx
│   │   ├── Report.tsx
│   │   └── History.tsx
│   ├── components/
│   │   ├── ProgressTracker.tsx
│   │   ├── Navbar.tsx
│   │   └── ServiceSelector.tsx
│   ├── types.ts
│   └── api.ts
├── package.json
├── tailwind.config.js
├── index.html
```

Update `backend/requirements.txt` — add `PyJWT`, `bcrypt`.

Refer to `Architecture.MD` and `RequestFlow.MD`. This covers step ① of the request flow and the UI layer.
