# AI Cloud Cost Detective

An AI-powered multi-cloud cost analysis tool. Connect your AWS, Azure, or GCP account, run a scan, and get a plain-English report showing exactly which resources are costing you money unnecessarily — with the precise commands to fix each one.

---

## What It Does

- Scans **87 AWS services**, **20 Azure services**, and **18 GCP services** across all regions
- Detects idle, over-provisioned, and forgotten resources
- Estimates monthly savings for every finding
- Provides exact CLI commands to resolve each issue
- Streams live scan progress to the browser via WebSocket
- Stores scan history per user — auto-deleted after 2 days
- Users can delete individual history entries at any time

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| Backend | Python 3.11 + FastAPI |
| Auth | JWT (bcrypt + PyJWT) with JTI-based token revocation |
| Cloud SDKs | boto3 (AWS), azure-mgmt (Azure), google-api-python-client (GCP) |
| AI Analysis | Claude · GPT-4o · Gemini · Groq · DeepSeek · xAI · Mistral · Cohere · Together · Perplexity · Azure OpenAI · AWS Bedrock · Ollama · Built-in rule engine |
| Database | PostgreSQL 15 |
| Live Updates | FastAPI WebSocket |
| Deployment | Docker + Docker Compose |

---

## Prerequisites

| Tool | Version | Check |
|---|---|---|
| Docker | 24+ | `docker --version` |
| Docker Compose | 2.24+ | `docker compose version` |
| Git | any | `git --version` |

You do **not** need Python, Node.js, or any cloud CLI installed locally — everything runs inside containers.

---

## Quick Start

### 1. Clone the repository

```bash
git clone <repo-url>
cd AI-Cloud-Cost-Detective
```

### 2. Build and start

```bash
docker compose up --build -d
```

That's it. No `.env` editing, no secret generation — everything is handled automatically on first run.

### 3. Open the app

```
http://localhost:3000
```

Create an account on the signup page and start scanning.

> **Optional**: To add an AI provider, open `backend/.env`, uncomment one API key line, and restart the backend (`docker compose restart backend`). Without a key the built-in rule engine runs for free.

---

## Environment Variables

No `.env` files are required for a standard Docker Compose deployment — all defaults are built into the compose file.

### Root `.env` *(optional — production override only)*

