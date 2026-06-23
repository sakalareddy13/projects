# 🐳 Local AWS Development with LocalStack

No AWS account needed! Run everything locally for free using **LocalStack**.

---

## What is LocalStack?

**LocalStack** is a fully functional local AWS cloud stack that runs on your computer. It emulates:
- EC2 (Virtual Machines)
- RDS (Databases)
- S3 (Storage)
- Lambda (Serverless)
- And 200+ other AWS services

**Benefits:**
- ✅ No AWS account needed
- ✅ Free (open source)
- ✅ Identical to AWS API
- ✅ Fast local development
- ✅ No internet needed
- ✅ No costs (completely local)

---

## Prerequisites

You need **Docker** and **Docker Compose** installed:

### Install Docker

**Windows/Mac:**
- Download: https://www.docker.com/products/docker-desktop
- Install and run Docker Desktop
- Verify: `docker --version`

**Linux:**
```bash
sudo apt-get install docker.io docker-compose
```

Verify installation:
```bash
docker --version
docker-compose --version
```

---

## Setup LocalStack (5 minutes)

### Step 1: Create Project Structure

```bash
mkdir aws-local-dev
cd aws-local-dev
```

### Step 2: Create docker-compose.yml

Create file: `docker-compose.yml`

```yaml
version: '3.9'

services:
  localstack:
    image: localstack/localstack:latest
    container_name: localstack
    ports:
      - "4566:4566"      # LocalStack gateway
      - "4571:4571"      # ES
      - "8055:8055"      # LocalStack UI (optional)
    environment:
      - SERVICES=ec2,rds,s3,lambda,cloudwatch,logs
      - DEBUG=1
      - DATA_DIR=/tmp/localstack/data
      - DOCKER_HOST=unix:///var/run/docker.sock
      - AWS_ACCESS_KEY_ID=test
      - AWS_SECRET_ACCESS_KEY=test
      - AWS_DEFAULT_REGION=us-east-1
    volumes:
      - "${TMPDIR:-.}/.localstack:/tmp/localstack"
      - "/var/run/docker.sock:/var/run/docker.sock"
    networks:
      - localstack-network

  postgres-local:
    image: postgres:14
    container_name: postgres-local
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: costdetective
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks:
      - localstack-network

volumes:
  postgres-data:

networks:
  localstack-network:
    driver: bridge
```

### Step 3: Start LocalStack

```bash
docker-compose up -d
```

This starts:
- **LocalStack** on port 4566
- **PostgreSQL** on port 5432
- **LocalStack UI** on port 8055 (optional)

Verify:
```bash
docker-compose ps
```

Should show both services running.

### Step 4: Configure AWS CLI for LocalStack

