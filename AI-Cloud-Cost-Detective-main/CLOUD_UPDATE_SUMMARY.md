# AWS Cloud Cost Detective - Architecture Summary

## Project Overview

This is a cloud cost optimization tool that **scans your AWS infrastructure, detects cost issues, and provides AI-powered recommendations** to save money.

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | React + TypeScript + Tailwind | Modern, dark-themed UI |
| **Backend** | FastAPI (Python) | Fast, async API server |
| **Cloud Access** | boto3 + AWS SDK | Query AWS resources |
| **AI Analysis** | OpenAI GPT-4 | Intelligent cost analysis |
| **Database** | AWS RDS PostgreSQL | Store users & history |
| **Real-time Updates** | WebSocket | Live progress tracking |
| **Authentication** | JWT + bcrypt | Secure user auth |

---

## Architecture

```
User (Browser)
    ↓
React Frontend (Vite + TypeScript + Tailwind)
    ↓
FastAPI Backend (Python)
    ↓
AWS SDK (boto3) ← Scans your AWS account
    ↓
OpenAI API ← Analyzes costs with AI
    ↓
AWS RDS PostgreSQL ← Stores results
    ↓
WebSocket → Live progress updates
    ↓
User sees: Cost report + Recommendations + Savings estimate
```

---

## Backend Modules

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, routes, auth middleware |
| `aws_scanner.py` | boto3 scanning (EC2, RDS, S3, Lambda, etc.) |
| `ai_analyzer.py` | OpenAI GPT-4 cost analysis |
| `db.py` | AWS RDS PostgreSQL connection and queries |

---

## AWS Services Scanned

```python
import boto3

ec2 = boto3.client('ec2', region_name='us-east-1')
rds = boto3.client('rds', region_name='us-east-1')
s3  = boto3.client('s3')
lmb = boto3.client('lambda', region_name='us-east-1')

ec2.describe_instances()
rds.describe_db_instances()
s3.list_buckets()
lmb.list_functions()
```

**Services supported:**
- EC2 Instances
- RDS Databases
- S3 Buckets
- Lambda Functions
- EBS Volumes
- Elastic IPs
- NAT Gateways
- CloudWatch Logs

---

## Database Schema

```sql
-- Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Analyses table
CREATE TABLE analyses (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    regions TEXT[],
    services TEXT[],
    resources_scanned INTEGER,
    issues_found INTEGER,
    estimated_savings TEXT,
    analysis_result JSONB,
    status TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## Environment Variables

```env
# AI Engine — choose one (leave blank to use built-in rule engine)
OPENAI_API_KEY=sk-proj-your_key_here
# ANTHROPIC_API_KEY=sk-ant-...
# GOOGLE_API_KEY=AIza...
# GROQ_API_KEY=gsk_...

# Database
DATABASE_URL=postgresql://costdetective:changeme123@localhost:5432/costdetective

# Security (required — minimum 32 characters)
JWT_SECRET=random_long_secret_string
```

> **Cloud credentials are entered via the dashboard UI** — not in `.env`:
> - AWS Access Key ID + Secret → Settings panel
> - Azure Subscription ID + Service Principal → Azure Credentials panel
> - GCP Project ID + service account JSON → GCP Credentials panel

---

## Typical Use Case

```
1. User signs up → Creates account
2. User logs in → Gets JWT token
3. User selects AWS regions + services → e.g., us-east-1, ec2, rds
4. User clicks "Run Analysis" → Backend scans AWS via boto3
5. Live progress shown → "Scanning EC2...", "Analyzing costs...", etc.
6. AI provides recommendations → "Downsize instance to save $50/month"
7. User sees report → Severity badges, cost savings, fix commands
8. User can view history → Past analyses stored in RDS
```

---

## Project Structure

```
AI-Cloud-Cost-Detective/
│
├── GETTING_STARTED.md       ← Start here
├── AWS_QUICK_CHECKLIST.md   ← What you need
├── AWS_SETUP_GUIDE.md       ← Detailed setup
├── Architecture.MD          ← Architecture diagram
├── README.md                ← Project overview
├── RequestFlow.MD           ← Request flow diagram
│
├── prompts/
│   ├── 01-fastapi-aws-sdk.md
│   ├── 02-openai-analysis-aws.md
│   ├── 03-aws-rds-postgres-websocket.md
│   ├── 04-react-frontend-auth-aws.md
│   └── 05-integrate-frontend-backend-aws.md
│
├── backend/ (TO CREATE)
│   ├── main.py
│   ├── aws_scanner.py
│   ├── ai_analyzer.py
│   ├── db.py
│   ├── requirements.txt
│   ├── .env
│   └── venv/
│
└── frontend/ (TO CREATE)
    ├── src/
    │   ├── pages/
    │   ├── components/
    │   └── App.tsx
    ├── package.json
    └── index.html
```

---

## Estimated Costs

### AWS
- **Free Tier (first 12 months)**: $0
  - EC2 t2/t3 micro: 750 hrs/month free
  - RDS db.t3.micro: 750 hrs/month free
  - S3: 5 GB free
- **After free tier**: ~$45-50/month
  - RDS db.t3.micro: ~$12-15/month
  - NAT Gateway (optional): ~$32/month
  - Data transfer: ~$1-5/month

### OpenAI
- **Per analysis**: ~$0.01-0.10

---

## Next Steps

1. **Read** `AWS_QUICK_CHECKLIST.md` → Get all requirements
2. **Follow** `AWS_SETUP_GUIDE.md` → Step-by-step setup
3. **Build** using `prompts/01-05` → Create backend & frontend
4. **Test** each component → Verify it works
5. **Deploy** (optional) → Put on AWS or cloud platform

---

**Project**: AI Cloud Cost Detective (AWS Edition)  
**Status**: Ready to build  
**Generated**: 2025
