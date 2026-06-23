# 🐧 Linux Server Setup Guide - AI Cloud Cost Detective

Complete guide to run your application on a Linux server (Ubuntu/Debian recommended).

---

## Prerequisites

### Supported Linux Distributions
- ✅ **Ubuntu 20.04 LTS** (recommended)
- ✅ **Ubuntu 22.04 LTS** (latest)
- ✅ **Debian 11+**
- ✅ **CentOS 8+**
- ✅ **Rocky Linux 8+**

### Server Requirements
- **CPU**: 1+ cores
- **RAM**: 2+ GB
- **Storage**: 10+ GB
- **Internet**: Yes (for downloads)

### Free/Cheap Hosting Options
- **AWS EC2**: t3.micro (free tier: 12 months)
- **DigitalOcean**: $5/month droplet
- **Linode**: $5/month
- **Heroku**: Free (limited)
- **Railway**: $5/month
- **Render**: Free tier available

---

## Part 1: Basic Linux Setup

### Step 1: Connect to Your Server

**If using AWS EC2:**
```bash
ssh -i your-key.pem ubuntu@your-instance-ip
```

**If using DigitalOcean/Linode:**
```bash
ssh root@your-server-ip
```

### Step 2: Update System

```bash
sudo apt update
sudo apt upgrade -y
```

### Step 3: Install Essential Tools

```bash
sudo apt install -y \
  curl \
  wget \
  git \
  build-essential \
  libssl-dev \
  libffi-dev \
  python3-dev \
  python3-pip \
  python3-venv
```

---

## Part 2: Install Docker & Docker Compose

### For Ubuntu/Debian:

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify installation
docker --version
docker-compose --version
```

### For CentOS/Rocky Linux:

```bash
sudo dnf install -y docker docker-compose
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
```

---

## Part 3: Clone Project

```bash
# Clone your repository
git clone https://github.com/yourusername/AI-Cloud-Cost-Detective.git
cd AI-Cloud-Cost-Detective

# Or if local, use SCP
scp -r /path/to/AI-Cloud-Cost-Detective user@server:/home/user/
```

---

## Part 4: Option A - Run with LocalStack (Recommended for Dev)

### Step 1: Create docker-compose.yml

In your project root, ensure you have:

```yaml
version: '3.9'

services:
  localstack:
    image: localstack/localstack:latest
    container_name: localstack
    ports:
      - "4566:4566"
    environment:
      - SERVICES=ec2,rds,s3,lambda,cloudwatch,logs
      - DEBUG=1
      - AWS_ACCESS_KEY_ID=test
      - AWS_SECRET_ACCESS_KEY=test
      - AWS_DEFAULT_REGION=us-east-1
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock"
      - "localstack-data:/tmp/localstack"
    restart: always

  postgres:
    image: postgres:14
    container_name: postgres-local
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres123
      POSTGRES_DB: costdetective
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    restart: always

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: backend
    ports:
      - "8000:8000"
    environment:
      - USE_LOCALSTACK=true
      - LOCALSTACK_ENDPOINT=http://localstack:4566
      - DATABASE_URL=postgresql://postgres:postgres123@postgres:5432/costdetective
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - JWT_SECRET=${JWT_SECRET}
    depends_on:
      - localstack
      - postgres
    volumes:
      - ./backend:/app
    restart: always

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: frontend
    ports:
      - "3000:3000"
    environment:
      - VITE_API_URL=http://localhost:8000
    depends_on:
      - backend
    restart: always

volumes:
  postgres-data:
  localstack-data:
```

### Step 2: Create Backend Dockerfile

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Run migrations if needed
RUN mkdir -p /app/logs

# Start FastAPI
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Step 3: Create Frontend Dockerfile

Create `frontend/Dockerfile`:

```dockerfile
FROM node:18-alpine as builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# Production image
FROM node:18-alpine

WORKDIR /app
RUN npm install -g serve

COPY --from=builder /app/dist ./dist

EXPOSE 3000

