# Prompt 3: AWS RDS PostgreSQL + WebSocket Progress Tracking

Build on top of the existing FastAPI backend. Add AWS RDS PostgreSQL for storing users and analysis history, and FastAPI WebSocket for live progress updates.

## What to build

### Database (AWS RDS PostgreSQL)

- Connect to an AWS RDS PostgreSQL instance using `asyncpg` or `psycopg2`
- Store the database connection string in `.env` (`DATABASE_URL`)
  - Example: `postgresql://username:password@your-rds-endpoint.rds.amazonaws.com:5432/costdetective`
- Create two tables on startup:
  - `users` — id, email, password_hash, created_at
  - `analyses` — id, user_id, regions (array), services (array), resources_scanned (int), issues_found (int), estimated_savings (text), analysis_result (jsonb), status, created_at
- After AI analysis completes, store the full result in the `analyses` table
- Add a `GET /api/history` endpoint that returns past analyses for the authenticated user

### AWS RDS Setup

Before running:
1. Create an RDS PostgreSQL instance in AWS Console (or via CLI)
2. Configure security group to allow inbound traffic on port 5432 from your application
3. Create database and get the endpoint (looks like: `mydb.xxxxx.rds.amazonaws.com`)
4. Add to `.env`: `DATABASE_URL=postgresql://user:password@endpoint:5432/dbname`

### WebSocket Progress

- Add a WebSocket endpoint `ws://localhost:8000/ws/progress/{analysis_id}`
- During the `POST /api/analyze` flow, push progress messages through the WebSocket at each stage:
  - `"Validating AWS credentials..."`
  - `"Fetching regions..."`
  - `"Scanning EC2 instances..."`
  - `"Scanning RDS databases..."`
  - `"Scanning S3 buckets..."`
  - `"Scanning Lambda functions..."`
  - `"Analyzing costs with AI..."`
  - `"Storing results in database..."`
  - `"Analysis complete"`
- The frontend will connect to this WebSocket to show live progress

### Update .env.example

```
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
OPENAI_API_KEY=your_openai_key
DATABASE_URL=postgresql://username:password@your-rds-endpoint.rds.amazonaws.com:5432/costdetective
JWT_SECRET=your_jwt_secret_key
```

## Project structure update

```
backend/
├── main.py          (updated — history endpoint, WebSocket, DB init)
├── aws_scanner.py   (no change)
├── ai_analyzer.py   (no change)
├── db.py            (new — DB connection, table creation, queries)
├── requirements.txt (updated — add asyncpg/psycopg2, websockets)
├── .env.example     (updated)
```

Refer to `Architecture.MD` and `RequestFlow.MD`. This covers steps ④ and ⑥ of the request flow.
