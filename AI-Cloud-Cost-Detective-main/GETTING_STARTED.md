# Getting Started — AI Cloud Cost Detective

Everything runs in Docker. You do not need Python, Node.js, or any cloud CLI installed locally.

---

## Prerequisites

| Tool | Version | Check |
|---|---|---|
| Docker | 24+ | `docker --version` |
| Docker Compose | 2.20+ | `docker compose version` |
| Git | any | `git --version` |

---

## Start in 2 Steps

### 1. Clone

```bash
git clone <repo-url>
cd AI-Cloud-Cost-Detective
```

### 2. Build and run

```bash
docker compose up --build -d
```

Open `http://localhost:3000`, create an account, and start scanning.

No secrets to generate, no `.env` files to edit. The `JWT_SECRET` is created automatically on first run and saved in a Docker volume so it persists across restarts.

---

## Adding an AI Provider (Optional)

Without an API key the built-in rule engine runs for free. To enable AI analysis, open `backend/.env`, uncomment one of the key lines, paste your key, then restart:

```bash
docker compose restart backend
```

Supported providers and the env var to set:

| Provider | Variable |
|---|---|
| Anthropic (Claude) | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Google Gemini | `GOOGLE_API_KEY` |
| Groq (Llama — free tier) | `GROQ_API_KEY` |
| DeepSeek | `DEEPSEEK_API_KEY` |
| Mistral | `MISTRAL_API_KEY` |
| AWS Bedrock | *(uses boto3 — no extra key)* |
| Ollama (local) | `OLLAMA_BASE_URL` |

See the full list in [README.md](README.md#ai-engine).

---

## Connecting Your Cloud Account

Credentials are entered in the dashboard UI — they are never stored in the database. They stay in memory only for the duration of each scan.

### AWS

- **Access keys** — paste Key ID + Secret in the AWS Credentials card
- **SSO** — use the SSO tab for browser-based login
- **Multi-account** — enable the Organizations tab and enter management account credentials

Minimum IAM permission: `ReadOnlyAccess` (or equivalent `List*` / `Describe*` / `Get*` actions).

### Azure

Enter Subscription ID in the Azure Credentials card. Optionally add Tenant ID, Client ID, and Client Secret for a Service Principal. Leave blank to use `DefaultAzureCredential` (Azure CLI or managed identity).

```bash
az ad sp create-for-rbac --name "CostDetective" --role Reader --scopes /subscriptions/<sub-id>
```

### GCP

Enter Project ID in the GCP Credentials card. Optionally paste a Service Account JSON key or an API key. Leave blank to use Application Default Credentials.

The service account needs `roles/viewer` on the project.

---

## Common Commands

```bash
# Start everything
docker compose up -d

# View logs
docker compose logs -f

# Rebuild after code changes
docker compose build backend && docker compose up -d backend

# Full rebuild (no cache)
docker compose build --no-cache && docker compose up -d

# Stop everything
docker compose down

# Reset a user's password
docker compose exec backend python3 create_user.py <email> <new-password>
```

---

## Troubleshooting

**Port 3000 already in use**
Change the frontend port in `docker-compose.yml` — replace `"0.0.0.0:3000:80"` with `"0.0.0.0:<your-port>:80"`.

**Scan returns no results**
- AWS: verify credentials with `aws sts get-caller-identity` and confirm `ReadOnlyAccess` is attached
- Azure: check the Service Principal has Reader role on the subscription
- GCP: check the service account has `roles/viewer`

**Want to rotate the JWT secret (logs all users out)**
```bash
docker compose down
docker volume rm ai-cloud-cost-detective-main_backend_data
docker compose up -d
```

For more detail see [README.md](README.md).