CMD ["serve", "-s", "dist", "-l", "3000"]
```

### Step 4: Create .env File

```bash
cat > .env << EOF
USE_LOCALSTACK=true
LOCALSTACK_ENDPOINT=http://localstack:4566
DATABASE_URL=postgresql://postgres:postgres123@postgres:5432/costdetective
OPENAI_API_KEY=your_openai_key_here
JWT_SECRET=your_jwt_secret_here
EOF
```

### Step 5: Start All Services

```bash
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f backend
```

---

## Part 5: Option B - Run with Real AWS

### Step 1: Install AWS CLI

```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
aws --version
```

### Step 2: Configure AWS Credentials

```bash
aws configure
# Enter:
# AWS Access Key ID: your_access_key
# AWS Secret Access Key: your_secret_key
# Default region: us-east-1
# Default output format: json
```

### Step 3: Setup Backend Manually

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Create .env
cat > backend/.env << EOF
DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/costdetective
OPENAI_API_KEY=your_openai_key
JWT_SECRET=your_jwt_secret
EOF
# NOTE: Cloud credentials (AWS, Azure, GCP) are entered via the dashboard UI — do not add them here.

# Create database tables
python backend/db.py  # Or use Alembic migrations

# Run backend
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### Step 4: Setup Frontend

```bash
# Install Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install dependencies
cd frontend
npm install

# Build for production
npm run build

# Serve with nginx (see below)
```

---

## Part 6: Production Setup with Systemd

### For Backend (FastAPI)

Create `/etc/systemd/system/ai-cost-backend.service`:

```ini
[Unit]
Description=AI Cloud Cost Detective Backend
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/AI-Cloud-Cost-Detective/backend
Environment="PATH=/home/ubuntu/AI-Cloud-Cost-Detective/backend/venv/bin"
ExecStart=/home/ubuntu/AI-Cloud-Cost-Detective/backend/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ai-cost-backend.service
sudo systemctl start ai-cost-backend.service
sudo systemctl status ai-cost-backend.service
```

### For Frontend with Nginx

Install Nginx:

```bash
sudo apt install -y nginx
```

Create `/etc/nginx/sites-available/ai-cost-frontend`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    root /home/ubuntu/AI-Cloud-Cost-Detective/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    location /ws {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

Enable and start:

```bash
sudo ln -s /etc/nginx/sites-available/ai-cost-frontend /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl start nginx
sudo systemctl enable nginx
```

---

## Part 7: SSL Certificate (HTTPS)

Using Let's Encrypt:

```bash
sudo apt install -y certbot python3-certbot-nginx

sudo certbot certonly --nginx -d your-domain.com

# Auto-renew
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

---

## Part 8: Firewall Setup

```bash
sudo ufw enable
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw allow 8000/tcp    # Backend (if needed)
sudo ufw allow 5432/tcp    # PostgreSQL (if remote)
```

---

## Part 9: Monitoring & Logs

### View Logs

```bash
# For Docker
docker-compose logs -f backend

# For Systemd service
sudo journalctl -u ai-cost-backend.service -f

# Check Nginx
sudo tail -f /var/log/nginx/error.log
```

### Monitor Resources

```bash
# Install htop
sudo apt install -y htop
htop

# Check disk space
df -h

# Check memory
free -h
```

---

## Part 10: Backup Strategy

### Backup PostgreSQL

```bash
# Create backup
pg_dump -U postgres costdetective > backup-$(date +%Y%m%d).sql

# Restore from backup
psql -U postgres costdetective < backup-20240101.sql
```

### Automated Backup

Create `backup.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/home/ubuntu/backups"
mkdir -p $BACKUP_DIR

# Database backup
pg_dump -U postgres costdetective | gzip > $BACKUP_DIR/db-$(date +%Y%m%d-%H%M%S).sql.gz

# Keep only last 7 days
find $BACKUP_DIR -name "db-*.sql.gz" -mtime +7 -delete
```

Add to crontab:
```bash
crontab -e

# Add line:
# 0 2 * * * /home/ubuntu/backup.sh
```