A root `.env` is only needed if you want to override the default Postgres credentials. Without it, these defaults are used automatically:

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_USER` | `costdetective` | Database username |
| `POSTGRES_PASSWORD` | `costdetective` | Database password — override for production |
| `POSTGRES_DB` | `costdetective` | Database name |

### `backend/.env` *(optional — AI keys only)*

Copy `backend/.env.example` to `backend/.env` only if you want to add an AI provider key. Without this file the built-in rule engine runs automatically.

| Variable | Default | Description |
|---|---|---|
| `JWT_SECRET` | *(auto-generated)* | Generated on first run and persisted in the `backend_data` Docker volume. Do not set manually unless rotating the secret. |
| `DATABASE_URL` | *(set by docker-compose)* | Pre-configured to connect to the postgres container. Only override if using an external database. |

---

## Cloud Credentials

Credentials are entered in the dashboard UI — they are **never stored in the database**. They are held in memory only for the duration of each scan.

### AWS

**Option 1 — Access Keys (recommended for single accounts)**

Enter your Access Key ID and Secret Access Key in the AWS Credentials card on the dashboard.

**Option 2 — AWS SSO**

Log in via the SSO tab. An in-browser device-authorization flow authenticates you with your AWS identity provider. Temporary credentials are stored in sessionStorage for the current browser tab only.

**Option 3 — AWS Organizations (multi-account)**

Scan across multiple accounts from a management account. Enable the **Organizations** tab and enter your management account credentials plus the list of accounts to scan.

IAM permissions required: read-only (`ReadOnlyAccess` managed policy, or custom with `List*`, `Describe*`, `Get*` actions across the services you scan).

For Organizations mode, each member account needs a role (`CostDetectiveRole`) that the management account can assume. See `CLOUD_ORGANIZATIONS_SETUP.md`.

---

### Azure

Enter credentials in the Azure Credentials card on the dashboard:

| Field | Required | Description |
|---|---|---|
| **Subscription ID** | Yes | The Azure subscription to scan |
| **Tenant ID** | Optional | Azure AD tenant ID |
| **Client ID** | Optional | Application (client) ID of your Service Principal |
| **Client Secret** | Optional | Client secret of your Service Principal |

Leave Tenant/Client fields blank to use `DefaultAzureCredential` (Azure CLI, managed identity, or environment credentials).

Create a Service Principal with Reader role:
```bash
az ad sp create-for-rbac --name "CostDetective" --role Reader --scopes /subscriptions/<sub-id>
```

---

### GCP

Enter credentials in the GCP Credentials card on the dashboard:

| Field | Required | Description |
|---|---|---|
| **Project ID** | Yes | The GCP project to scan |
| **Service Account JSON or API Key** | Optional | Paste the full JSON key, or an API key starting with `AIza` |

Leave the key field blank to use Application Default Credentials (`gcloud auth` or `GOOGLE_APPLICATION_CREDENTIALS`).

The service account needs `roles/viewer` on the project.

---

## AI Engine

Set **one** API key in `backend/.env` to enable AI-powered analysis. If none is set, the built-in rule engine runs automatically at no cost.

| Provider | Environment Variable | Default Model |
|---|---|---|
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | claude-sonnet-4-6 |
| OpenAI | `OPENAI_API_KEY` | gpt-4o |
| Google Gemini | `GOOGLE_API_KEY` | gemini-2.0-flash |
| Groq (Llama) | `GROQ_API_KEY` | llama-3.3-70b-versatile |
| DeepSeek | `DEEPSEEK_API_KEY` | deepseek-chat |
| xAI (Grok) | `XAI_API_KEY` | grok-3 |
| Mistral | `MISTRAL_API_KEY` | mistral-large-latest |
| Cohere | `COHERE_API_KEY` | command-r-plus |
| Together AI | `TOGETHER_API_KEY` | Meta-Llama-3.1-70B |
| Perplexity | `PERPLEXITY_API_KEY` | sonar-pro |
| Azure OpenAI | `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT` | — |
| AWS Bedrock | *(uses boto3 credentials)* | amazon.nova-pro-v1:0 |
| Ollama (local) | *(no key — set `OLLAMA_BASE_URL`)* | llama3.2 |
| Built-in rule engine | *(no key required)* | — |

Override provider or model:
```env
AI_PROVIDER=anthropic   # force a specific provider
AI_MODEL=claude-opus-4-8  # override the default model
```

---

## Services Scanned

### AWS — 87 services

| Category | Services |
|---|---|
| Compute | EC2 / EBS / EIP / NAT, Load Balancers (ALB/NLB/CLB), Auto Scaling, ECS, EKS, ECR, App Runner, Elastic Beanstalk, Batch, Lightsail |
| Storage | S3, EFS, FSx, AWS Backup |
| Databases | RDS, ElastiCache, DynamoDB, DAX, Redshift, DocumentDB, Neptune, Timestream, QLDB, Keyspaces, MemoryDB, DMS |
| Serverless | Lambda |
| Networking | CloudFront, API Gateway, Transit Gateway, VPC Endpoints, Global Accelerator, Direct Connect, Network Firewall, Route 53, Transfer Family, WAF |
| Messaging | SQS, SNS, Kinesis, MSK, Amazon MQ, EventBridge, Step Functions, AppSync |
| Analytics | EMR, Glue, Athena, OpenSearch, QuickSight |
| AI / ML | SageMaker, Bedrock, Rekognition, Comprehend, Lex |
| Security | KMS, Secrets Manager, SSM, ACM Private CA, GuardDuty, Macie, Inspector, Security Hub, Firewall Manager, Shield, License Manager |
| Management | CloudWatch Synthetics, CloudTrail, AWS Config, X-Ray |
| Developer Tools | CodeBuild, CodePipeline, CodeArtifact |
| Business & Media | Connect, SES, WorkSpaces, Pinpoint, MediaConvert, MediaLive, IVS |

### Azure — 20 services

Virtual Machines, Managed Disks, Disk Snapshots, AKS Clusters, Storage Accounts, Azure SQL Databases, Cosmos DB, Azure Cache for Redis, Public IP Addresses, App Services, App Service Plans, Load Balancers, Application Gateways, NAT Gateways, Key Vaults, Container Registry, Service Bus, Event Hubs, Azure Database for PostgreSQL, Azure Database for MySQL

### GCP — 18 services

Compute Engine VMs, Persistent Disks, Static IPs, Disk Snapshots, GKE Clusters, Cloud Storage Buckets, Cloud SQL, Cloud Functions, Cloud Run, BigQuery Datasets, Cloud Spanner, Pub/Sub Topics, Dataproc Clusters, App Engine, Memorystore (Redis), Artifact Registry, Bigtable, Vertex AI Endpoints

---

## Project Structure

```
AI-Cloud-Cost-Detective/
├── backend/
│   ├── main.py                 # FastAPI app — all API endpoints
│   ├── cloud_scanner.py        # AWS scanner (87 services)
│   ├── azure_scanner.py        # Azure scanner (20 services)
│   ├── gcp_scanner.py          # GCP scanner (18 services)
│   ├── ai_analyzer.py          # AI cost analysis engine (14 providers)
│   ├── db.py                   # PostgreSQL database layer
│   ├── cloud_organizations.py  # AWS multi-account / SSO support
│   ├── ownership.py            # Ownership validation
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── .env                    # Optional — AI API keys only (gitignored; copy from .env.example)
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── pages/              # Dashboard, Analyze, History, Report, Login, Signup
│   │   ├── components/         # Navbar, ServiceSelector, ProgressTracker, SSOAuth
│   │   └── api.ts              # Backend API client
│   ├── nginx.conf              # Reverse proxy + security headers
│   ├── vite.config.ts          # Build config (source maps disabled)
│   └── Dockerfile
│
├── docker-compose.yml
└── .env                        # Root env (optional — Postgres credential overrides only; gitignored)
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/auth/signup` | Create account |
| `POST` | `/api/auth/login` | Login — returns JWT |
| `POST` | `/api/auth/logout` | Revoke current token |
| `POST` | `/api/auth/change-password` | Change password |
| `GET` | `/api/regions` | Region list for provider |
| `GET` | `/api/services` | Service list for provider |
| `POST` | `/api/validate` | Pre-scan credential check |
| `POST` | `/api/analyze` | Start scan + analysis |
| `WS` | `/ws/progress/{id}` | Live scan progress |
| `GET` | `/api/history` | Past analyses |
| `GET` | `/api/history/{id}` | Single analysis result |
| `DELETE` | `/api/history/{id}` | Delete own analysis |
| `POST` | `/api/sso/start` | Begin AWS SSO device flow |
| `GET` | `/api/sso/poll/{session}` | Poll SSO auth status |
| `GET` | `/api/sso/accounts/{session}` | List SSO accounts/roles |
| `POST` | `/api/sso/credentials` | Get temporary credentials |
| `GET` | `/api/config/accounts` | List org/SSO accounts |
| `POST` | `/api/config/accounts` | Add account |
| `DELETE` | `/api/config/accounts/{id}` | Remove account |
| `GET` | `/health` | Health check |

---

## How a Scan Works

```
Browser → FastAPI → Cloud Scanner(s) → AI Analyser → PostgreSQL
                         ↕
                  WebSocket (live progress streamed to browser)
