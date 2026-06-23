# AWS Cloud Cost Detective - Setup Guide

This guide walks you through everything you need to set up and run the AI Cloud Cost Detective with AWS.

## Prerequisites

### 1. AWS Account

- Create a free AWS account at https://aws.amazon.com
- Free tier includes:
  - 750 hours/month of EC2 (t2/t3 micro)
  - 20 GB S3 storage
  - 750 hours/month RDS (db.t3.micro)
  - 1 million Lambda invocations
  - Full API access for all services

### 2. AWS CLI

Install AWS CLI v2:
- **macOS**: `brew install awscli`
- **Windows**: Download from https://awscli.amazonaws.com/AWSCLIV2.msi
- **Linux**: `curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && unzip awscliv2.zip && sudo ./aws/install`

Verify installation:
```bash
aws --version
```

### 3. AWS Credentials

#### Option A: Using AWS Management Console (Recommended for beginners)

1. Go to AWS Management Console → IAM Dashboard
2. Click "Users" → "Create user"
3. Enter username (e.g., `cost-detective-user`)
4. Click "Attach policies directly"
5. Search and attach these policies:
   - `ReadOnlyAccess` (for read-only access to all resources)
   - `AmazonEC2ReadOnlyAccess`
   - `AmazonRDSReadOnlyAccess`
   - `AmazonS3ReadOnlyAccess`
   - `AWSLambdaReadOnlyAccess`
   - `CloudWatchReadOnlyAccess` (for cost data)
6. Click "Create user"
7. Click on the user → "Security credentials" → "Create access key"
8. Choose "Application running on AWS resources" or "Other"
9. Copy the Access Key ID and Secret Access Key

#### Option B: Using AWS CLI (Faster)

```bash
# Create IAM user
aws iam create-user --user-name cost-detective-user

# Create access key
aws iam create-access-key --user-name cost-detective-user

# Attach read-only policy
aws iam attach-user-policy --user-name cost-detective-user \
  --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess
```

### 4. Configure AWS CLI

```bash
aws configure
```

When prompted, enter:
- **AWS Access Key ID**: (from step 3)
- **AWS Secret Access Key**: (from step 3)
- **Default region**: `us-east-1` (or your preferred region)
- **Default output format**: `json`

Verify configuration:
```bash
aws sts get-caller-identity
```

## Backend Setup

### Step 1: Create Backend Folder Structure

```bash
mkdir backend
cd backend
```

### Step 2: Create Virtual Environment

```bash
# macOS/Linux
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### Step 3: Install Dependencies

Create `requirements.txt`:
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

Install:
```bash
pip install -r requirements.txt
```

### Step 4: Create .env File

Create `backend/.env`:
```env
# AI Engine (choose one — leave blank to use built-in rule engine)
OPENAI_API_KEY=your_openai_api_key_here
# ANTHROPIC_API_KEY=sk-ant-...
# GOOGLE_API_KEY=AIza...
# GROQ_API_KEY=gsk_...

# Database Configuration
DATABASE_URL=postgresql://costdetective:changeme123@localhost:5432/costdetective

# JWT Secret (required — min 32 characters)
JWT_SECRET=your_random_secret_key_here_make_it_long
```

> **AWS, Azure, and GCP credentials are entered through the dashboard UI** when running a scan — do not put cloud credentials in `.env`.

### Step 5: Create AWS RDS PostgreSQL Database (Optional but Recommended)

If you want to store analysis history:

**Via AWS Console:**
1. Go to RDS Dashboard
2. Click "Create database"
3. Engine: PostgreSQL
4. DB instance class: `db.t3.micro` (free tier eligible)
5. Allocated storage: 20 GB
6. DB name: `costdetective`
7. Master username: `postgres`
8. Master password: (create a strong password)
9. VPC security group: Allow inbound on port 5432
10. Create database
11. Get the endpoint from the database details page

**Via AWS CLI:**
```bash
aws rds create-db-instance \
  --db-instance-identifier cost-detective-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --master-username postgres \
  --master-user-password YourStrongPassword123 \
  --allocated-storage 20 \
  --db-name costdetective \
  --publicly-accessible \
  --enable-iam-database-authentication