---

## Part 11: Deployment Options

### Option 1: Your Own Linux Server (VPS)

Providers:
- **AWS EC2** - $0-5/month (free tier)
- **DigitalOcean** - $5/month
- **Linode** - $5/month
- **Vultr** - $2.50/month
- **Hetzner** - $2.99/month

### Option 2: Container Platform

- **Docker Swarm** - On your VPS
- **Kubernetes** - Complex but powerful
- **AWS ECS** - Pay per container
- **DigitalOcean App Platform** - $5/month

### Option 3: PaaS (Easiest)

- **Railway** - $5/month
- **Render** - Free tier available
- **Heroku** - $7+/month
- **Fly.io** - $5/month

---

## Quick Start Commands

### Start Everything (LocalStack)

```bash
# 1. Connect to server
ssh ubuntu@your-ip

# 2. Clone/navigate to project
cd AI-Cloud-Cost-Detective

# 3. Create .env
cat > .env << EOF
OPENAI_API_KEY=your_key
JWT_SECRET=your_secret
EOF

# 4. Start services
docker-compose up -d

# 5. Check status
docker-compose ps

# 6. View logs
docker-compose logs -f
```

### Access Your App

- **Frontend**: http://your-server-ip:3000
- **Backend API**: http://your-server-ip:8000
- **API Docs**: http://your-server-ip:8000/docs
- **LocalStack**: http://your-server-ip:4566

---

## Troubleshooting

### Container won't start
```bash
docker-compose logs backend
docker-compose ps
```

### Permission denied
```bash
sudo usermod -aG docker $USER
newgrp docker
```

### Port already in use
```bash
sudo lsof -i :8000  # Check what's using port
sudo kill -9 <PID>  # Kill the process
```

### Database connection failed
```bash
# Test PostgreSQL
psql -h localhost -U postgres -d costdetective

# Check database container
docker-compose logs postgres
```

### Frontend not loading
```bash
# Check Nginx
sudo systemctl status nginx
sudo nginx -t
sudo tail -f /var/log/nginx/error.log
```

---

## Production Checklist

- [ ] Create Linux server (Ubuntu 22.04 recommended)
- [ ] Update system: `sudo apt update && sudo apt upgrade`
- [ ] Install Docker & Docker Compose
- [ ] Clone project
- [ ] Create `.env` with secrets
- [ ] Create Dockerfiles
- [ ] Create docker-compose.yml
- [ ] Start services: `docker-compose up -d`
- [ ] Verify all services running: `docker-compose ps`
- [ ] Setup Nginx reverse proxy
- [ ] Setup SSL with Let's Encrypt
- [ ] Setup firewall
- [ ] Setup monitoring & logs
- [ ] Setup backup strategy
- [ ] Test full application flow

---

## Cost Summary

### Monthly Costs (Minimal Setup)

| Component | Cost |
|-----------|------|
| Linux server (1GB RAM) | $3-5 |
| PostgreSQL (included) | $0 |
| Docker & containers | $0 |
| Bandwidth | $0-5 |
| **Total** | **$5-10/month** |

### With AWS Services

| Component | Cost |
|-----------|------|
| EC2 t3.micro | $0-5 |
| RDS PostgreSQL | $15 |
| NAT Gateway | $32 |
| **Total** | **$50+/month** |

**Recommendation**: Use Linux VPS for lowest cost, switch to AWS later if needed.

---

## Next Steps

1. **Choose hosting** (DigitalOcean, AWS, etc.)
2. **Create Linux server** (Ubuntu 22.04)
3. **Follow Part 1-4** above for LocalStack setup
4. **Or follow Part 5-6** for real AWS setup
5. **Test your app** at `http://your-ip:3000`

---

## Support Resources

- **Ubuntu Docs**: https://ubuntu.com/server/docs
- **Docker Docs**: https://docs.docker.com
- **Nginx Docs**: https://nginx.org/en/docs
- **PostgreSQL Docs**: https://www.postgresql.org/docs

Good luck! 🚀