```

1. You select a cloud provider, regions, and services in the dashboard
2. The backend validates credentials with a lightweight API call
3. Scanners query every selected service in every selected region in parallel
4. Resources are passed to the AI engine (or rule engine) for cost analysis
5. Live progress streams to the browser via WebSocket
6. The final report is saved to PostgreSQL and displayed

---

## Docker Services

| Container | Role | Port |
|---|---|---|
| `cost-detective-frontend` | React app served by nginx | `0.0.0.0:3000` |
| `cost-detective-backend` | FastAPI + scanners | `127.0.0.1:8000` (internal) |
| `cost-detective-db` | PostgreSQL 15 | `127.0.0.1:5432` (internal) |
| `cost-detective-tunnel` | Cloudflare tunnel — auto public URL | *(no port binding)* |

The backend and database are not exposed to the internet — only port 3000 is public. The Cloudflare tunnel prints a randomly generated `trycloudflare.com` URL in its logs that exposes the frontend publicly without opening any firewall ports.

### Named Volumes

| Volume | Purpose |
|---|---|
| `postgres_data` | PostgreSQL data — persists across container restarts |
| `backend_data` | Stores the auto-generated `JWT_SECRET` — deleting this volume logs all users out |

---

## Security

| Feature | Implementation |
|---|---|
| Authentication | JWT (HS256, 8-hour expiry) via `Depends(_verify_token)` on every protected endpoint |
| JWT secret | Auto-generated at first startup using `secrets.token_hex(32)`; persisted in the `backend_data` Docker volume — never stored in source code |
| Token revocation | JTI stored in `revoked_tokens` table; logout immediately invalidates the token |
| Password storage | bcrypt (constant-time comparison prevents user enumeration) |
| Rate limiting | Login: 20/min per IP, 10/min per email. Signup: 10/5 min per IP. Password change: 5/5 min per user |
| Concurrent scans | Max 5 platform-wide, max 3 per user |
| Credential handling | Cloud credentials never stored — in memory for scan duration only |
| Input validation | Pydantic with field validators; emails, account IDs, subscription UUIDs, GCP project IDs all validated |
| Auto data purge | Analyses older than 2 days deleted automatically every 12 hours |
| Security headers | X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy, Permissions-Policy, CSP |
| Source maps | Disabled in production build; `.map` and `.ts` file routes blocked by nginx |
| Container isolation | Backend runs as non-root `appuser`; database and backend ports not exposed publicly |
| Error sanitization | Internal file paths stripped from error messages before reaching the client |

---

## Common Commands

```bash
# Build all containers
docker compose build

