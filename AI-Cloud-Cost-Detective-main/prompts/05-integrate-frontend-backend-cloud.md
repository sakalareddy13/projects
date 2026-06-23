# Prompt 5: Integrate Frontend with Backend (End-to-End AWS Edition)

Connect the React frontend to the FastAPI backend. Wire up WebSocket for live progress, auth for all routes, and history display.

## What to build

### API Integration

- When the user clicks "Run Analysis", send `POST /api/analyze` with selected regions, services, and JWT in the `Authorization` header
  - Payload: `{ "regions": ["us-east-1", "us-west-2"], "services": ["ec2", "rds", "s3"], "analysis_id": "uuid" }`
- On the backend, validate the JWT on all protected endpoints (`/api/analyze`, `/api/history`, `/api/regions`, `/api/services`) using a FastAPI dependency

### WebSocket Progress

- After triggering analysis, connect to `ws://localhost:8000/ws/progress/{analysis_id}` from React
- Display each progress message in the `ProgressTracker` component as an animated step list
- Update the list in real-time as messages arrive

### History + Reports

- History page fetches from `GET /api/history` with JWT
- Clicking a past analysis opens the Report page with full details
- Include filters: by date range, by regions, by issues found, by severity

### Report Display

- Summary card at the top:
  - Regions scanned
  - Services analyzed
  - Total resources found
  - Issues found
  - Estimated monthly savings
  - Estimated annual savings
- Each issue shows:
  - AWS service (EC2, RDS, S3, etc)
  - Resource name
  - Issue type (over-provisioned / unused / misconfigured / non-optimized)
  - Severity badge (high = red, medium = yellow, low = green)
  - Explanation and impact
  - Fix command in a copyable code block
  - Potential savings ($)

### Example Issues to Display

- "Downsize EC2 instance from t3.large to t3.medium → Save $50/month"
- "Delete unused EBS volumes (gp2 20GB) → Save $2/month"
- "Add S3 lifecycle policy to archive old logs → Save $100/month"
- "Use Reserved Instances for production RDS → Save $200/month"
- "Remove unused Elastic IP → Save $3.60/month"

### Final Testing

- Test the full flow: signup → login → select regions/services → run analysis → see live progress → view report → check history
- Verify JWT is included in all API calls
- Verify WebSocket progress updates in real-time
- Verify all fix commands are correct AWS CLI syntax

Refer to `Architecture.MD` and `RequestFlow.MD`. This covers the full end-to-end flow — steps ① through ⑦.