Create file: `~/.aws/config` (if doesn't exist)

```
[profile localstack]
region = us-east-1
output = json
```

Create file: `~/.aws/credentials` (if doesn't exist)

```
[localstack]
aws_access_key_id = test
aws_secret_access_key = test
```

### Step 5: Test LocalStack

```bash
# List S3 buckets (empty)
aws --endpoint-url=http://localhost:4566 --profile localstack s3 ls

# List EC2 instances (empty)
aws --endpoint-url=http://localhost:4566 --profile localstack ec2 describe-instances
```

Both should work without errors!

---

## Use LocalStack with boto3

In your Python code, just point to LocalStack:

```python
import boto3

# Connect to LocalStack instead of real AWS
ec2 = boto3.client(
    'ec2',
    endpoint_url='http://localhost:4566',  # LocalStack endpoint
    region_name='us-east-1',
    aws_access_key_id='test',
    aws_secret_access_key='test'
)

# Now everything works locally!
response = ec2.describe_instances()
print(response)
```

### Create EC2 Instance Locally

```python
# Create a test instance
response = ec2.run_instances(
    ImageId='ami-12345678',
    MinCount=1,
    MaxCount=1,
    InstanceType='t2.micro'
)

# List instances
instances = ec2.describe_instances()
print(instances)
```

### Create S3 Bucket Locally

```python
s3 = boto3.client(
    's3',
    endpoint_url='http://localhost:4566',
    aws_access_key_id='test',
    aws_secret_access_key='test'
)

# Create bucket
s3.create_bucket(Bucket='my-test-bucket')

# List buckets
buckets = s3.list_buckets()
print(buckets)
```

---

## Updated Backend Setup for LocalStack

### Step 1: Update requirements.txt

```
fastapi==0.115.5
uvicorn==0.32.1
boto3==1.35.76
python-dotenv==1.0.1
openai==1.57.0
psycopg2-binary==2.9.10
asyncpg==0.30.0
PyJWT==2.10.1
bcrypt==4.2.1
python-multipart==0.0.17
```

No changes needed - boto3 works with LocalStack!

### Step 2: Create `.env` for LocalStack

```env
# LocalStack Configuration
USE_LOCALSTACK=true
LOCALSTACK_ENDPOINT=http://localhost:4566
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test

# Local Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/costdetective

# OpenAI (still needed for AI analysis)
OPENAI_API_KEY=sk-proj-your_key_here

# JWT Secret
JWT_SECRET=your_jwt_secret_key_here

# Server
BACKEND_URL=http://localhost:8000
FRONTEND_URL=http://localhost:5173
```

### Step 3: Update aws_scanner.py

```python
import boto3
import os

LOCALSTACK_ENDPOINT = os.getenv('LOCALSTACK_ENDPOINT', 'http://localhost:4566')
USE_LOCALSTACK = os.getenv('USE_LOCALSTACK', 'false').lower() == 'true'

def get_ec2_client():
    if USE_LOCALSTACK:
        return boto3.client(
            'ec2',
            endpoint_url=LOCALSTACK_ENDPOINT,
            region_name='us-east-1',
            aws_access_key_id='test',
            aws_secret_access_key='test'
        )
    else:
        # Use real AWS credentials from environment
        return boto3.client('ec2', region_name=os.getenv('AWS_REGION'))

def get_rds_client():
    if USE_LOCALSTACK:
        return boto3.client(
            'rds',
            endpoint_url=LOCALSTACK_ENDPOINT,
            region_name='us-east-1',
            aws_access_key_id='test',
            aws_secret_access_key='test'
        )
    else:
        return boto3.client('rds', region_name=os.getenv('AWS_REGION'))

def get_s3_client():
    if USE_LOCALSTACK:
        return boto3.client(
            's3',
            endpoint_url=LOCALSTACK_ENDPOINT,
            region_name='us-east-1',
            aws_access_key_id='test',
            aws_secret_access_key='test'
        )
    else:
        return boto3.client('s3', region_name=os.getenv('AWS_REGION'))

async def scan_resources(regions: list, services: list):
    """Scan AWS or LocalStack resources"""
    results = {}
    
    for service in services:
        if service == 'ec2':
            client = get_ec2_client()
            try:
                response = client.describe_instances()
                results['ec2'] = response.get('Reservations', [])
            except Exception as e:
                results['ec2'] = {'error': str(e)}
        
        elif service == 's3':
            client = get_s3_client()
            try:
                response = client.list_buckets()
                results['s3'] = response.get('Buckets', [])
            except Exception as e:
                results['s3'] = {'error': str(e)}
        
        elif service == 'rds':
            client = get_rds_client()
            try:
                response = client.describe_db_instances()
                results['rds'] = response.get('DBInstances', [])
            except Exception as e:
                results['rds'] = {'error': str(e)}
    
    return results
```

---

## Create Sample Test Data in LocalStack

### Script: setup_localstack.sh

```bash
#!/bin/bash

# Set endpoint
ENDPOINT="http://localhost:4566"
PROFILE="--endpoint-url=$ENDPOINT"

echo "Creating test resources in LocalStack..."

# Create S3 bucket
aws $PROFILE s3 mb s3://test-bucket
echo "✓ Created S3 bucket: test-bucket"

# Create RDS database (simulated)
aws $PROFILE rds create-db-instance \
  --db-instance-identifier test-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --master-username postgres \
  --master-user-password password
echo "✓ Created RDS instance: test-db"

# List created resources
echo ""
echo "Test resources created:"
aws $PROFILE s3 ls
aws $PROFILE rds describe-db-instances
```

Run:
```bash
bash setup_localstack.sh
```

---

## Run Your Backend Against LocalStack

### Step 1: Start LocalStack

```bash
docker-compose up -d
```

### Step 2: Setup Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Step 3: Create .env

Use the LocalStack `.env` from above

### Step 4: Run Backend

```bash
python -m uvicorn main:app --reload
```

Your backend now connects to LocalStack instead of AWS!

### Step 5: Test It

```bash
# Scan LocalStack resources
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"regions": ["us-east-1"], "services": ["ec2", "s3"]}'
```

---

## LocalStack vs Real AWS

| Feature | LocalStack | Real AWS |
|---------|-----------|----------|
| **Cost** | Free | Pay as you go |
| **Internet** | Not needed | Required |
| **Speed** | Very fast | Network latency |
| **Account** | Not needed | Required |
| **Data persistence** | Limited | Full |
| **Perfect for** | Development/Testing | Production |

---

## Switch Between LocalStack and Real AWS

Just change `.env`:

**For LocalStack:**
```env
USE_LOCALSTACK=true
LOCALSTACK_ENDPOINT=http://localhost:4566
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
```

**For Real AWS:**
```env
USE_LOCALSTACK=false
AWS_ACCESS_KEY_ID=your_real_key
AWS_SECRET_ACCESS_KEY=your_real_secret
```

Your code handles both automatically!

---

## LocalStack Dashboard (Optional)

Access the LocalStack UI at:
```
http://localhost:8055
```

This shows:
- Resources created
- API calls made
- Logs and debugging info

---

## Troubleshooting LocalStack

### Container won't start
```bash
# Check logs
docker-compose logs localstack

# Restart
docker-compose down
docker-compose up -d
```

### Connection refused
```bash
# Verify LocalStack is running
docker ps | grep localstack

# Test connection
curl http://localhost:4566
```

### Port already in use
```bash
# Change port in docker-compose.yml
ports:
  - "4567:4566"  # Use 4567 instead of 4566
```

### AWS CLI not finding endpoint
```bash
# Use --endpoint-url explicitly
aws --endpoint-url=http://localhost:4566 s3 ls
```

---

## Next Steps

1. **Install Docker**: Docker Desktop (https://www.docker.com/products/docker-desktop)
2. **Create docker-compose.yml** from above
3. **Run**: `docker-compose up -d`
4. **Test**: `aws --endpoint-url=http://localhost:4566 s3 ls`
5. **Build backend** with LocalStack endpoint

---

## Comparison: LocalStack vs Other Options

### Option 1: LocalStack (Recommended)
- ✅ Complete AWS emulation
- ✅ Docker-based
- ✅ All AWS services
- ✅ Easy setup
- ⭕ Slight overhead

### Option 2: moto (Python library)
- ✅ Pure Python
- ✅ No Docker needed
- ⭕ Limited services
- ⭕ Mocking, not emulation
- ✅ Fast

### Option 3: Real AWS
- ✅ Production identical
- ⭕ Costs money
- ⭕ Needs internet
- ⭕ Slower feedback

**Best choice for development: LocalStack** 🐳

---

**Summary**: You can now develop completely locally without any AWS account or installation! Just Docker and you're good to go.

Ready to get started? Follow the steps above! 🚀