# Start everything
docker compose up -d

# Stop everything
docker compose down

# View logs
docker compose logs -f

# Rebuild a single service after code changes
docker compose build backend && docker compose up -d backend

# Full rebuild (no cache)
docker compose build --no-cache && docker compose up -d

# Reset a user's password (inside backend container)
docker compose exec backend python3 create_user.py <email> <password>
```

---

## Troubleshooting

**Containers won't start**
```bash
docker compose logs backend
docker compose logs postgres
```

**Want to rotate the JWT secret (logs all users out)**
```bash
docker compose down
docker volume rm ai-cloud-cost-detective-main_backend_data
docker compose up -d
```
A fresh secret is generated on the next start.

**AWS scan returns no results**
- Confirm credentials work: `aws sts get-caller-identity`
- Check that selected regions contain your resources
- Verify the IAM user/role has `ReadOnlyAccess`

**Azure scan fails with auth error**
- Ensure Tenant ID, Client ID, and Client Secret are filled in on the dashboard
- Verify the Service Principal has Reader role on the subscription

**GCP scan fails**
- Ensure Project ID and service account JSON (or API key) are entered on the dashboard
- The service account needs `roles/viewer` on the project

**Login returns 500 after password reset**
- Do not update `password_hash` via shell variable interpolation — the `$2b$...` hash gets mangled
- Always reset passwords using Python inside the container:
  ```bash
  docker compose exec backend python3 create_user.py <email> <new-password>
  ```
