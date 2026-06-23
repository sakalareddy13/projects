# Prompt 1: FastAPI Backend + AWS SDK (boto3)

Create a Python FastAPI backend in a `backend/` folder for the AI Cloud Cost Detective project.

## What to build

- A FastAPI server with a `POST /api/analyze` endpoint that accepts `{ "regions": ["us-east-1", "us-west-2"], "services": ["ec2", "rds", "s3"] }`.
- A `GET /api/regions` endpoint that returns the list of available AWS regions.
- A `GET /api/services` endpoint that returns the list of AWS services to scan.
- Use Python's `boto3` (AWS SDK) to fetch resources:
  - `ec2.describe_instances()` for EC2 instances
  - `rds.describe_db_instances()` for RDS databases
  - `s3.list_buckets()` for S3 buckets
  - `lambda.list_functions()` for Lambda functions
  - And other relevant AWS service APIs
- Parse the AWS API responses and return structured data with: resource type, name, region, instance type/size, tags, and estimated monthly cost
- Add error handling for missing AWS credentials, invalid regions, or API errors
- Enable CORS for `http://localhost:5173`
- Include a `requirements.txt` with `fastapi`, `uvicorn`, `boto3`

## AWS Setup Required

Before running the backend, users must:
1. Install AWS CLI: `brew install awscli` (macOS) or download from aws.amazon.com
2. Configure AWS credentials:
   - `aws configure` and enter AWS Access Key ID and Secret Access Key
   - Or set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables
3. Ensure IAM user has permissions for: `ec2:Describe*`, `rds:Describe*`, `s3:List*`, `lambda:List*`, `organizations:List*` (for cost data)

## Project structure

```
backend/
├── main.py
├── aws_scanner.py
├── requirements.txt
├── .env.example
```

## Environment Variables (.env.example)

```
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
OPENAI_API_KEY=your_openai_key
```

Refer to `Architecture.MD` and `RequestFlow.MD`. This covers step ③ of the request flow.
