# Prompt 2: OpenAI API Integration for Cost Analysis

Build on top of the existing FastAPI backend. Add AI-powered cost analysis using the OpenAI API directly.

## What to build

- Create an `ai_analyzer.py` module in `backend/` that:
  - Takes the list of AWS resources (from `aws_scanner.py`) as input.
  - Builds a prompt asking the AI to analyze the resources for: over-provisioning, unused/idle resources, misconfigurations, wrong instance types, and cost optimization opportunities.
  - Calls the OpenAI chat completions API (`gpt-4o`) and returns the structured analysis.
- The AI response should include: a summary, list of issues found (with severity: high/medium/low), estimated savings, and actionable fix commands (AWS CLI commands the user can run).
- Update `POST /api/analyze` to call `aws_scanner` first, then pass results to `ai_analyzer`, and return the final analysis.
- Store the OpenAI API key in environment variables. Add a `.env.example` file.
- Update `requirements.txt` — add `openai`, `python-dotenv`.

## AI Prompt Template

The prompt should analyze AWS resources for:
- **EC2**: Right-sizing opportunities, unused instances, older generation types
- **RDS**: Wrong instance sizes, unused databases, missing read replicas
- **S3**: Unused buckets, missing lifecycle policies, versioning costs
- **Lambda**: Over-provisioned memory, unused functions
- **Storage**: Unattached EBS volumes, old snapshots, inefficient storage classes
- **Network**: Unused Elastic IPs, data transfer costs, unused NAT Gateways

## Project structure update

```
backend/
├── main.py          (updated)
├── aws_scanner.py   (no change)
├── ai_analyzer.py   (new)
├── requirements.txt (updated)
├── .env.example     (updated — add OPENAI_API_KEY)
```

Refer to `Architecture.MD` and `RequestFlow.MD`. This covers step ⑤ of the request flow.
