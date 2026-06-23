## AI Cloud Cost Detective - Request Flow (AWS Edition)

```
①  User ─·─·─► React ─·─·─► FastAPI Auth ─·─·─► JWT (AWS RDS PostgreSQL)

②  User selects AWS Region/Service ─·─·─► Python Backend

③  Python ─·─·─► AWS SDK (boto3) ─·─·─► Fetches all resources (EC2, RDS, S3, Lambda, etc.)

④  Python ─·─·─► FastAPI WebSocket ─·─·─► React (live progress)

⑤  Python ─·─·─► OpenAI API ─·─·─► Cost analysis

⑥  Python ─·─·─► AWS RDS PostgreSQL ─·─·─► Stores analysis history

⑦  React ◄·─·─·─ Final report with suggestions & fixes
```