```

Get endpoint:
```bash
aws rds describe-db-instances --db-instance-identifier cost-detective-db \
  --query 'DBInstances[0].Endpoint.Address' --output text
```

Update `.env` with the endpoint.

### Step 6: Run Backend

```bash
# From backend/ folder
python -m uvicorn main:app --reload --port 8000
```

Backend runs at: `http://localhost:8000`

API docs at: `http://localhost:8000/docs`

## Frontend Setup

### Step 1: Create Frontend

```bash
cd ..
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```

### Step 2: Install Tailwind CSS

```bash
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

### Step 3: Install Dependencies

```bash
npm install axios zustand
```

### Step 4: Run Frontend

```bash
npm run dev
```

Frontend runs at: `http://localhost:5173`

## Testing the Application

### 1. Test AWS Credentials

```bash
# In backend/
python3 -c "import boto3; ec2 = boto3.client('ec2'); print(ec2.describe_instances())"
```

### 2. Test Backend Health

```bash
curl http://localhost:8000/docs
```

### 3. Test AWS Scanner

```bash
# In backend/main.py, create a test endpoint
@app.get("/test/regions")
async def test_regions():
    from aws_scanner import get_regions
    return await get_regions()
```

Call: `curl http://localhost:8000/test/regions`

## What AWS Resources Can Be Detected

The tool scans for cost issues in:

### EC2 (Virtual Machines)
- Over-provisioned instance types
- Unused instances (stopped for >30 days)
- Old generation instances (need upgrading)
- Unattached EBS volumes
- Unused Elastic IPs

### RDS (Databases)
- Wrong instance sizes
- Unused databases
- Missing read replicas
- Inefficient backup retention

### S3 (Storage)
- Unused buckets
- Missing lifecycle policies
- High storage classes (not transitioning to cheaper tiers)
- Versioning on non-critical buckets

### Lambda (Serverless)
- Over-provisioned memory
- Unused functions
- High invocation costs

### Network
- Unused NAT Gateways
- Unused load balancers
- High data transfer costs
- Unused VPN connections

### Other Services
- Unused CloudWatch log groups
- Unattached ENIs
- Unused security groups
- Unattached snapshots

## Estimated Cost of Running This Tool

### AWS (Monthly)
- **RDS db.t3.micro**: ~$12-15 (free tier: $0)
- **NAT Gateway** (if needed): $32/month
- **Data transfer**: ~$1-5/month
- **API calls**: Free tier (1M requests/month)
- **Total**: ~$45-55 (or $0 if within free tier)

### External
- **OpenAI API**: ~$0.01-0.10 per analysis (very cheap)

## Troubleshooting

### Issue: "NoCredentialsError" or "AccessDenied"

```bash
# Verify your key works locally
aws sts get-caller-identity
```

Then open the dashboard **Settings** panel and enter your Access Key ID and Secret Access Key there — the app reads credentials from the UI, not from environment variables.

### Issue: "An error occurred (UnauthorizedOperation) when calling..."

The IAM user doesn't have the required permissions. Add the following policies:
- `ReadOnlyAccess`
- `SecurityAudit`

### Issue: Database connection fails

```bash
# Test connection
psql -h your-endpoint.rds.amazonaws.com -U postgres -d costdetective
```

If it fails, check:
1. RDS security group allows inbound on port 5432
2. Endpoint is correct
3. Username and password are correct

## Next Steps

1. **Fill in all `.env` variables** with your actual values
2. **Run the backend**: `python -m uvicorn main:app --reload`
3. **Run the frontend**: `npm run dev`
4. **Test signup/login**
5. **Run a cost analysis** on your AWS account
6. **Review the AI findings** and recommendations

## Security Best Practices

⚠️ **NEVER commit `.env` to Git**

1. Add `.env` to `.gitignore`
2. Use AWS IAM roles (not access keys) in production
3. Rotate access keys every 90 days
4. Use a strong JWT secret
5. Run RDS with encryption enabled
6. Restrict security group access

## Support

For AWS-specific issues:
- AWS Documentation: https://docs.aws.amazon.com
- AWS Support: https://console.aws.amazon.com/support

For OpenAI API issues:
- OpenAI Documentation: https://platform.openai.com/docs
- OpenAI Support: https://help.openai.com
