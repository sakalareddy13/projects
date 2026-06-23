# AWS Cloud Cost Detective - Quick Start Checklist

## What You Need to Get

### 1. AWS Account
- [ ] Create AWS account at https://aws.amazon.com
- [ ] Sign in to AWS Management Console
- [ ] Set default region (us-east-1 recommended)

### 2. AWS Credentials
- [ ] Create IAM user (`cost-detective-user`)
- [ ] Attach `ReadOnlyAccess` policy
- [ ] Create access key
- [ ] Copy Access Key ID
- [ ] Copy Secret Access Key
- [ ] Save these securely (you'll need them later)

### 3. OpenAI API Key
- [ ] Create account at https://platform.openai.com
- [ ] Go to API Keys section
- [ ] Create new API key
- [ ] Copy the key (you won't see it again)
- [ ] Set up billing (credit card required)

### 4. Local Software
- [ ] Install Python 3.9+ (`python --version`)
- [ ] Install pip (`pip --version`)
- [ ] Install Node.js 18+ (`node --version`)
- [ ] Install npm (`npm --version`)
- [ ] Install AWS CLI (`aws --version`)
- [ ] Install PostgreSQL client (optional, for database testing)

### 5. AWS RDS Database (Optional but Recommended)
- [ ] Create RDS PostgreSQL instance (db.t3.micro)
- [ ] Copy RDS endpoint (ends with `.rds.amazonaws.com`)
- [ ] Copy master username
- [ ] Copy master password

---

## Setup Steps

### Phase 1: AWS Configuration
- [ ] Run `aws configure`
- [ ] Enter Access Key ID
- [ ] Enter Secret Access Key
- [ ] Enter default region
- [ ] Verify: `aws sts get-caller-identity`

### Phase 2: Backend Setup
- [ ] Create `backend/` folder
- [ ] Create Python virtual environment: `python -m venv venv`
- [ ] Activate venv: `source venv/bin/activate` (macOS/Linux) or `venv\Scripts\activate` (Windows)
- [ ] Create `requirements.txt` with dependencies
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Create `.env` file with:
  - OPENAI_API_KEY (or ANTHROPIC_API_KEY / GOOGLE_API_KEY / GROQ_API_KEY)
  - DATABASE_URL
  - JWT_SECRET
- [ ] AWS credentials are **entered in the Settings panel** on the dashboard — do not put them in `.env`

### Phase 3: Frontend Setup
- [ ] Create React project: `npm create vite@latest frontend -- --template react-ts`
- [ ] Install Tailwind: `npm install -D tailwindcss postcss autoprefixer`
- [ ] Install dependencies: `npm install`

### Phase 4: Run Application
- [ ] Start backend: `python -m uvicorn main:app --reload` (from `backend/`)
- [ ] Start frontend: `npm run dev` (from `frontend/`)
- [ ] Open http://localhost:5173
- [ ] Test signup/login
- [ ] Run cost analysis

---

## File Structure After Setup

```
project/
├── Architecture.MD                    (Updated for AWS)
├── README.md                          (Updated for AWS)
├── RequestFlow.MD                     (Updated for AWS)
├── AWS_SETUP_GUIDE.md                (NEW - Detailed AWS setup)
├── AWS_QUICK_CHECKLIST.md            (This file)
│
├── prompts/
│   ├── 01-fastapi-aws-sdk.md
│   ├── 02-openai-analysis-aws.md
│   ├── 03-aws-rds-postgres-websocket.md
│   ├── 04-react-frontend-auth-aws.md
│   ├── 05-integrate-frontend-backend-aws.md
│   │
│   ├── 01-fastapi-aws-sdk-alt.md
│   ├── 02-openai-analysis.md
│   ├── 03-aws-rds-postgres-alt.md
│   ├── 04-react-frontend-auth.md
│   └── 05-integrate-frontend-backend.md
│
├── backend/
│   ├── main.py                       (TO CREATE - FastAPI main app)
│   ├── aws_scanner.py                (TO CREATE - AWS resource scanner)
│   ├── ai_analyzer.py                (TO CREATE - OpenAI analyzer)
│   ├── db.py                         (TO CREATE - Database setup)
│   ├── requirements.txt              (TO CREATE - Dependencies)
│   ├── .env                          (TO CREATE - Your secrets)
│   ├── .env.example                  (TO CREATE - Template)
│   └── venv/                         (Virtual environment)
│
└── frontend/
    ├── src/
    │   ├── pages/
    │   │   ├── Login.tsx             (TO CREATE)
    │   │   ├── Signup.tsx            (TO CREATE)
    │   │   ├── Dashboard.tsx         (TO CREATE)
    │   │   ├── Report.tsx            (TO CREATE)
    │   │   └── History.tsx           (TO CREATE)
    │   ├── components/
    │   │   ├── Navbar.tsx            (TO CREATE)
    │   │   ├── ProgressTracker.tsx   (TO CREATE)
    │   │   └── ServiceSelector.tsx   (TO CREATE)
    │   ├── App.tsx                   (TO CREATE)
    │   └── main.tsx                  (TO CREATE)
    ├── index.html                    (TO CREATE)
    ├── tailwind.config.js            (TO CREATE)
    ├── package.json                  (AUTO-GENERATED)
    └── node_modules/                 (AUTO-INSTALLED)
```

---

## Environment Variables Needed

```env
# AI Engine — choose one (leave blank to use built-in rule engine)
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxx
# ANTHROPIC_API_KEY=sk-ant-...
# GOOGLE_API_KEY=AIza...
# GROQ_API_KEY=gsk_...

# Database (Required)
DATABASE_URL=postgresql://costdetective:changeme123@localhost:5432/costdetective

# Security (Required)
JWT_SECRET=your_super_secret_long_random_string_here
```

> **Cloud credentials are entered via the dashboard UI** — not in `.env`:
> - AWS: Access Key ID + Secret Access Key → Settings panel
> - Azure: Subscription ID + Service Principal fields → Azure Credentials panel
> - GCP: Project ID + service account JSON → GCP Credentials panel

---

## Common Issues & Solutions

### AWS Credentials Not Working
```bash
# Verify
aws sts get-caller-identity

# Reconfigure
aws configure
```

### Python Not Found
```bash
# Check version
python3 --version

# Use python3 instead of python
python3 -m venv venv
```

### Port Already in Use
```bash
# Backend on different port
python -m uvicorn main:app --port 8001

# Frontend on different port
npm run dev -- --port 5174
```

### Database Connection Failed
- Check RDS security group allows inbound on port 5432
- Verify endpoint, username, password in `.env`
- Test: `psql -h endpoint -U postgres`

---

## Next: Start Building!

1. **Read**: `AWS_SETUP_GUIDE.md` (detailed walkthrough)
2. **Follow**: Prompts in `prompts/` folder (numbered 01-05)
3. **Build**: Backend, then Frontend
4. **Test**: Each component as you go
5. **Deploy**: (optional, covered later)

---

## Helpful Resources

- AWS Docs: https://docs.aws.amazon.com
- boto3 Docs: https://boto3.amazonaws.com/v1/documentation/api/latest/index.html
- FastAPI: https://fastapi.tiangolo.com
- React: https://react.dev
- OpenAI API: https://platform.openai.com/docs
- Tailwind CSS: https://tailwindcss.com

Good luck! 🚀
